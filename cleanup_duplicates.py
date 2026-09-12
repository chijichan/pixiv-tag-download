# -*- coding: utf-8 -*-
"""
删除 downloadIMG\pixiv_muxmus 中与 W:\Img\葬送的芙莉莲\芙莉莲 同名的文件
用于清理：已在芙莉莲目录保存过的图片，从下载目录中删除，避免重复占用空间

使用方式：
    python cleanup_duplicates.py           # 预览（dry-run），只显示将要删除的文件
    python cleanup_duplicates.py --delete  # 真正执行删除
"""
import os
import sys
import argparse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ==================== 配置区 ====================
SRC_DIR = r"W:\Img\葬送的芙莉莲\芙莉莲"          # 源目录（保留的文件）
TARGET_DIR = r"E:\pj\downloadIMG\pixiv_muxmus"  # 目标目录（要清理的文件）
# ==============================================


def collect_filenames(root):
    """递归收集目录下所有文件名集合"""
    names = set()
    if not os.path.isdir(root):
        print(f"[X] 目录不存在: {root}")
        return names
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            names.add(fn)
    return names


def main():
    parser = argparse.ArgumentParser(description="清理重复文件")
    parser.add_argument("--delete", action="store_true", help="真正删除（默认仅预览）")
    args = parser.parse_args()

    src_names = collect_filenames(SRC_DIR)
    if not src_names:
        print(f"[X] 源目录为空或不存在: {SRC_DIR}")
        return
    print(f"[OK] 源目录 {SRC_DIR} 共 {len(src_names)} 个文件")

    tgt_names = collect_filenames(TARGET_DIR)
    if not tgt_names:
        print(f"[OK] 目标目录为空或不存在，无需清理: {TARGET_DIR}")
        return
    print(f"[OK] 目标目录 {TARGET_DIR} 共 {len(tgt_names)} 个文件")

    # 找出目标目录中与源目录同名的文件
    to_delete = sorted(tgt_names & src_names)

    if not to_delete:
        print("[OK] 没有需要删除的同名文件")
        return

    print(f"\n共 {len(to_delete)} 个文件在目标目录中与源目录同名，将被删除：")
    for fn in to_delete:
        print(f"  - {fn}")

    if not args.delete:
        print("\n[预览模式] 未删除任何文件。确认无误后加 --delete 参数执行：")
        print("    python cleanup_duplicates.py --delete")
        return

    # 执行删除
    deleted = 0
    failed = 0
    for fn in to_delete:
        path = os.path.join(TARGET_DIR, fn)
        try:
            os.remove(path)
            deleted += 1
        except Exception as e:
            failed += 1
            print(f"  [X] 删除失败 {fn}: {e}")

    print(f"\n完成! 删除 {deleted} 个, 失败 {failed} 个")


if __name__ == "__main__":
    main()
