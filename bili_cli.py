# -*- coding: utf-8 -*-
"""
bili_cli.py — B站视频下载器（命令行）

用法:
  python bili_cli.py links.txt                 # 从文件读链接
  python bili_cli.py links.txt --out D:/bili   # 指定输出目录
  python bili_cli.py "https://www.bilibili.com/video/BVxxx" "https://.../collection/detail?sid=yyy"
  python bili_cli.py links.txt --cookies cookies.txt

合集 / 多P 视频会自动全部下载，无需逐个列出。
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from bili_core import BiliDownloader  # noqa: E402


def collect_urls(args):
    urls = []
    for path in args.files:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                import re
                urls += [u for u in re.split(r"[\s,]+", f.read()) if u.strip()]
        else:
            urls.append(path)  # 当作直接链接
    return urls


def main():
    ap = argparse.ArgumentParser(description="B站视频下载器（合集/多P 自动全下）")
    ap.add_argument("files", nargs="+", help="链接文件(.txt/.csv)或直接链接")
    ap.add_argument("--out", default=os.path.join(HERE, "downloads"), help="输出目录")
    ap.add_argument("--cookies", default=None, help="Cookie 文件路径（默认自动查找 cookies.txt）")
    args = ap.parse_args()

    dl = BiliDownloader()
    cookies = args.cookies or dl.find_cookies(HERE)
    urls = collect_urls(args)

    if not urls:
        print("没有有效的链接。")
        sys.exit(1)

    dl.download(
        urls,
        args.out,
        cookies_path=cookies,
        on_log=lambda m, l: print(m),
        on_progress=lambda d: None,
        on_item=lambda i, t, u: print(f"\n>>> [{i}/{t}] {u}"),
    )


if __name__ == "__main__":
    main()
