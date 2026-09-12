# -*- coding: utf-8 -*-
"""
从 pid_list.txt 读取 PID，通过 i.muxmus.com 批量下载
使用方式：
    python muxmus_download.py [pid列表文件] [-o 输出目录]
"""
import os
import sys
import time
import glob
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# 解决 Windows GBK 控制台中文/emoji 乱码
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = "https://i.muxmus.com"
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pixiv_muxmus")

EXT_MAP = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
}


def find_existing(pid, save_dir):
    """检查该 PID 是否已下载（匹配任意扩展名），返回已存在的文件路径或 None"""
    if not os.path.isdir(save_dir):
        return None
    pattern = os.path.join(save_dir, pid + ".*")
    matches = glob.glob(pattern)
    return matches[0] if matches else None


def verify_image(filepath, ext):
    """校验图片文件完整性，返回 (ok, 说明)。
    检测：非空、文件头魔数、尾部结束标记（可识别截断的损坏图）。
    """
    try:
        size = os.path.getsize(filepath)
        if size == 0:
            return False, "文件为空(0字节)"
        if size < 8:
            return False, "文件过小，疑似损坏"

        with open(filepath, "rb") as f:
            head = f.read(12)
            # 定位到文件尾读最后若干字节
            f.seek(max(0, size - 24))
            tail = f.read()

        ext_l = (ext or ".img").lower()

        # 魔数校验
        if ext_l == ".png":
            if not head.startswith(b"\x89PNG\r\n\x1a\n"):
                return False, "PNG 文件头无效"
            if not tail.endswith(b"IEND\xaeB`\x82"):
                return False, "PNG 缺少 IEND 结束块，文件截断"
        elif ext_l == ".jpg":
            if not head.startswith(b"\xff\xd8\xff"):
                return False, "JPEG 文件头无效"
            if not tail.rstrip(b"\x00\xff").endswith(b"\xff\xd9"):
                return False, "JPEG 缺少 EOI 结束标记，文件截断"
        elif ext_l == ".gif":
            if not head.startswith(b"GIF87a") and not head.startswith(b"GIF89a"):
                return False, "GIF 文件头无效"
            if not tail.endswith(b"\x3b"):
                return False, "GIF 缺少结尾标记，文件截断"
        elif ext_l == ".webp":
            if not head.startswith(b"RIFF") or head[8:12] != b"WEBP":
                return False, "WEBP 文件头无效"
        elif ext_l == ".bmp":
            if not head.startswith(b"BM"):
                return False, "BMP 文件头无效"

        return True, f"完整性OK({size}字节)"
    except Exception as e:
        return False, f"校验异常: {e}"


def download_pid(pid, save_dir, session, check=True):
    url = f"{BASE}/{pid}"
    try:
        r = session.get(url, timeout=60, stream=True)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        ctype = r.headers.get("Content-Type", "")
        ext = EXT_MAP.get(ctype, ".img")
        filepath = os.path.join(save_dir, f"{pid}{ext}")
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

        # 图片完整性检测，失败则删除损坏文件
        if check:
            ok, msg = verify_image(filepath, ext)
            if not ok:
                try:
                    os.remove(filepath)
                except Exception:
                    pass
                return False, f"完整性检测失败({msg})"
            return True, os.path.basename(filepath) + " (" + msg + ")"
        return True, os.path.basename(filepath)
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="i.muxmus.com 批量下载")
    parser.add_argument("pidfile", nargs="?", default="pid_list.txt", help="PID 列表文件，每行一个")
    parser.add_argument("-o", "--output", default=SAVE_DIR, help="输出目录")
    parser.add_argument("-c", "--concurrency", type=int, default=5, help="并发下载数，默认5")
    parser.add_argument("--no-skip", action="store_true", help="不跳过已下载的图片")
    parser.add_argument("--no-check", action="store_true", help="关闭下载后图片完整性检测")
    parser.add_argument("--retry", type=int, default=5,
                        help="网络失败重试次数（默认5；连续4次404/403判定永久失效，提前跳过）")
    parser.add_argument("--repair", action=argparse.BooleanOptionalAction, default=True,
                        help="启动时校验已下载图片，损坏的自动删除重新下载（默认开启，--no-repair 关闭）")
    args = parser.parse_args()

    if not os.path.exists(args.pidfile):
        print(f"[X] 找不到文件: {args.pidfile}")
        return

    with open(args.pidfile, "r", encoding="utf-8") as f:
        pids = [line.strip() for line in f if line.strip()]

    if not pids:
        print("[X] PID 列表为空")
        return

    os.makedirs(args.output, exist_ok=True)

    # 跳过已下载的 PID（启动时先校验已存在文件，损坏的删除重下，用于断点续传）
    if not args.no_skip:
        pending = []
        skipped = 0
        repaired = 0
        for pid in pids:
            existing = find_existing(pid, args.output)
            if existing:
                if args.repair:
                    ok, msg = verify_image(existing, os.path.splitext(existing)[1])
                    if not ok:
                        try:
                            os.remove(existing)
                        except Exception:
                            pass
                        repaired += 1
                        print(f"  [修复] {pid} 已存在但损坏({msg})，删除后重新下载")
                        pending.append(pid)
                        continue
                skipped += 1
                print(f"  [跳过] {pid} 已存在: {os.path.basename(existing)}")
            else:
                pending.append(pid)
        pids = pending
        if repaired:
            print(f"[OK] 修复损坏文件 {repaired} 个")
        if skipped:
            print(f"[OK] 跳过已下载 {skipped} 个，剩余 {len(pids)} 个待下载")
        if not pids:
            print("[OK] 全部已下载，无需操作")
            return
    else:
        print(f"[OK] 未开启跳过功能（--no-skip），全部 {len(pids)} 个重新下载")

    print(f"[OK] 保存到 {args.output}，并发 {args.concurrency}")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    })

    total = len(pids)
    ok = 0
    fail = 0
    failures = []

    def work(pid):
        # 每个线程独立的 Session，避免并发下 Session 状态竞争
        s = requests.Session()
        s.headers.update(session.headers)
        check = not args.no_check

        # 重试循环：完整性失败/网络错误均可重试（退避递增、封顶）
        # 网络类错误最多尝试 1+retry 次（默认 61 次）；连续 4 次 404/403 判定永久失效，提前跳过
        max_attempts = 1 + max(0, args.retry)
        used = 0
        last_err = None
        perm_fail = 0
        for attempt in range(1, max_attempts + 1):
            used = attempt
            status, info = download_pid(pid, args.output, s, check=check)
            if status:
                return pid, (True, info, used)
            last_err = info
            if attempt >= max_attempts:
                break
            if info.startswith("HTTP 404") or info.startswith("HTTP 403"):
                perm_fail += 1
                if perm_fail >= 4:
                    return pid, (False, f"{info}（连续{perm_fail}次，判定永久失效，不再重试）", used)
                time.sleep(min(2.0 * attempt, 10.0))   # 限流/临时失效，长一点冷却
            else:
                perm_fail = 0
                time.sleep(min(0.5 * attempt, 5.0))    # 网络抖动，短退避
        return pid, (False, last_err, used)
    done = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(work, pid): pid for pid in pids}
        for fut in as_completed(futures):
            pid, (status, info, used) = fut.result()
            done += 1
            if status:
                ok += 1
                print(f"  [{done}/{total}] {pid} -> {info}" + ("" if used == 1 else f" (重试{used-1}次)"))
            else:
                fail += 1
                failures.append(pid)
                print(f"  [{done}/{total}] {pid} 失败: {info}" + ("" if used <= 1 else f" (已重试{used-1}次)"))

    print(f"\n完成! 成功 {ok}, 失败 {fail}")
    if failures:
        print("失败的 PID:", ", ".join(failures))


if __name__ == "__main__":
    main()
