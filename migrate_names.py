# -*- coding: utf-8 -*-
"""
把工作区根目录下「纯 PID 列表且文件名含中文」的角色文件移动到 names/ 文件夹
（如 凯伊、吹雪、扇喜葵.txt ...），避免根目录越来越乱。
非角色文件（脚本、pid_list.txt、mux_test.txt 等）保留在根目录。

用法:
    python migrate_names.py
"""
import os
import re
import sys
import shutil

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NAMES_DIR = os.path.join(SCRIPT_DIR, "names")

CJK = re.compile(r"[\u4e00-\u9fff]")
PID_RE = re.compile(r"^\d{5,}$")

# 根目录下即使内容是纯数字也不移动的文件（工具自身的工作文件）
KEEP = {"pid_list.txt", "mux_test.txt"}


def is_char_pid_file(path):
    """是角色 PID 文件：文件名含中文，且每一行都是 5 位以上数字"""
    if not CJK.search(os.path.basename(path)):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
    except Exception:
        return False
    return bool(lines) and all(PID_RE.match(l) for l in lines)


def main():
    os.makedirs(NAMES_DIR, exist_ok=True)
    moved, skipped = [], []
    for fn in sorted(os.listdir(SCRIPT_DIR)):
        path = os.path.join(SCRIPT_DIR, fn)
        if not os.path.isfile(path):
            continue
        if fn in KEEP:
            skipped.append(f"{fn}  (工作文件)")
            continue
        if is_char_pid_file(path):
            dst = os.path.join(NAMES_DIR, fn)
            shutil.move(path, dst)
            moved.append(fn)
        else:
            skipped.append(fn)

    print(f"\n移动到 names/ 共 {len(moved)} 个：")
    for fn in moved:
        print(f"  [OK] {fn}")
    print(f"\n保留在根目录共 {len(skipped)} 个：")
    for fn in skipped:
        print(f"  [-] {fn}")


if __name__ == "__main__":
    main()
