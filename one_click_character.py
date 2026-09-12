# -*- coding: utf-8 -*-
"""
一键角色图片下载流程（直存版）
流程：输入角色名 -> 读取剪贴板 PID -> 写 <角色名>.txt / pid_list.txt
      -> muxmus_download.py -o W:\临时文件夹\<角色名> 直接保存（不经 pixiv_muxmus 中转）
"""
import os, re, sys, subprocess

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PID_LIST = os.path.join(SCRIPT_DIR, "pid_list.txt")
TARGET_ROOT = r"W:\临时文件夹"


def try_read_clipboard():
    try:
        import pyperclip
        return pyperclip.paste().splitlines()
    except Exception:
        return []


def read_pids_from_input():
    print("请粘贴 pixiv_search.js 复制的 PID（每行一个，空行结束）：")
    lines = []
    while True:
        try:
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        lines.append(line)
    return lines


def extract_pids(texts):
    return [t.strip() for t in texts if re.fullmatch(r"\d{5,}", t.strip())]


def load_pid_file(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def save_pid_file(path, pids):
    seen, out = set(), []
    for p in pids:
        if p not in seen:
            seen.add(p); out.append(p)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + ("\n" if out else ""))


def existing_pids_in_target(target_dir):
    if not os.path.isdir(target_dir):
        return set()
    return {os.path.splitext(f)[0] for f in os.listdir(target_dir)}


def main():
    print("=" * 50)
    print("  一键角色图片下载（直存）")
    print("=" * 50)

    name = input("角色名（中文）: ").strip()
    if not name:
        print("[X] 角色名不能为空"); return
    input("日文搜索标签（可选，仅记录）: ").strip()

    char_file = os.path.join(SCRIPT_DIR, name)
    if not os.path.exists(char_file):
        char_file = os.path.join(SCRIPT_DIR, name + ".txt")

    old_pids = load_pid_file(char_file)
    new_pids = extract_pids(try_read_clipboard())
    if new_pids:
        print(f"[OK] 从剪贴板读取到 {len(new_pids)} 个 PID")
    else:
        print("[提示] 剪贴板未检测到 PID，请手动粘贴")
        new_pids = extract_pids(read_pids_from_input())
    if not new_pids:
        print("[X] 未获取到任何 PID"); return

    merged = old_pids + [p for p in new_pids if p not in set(old_pids)]
    save_pid_file(char_file, merged)
    print(f"[OK] 已更新 {os.path.basename(char_file)}，共 {len(merged)} 个 PID")

    target_dir = os.path.join(TARGET_ROOT, name)
    already = existing_pids_in_target(target_dir)
    todo = [p for p in merged if p not in already]
    if not todo:
        print("[OK] 该角色图片已全部在临时文件夹，无需下载"); return

    save_pid_file(PID_LIST, todo)
    print(f"[OK] 已写入 pid_list.txt，待下载 {len(todo)} 个（已忽略已下载的 {len(already)} 个）")

    # 直接下载到目标目录（不经 pixiv_muxmus 中转）
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n>>> 开始下载 -> {target_dir} ...")
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "muxmus_download.py"),
        PID_LIST,
        "-o", target_dir,
    ]
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"[X] 下载脚本返回码 {rc}"); return

    print(f"\n[OK] 图片已直接保存到 {target_dir}")


if __name__ == "__main__":
    main()