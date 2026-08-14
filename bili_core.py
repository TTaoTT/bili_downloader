"""
bili_core.py — B站视频下载核心逻辑（GUI / CLI 共用）

基于 yt-dlp 引擎：
- 自动识别「多P视频 / 合集 / 收藏夹 / 频道」，无需逐个输入分P链接
- 支持登录 Cookie（同目录 cookies.txt 自动启用，也可在界面粘贴 Cookie 字符串）
- 通过回调把日志与进度抛给上层（GUI 或 CLI）
"""
import os
import re
import sys
import json
import shutil
import time
import threading
import urllib.request
import zipfile
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


class StopDownload(Exception):
    """在进度回调里抛出以中止下载。"""
    pass


class _YdlLogger:
    """把 yt-dlp 内部日志路由到上层回调。"""
    def __init__(self, on_log):
        self.on_log = on_log

    def debug(self, msg):
        if self.on_log:
            self.on_log(msg, "debug")

    def info(self, msg):
        if self.on_log:
            self.on_log(msg, "info")

    def warning(self, msg):
        if self.on_log:
            self.on_log(msg, "warn")

    def error(self, msg):
        if self.on_log:
            self.on_log(msg, "error")


class BiliDownloader:
    def __init__(self):
        self._stop = False
        self._paused = False
        self._pause_reported = False
        self._pause_lock = threading.Lock()
        self._on_log = None
        self._on_progress = None
        self._on_item = None

    # ---------- 控制 ----------
    def request_stop(self):
        self._stop = True

    def request_pause(self):
        """暂停：下载线程会在下次进度回调处阻塞，直到 request_resume()。"""
        self._paused = True

    def request_resume(self):
        """继续：解除暂停阻塞。"""
        self._paused = False

    def is_paused(self):
        return self._paused

    def _should_stop(self):
        return self._stop

    # ---------- 工具 ----------
    @staticmethod
    def find_cookies(base_dir=None):
        """按顺序查找 cookies.txt：base_dir -> 脚本/exe 目录 -> 当前目录。"""
        candidates = []
        if base_dir:
            candidates.append(os.path.join(base_dir, "cookies.txt"))
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, "cookies.txt"))
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            candidates.append(os.path.join(exe_dir, "cookies.txt"))
        candidates.append(os.path.join(os.getcwd(), "cookies.txt"))
        for c in candidates:
            if c and os.path.isfile(c):
                return c
        return None

    @staticmethod
    def ffmpeg_path():
        """返回 ffmpeg.exe 路径；找不到返回 None。
        依次检查：PATH -> exe 同目录 / 临时解压目录(_MEIPASS) 的 tools/ffmpeg/bin 与根目录
        -> 源码目录。注意打包成单文件 exe 时，__file__ 指向 MEIPASS 临时目录，
        必须用 sys.executable 的目录（exe 真实所在目录）才能找到用户手动放置的 ffmpeg。"""
        exe = shutil.which("ffmpeg")
        if exe:
            return exe
        candidates = []
        if getattr(sys, "frozen", False):
            exe_dir = os.path.dirname(sys.executable)
            candidates.append(os.path.join(exe_dir, "tools", "ffmpeg", "bin", "ffmpeg.exe"))
            candidates.append(os.path.join(exe_dir, "ffmpeg.exe"))
            base = getattr(sys, "_MEIPASS", exe_dir)
            candidates.append(os.path.join(base, "ffmpeg.exe"))
            candidates.append(os.path.join(base, "ffmpeg", "ffmpeg.exe"))
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, "tools", "ffmpeg", "bin", "ffmpeg.exe"))
        candidates.append(os.path.join(script_dir, "ffmpeg.exe"))
        for c in candidates:
            if c and os.path.isfile(c):
                return c
        return None

    @staticmethod
    def has_ffmpeg():
        return BiliDownloader.ffmpeg_path() is not None

    @staticmethod
    def _download_file(url, dest, on_log=None, timeout=60, max_retries=4,
                       chunk_size=1024 * 1024):
        """带重试与进度回传的单文件下载（urllib 实现，无需第三方库）。
        单块读取超过 timeout 秒即视为卡死并重试；任一镜像重试耗尽再换下一个。
        返回 True / False。"""
        import ssl
        import time
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                if on_log:
                    on_log(f"    [第 {attempt}/{max_retries} 次尝试]", "debug")
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0 Safari/537.36",
                    "Accept": "*/*",
                })
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                    total = r.length or 0
                    tmp = dest + ".part"
                    if os.path.isfile(tmp):
                        os.remove(tmp)
                    downloaded = 0
                    last_pct = -1
                    with open(tmp, "wb") as f:
                        while True:
                            chunk = r.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                pct = int(downloaded * 100 / total)
                                if pct - last_pct >= 10:
                                    last_pct = pct
                                    if on_log:
                                        on_log(f"    下载进度 {pct}%", "debug")
                            elif downloaded % (8 * chunk_size) == 0:
                                if on_log:
                                    on_log(f"    已下载 {downloaded // (1024 * 1024)} MB", "debug")
                os.replace(tmp, dest)
                return True
            except Exception as e:
                last_err = e
                if on_log:
                    on_log(f"    [第 {attempt}/{max_retries} 次] 失败: {e}", "warn")
                try:
                    time.sleep(2)
                except Exception:
                    pass
        if on_log and last_err:
            on_log(f"    该镜像最终失败: {last_err}", "warn")
        return False

    @staticmethod
    def _ensure_ffmpeg(on_log):
        """若本地/同目录没有 ffmpeg，则下载便携版到 tools/ffmpeg/bin（由界面按钮触发）。
        多镜像 + 重试 + 分块进度；失败也不阻断，仅画质受限。返回 ffmpeg.exe 路径或 None。"""
        p = BiliDownloader.ffmpeg_path()
        if p:
            return p
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
            else os.path.dirname(os.path.abspath(__file__))
        dest_dir = os.path.join(base, "tools", "ffmpeg", "bin")
        os.makedirs(dest_dir, exist_ok=True)
        exe_target = os.path.join(dest_dir, "ffmpeg.exe")
        zp = os.path.join(dest_dir, "ffmpeg.zip")
        # 镜像列表：官方 essentials（小，~45MB）优先；GitHub BtbN（稳，~170MB）兜底
        mirrors = [
            "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-gpl.zip",
        ]
        if on_log:
            on_log("未找到 ffmpeg，开始下载便携版（多镜像自动重试，约几十~一百多 MB）...", "info")
        ok = False
        for url in mirrors:
            if on_log:
                on_log(f"尝试镜像: {url}", "info")
            if BiliDownloader._download_file(url, zp, on_log, timeout=60, max_retries=4):
                ok = True
                break
            # 失败清理残留，避免下次误用半截文件
            if os.path.isfile(zp):
                try:
                    os.remove(zp)
                except Exception:
                    pass
        if not ok:
            if on_log:
                on_log("ffmpeg 下载失败（不影响使用，仅画质受限）。可手动下载后放到 exe 同目录 "
                       "tools/ffmpeg/bin：\n"
                       "  官方: https://www.gyan.dev/ffmpeg/builds/  \n"
                       "  GitHub: https://github.com/BtbN/FFmpeg-Builds/releases", "warn")
            return None
        # 解压取出 ffmpeg.exe
        try:
            with zipfile.ZipFile(zp) as z:
                cand = [n for n in z.namelist() if n.endswith("bin/ffmpeg.exe")]
                if not cand:
                    cand = [n for n in z.namelist() if n.endswith("ffmpeg.exe")]
                if not cand:
                    raise FileNotFoundError("ffmpeg.exe not found in archive")
                z.extract(cand[0], dest_dir)
                src = os.path.join(dest_dir, cand[0])
                if os.path.abspath(src) != os.path.abspath(exe_target):
                    if os.path.isfile(exe_target):
                        os.remove(exe_target)
                    shutil.move(src, exe_target)
            try:
                os.remove(zp)
            except Exception:
                pass
            if on_log:
                on_log("ffmpeg 已就绪，最高画质已解锁。", "ok")
            return exe_target if os.path.isfile(exe_target) else None
        except Exception as e:
            if on_log:
                on_log(f"ffmpeg 解压失败（不影响使用，仅画质受限）: {e}", "warn")
            return None

    # ---------- Cookie / 合集检测 ----------
    @staticmethod
    def _cookie_header(cookies_path):
        """把 cookies.txt（Netscape）转成请求头 Cookie 字符串，供网页抓取用。"""
        if not cookies_path or not os.path.isfile(cookies_path):
            return None
        try:
            parts = []
            with open(cookies_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    cols = line.split("\t")
                    if len(cols) >= 7:
                        parts.append(f"{cols[5]}={cols[6]}")
                    elif "=" in line:
                        name, _, value = line.partition("=")
                        parts.append(f"{name.strip()}={value.strip().strip(chr(34))}")
            return "; ".join(parts) if parts else None
        except Exception:
            return None

    @staticmethod
    def _extract_initial_state(html):
        """从 B站网页里抽取 window.__INITIAL_STATE__ 的 JSON（用括号配对，避免提前截断）。"""
        marker = "window.__INITIAL_STATE__"
        i = html.find(marker)
        if i < 0:
            return None
        j = html.find("{", i)
        if j < 0:
            return None
        depth = 0
        in_str = False
        esc = False
        k = j
        n = len(html)
        while k < n:
            c = html[k]
            if esc:
                esc = False
            elif c == "\\" and in_str:
                esc = True
            elif c == '"' and not esc:
                in_str = not in_str
            elif not in_str:
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return html[j:k + 1]
            k += 1
        return None

    def _resolve_collection(self, url, cookie_header):
        """若单集属于 B站「合集(ugc_season)」，返回 (合集URL, 标题)；否则 None。
        合集URL 交给 yt-dlp 的 BilibiliChannelCollection 提取器展开。"""
        import ssl
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        })
        if cookie_header:
            req.add_header("Cookie", cookie_header)
        try:
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                html = r.read().decode("utf-8", "ignore")
        except Exception:
            return None
        raw = self._extract_initial_state(html)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            return None
        ugc = data.get("ugc_season")
        if not ugc:
            return None
        sid = ugc.get("id")
        mid = (data.get("upData") or {}).get("mid")
        if not sid or not mid:
            return None
        title = ugc.get("title") or "合集"
        eps = []
        for sec in ugc.get("sections") or []:
            for ep in sec.get("episodes") or []:
                if ep.get("bvid"):
                    eps.append(ep["bvid"])
        if len(eps) <= 1:
            return None
        coll_url = f"https://space.bilibili.com/{mid}/channel/collectiondetail?sid={sid}"
        return coll_url, title

    # ---------- 内部 ----------
    def _log(self, msg, level="info"):
        if self._on_log:
            self._on_log(msg, level)

    def _base_opts(self, out_dir, cookies_path):
        ffmpeg_ok = self.has_ffmpeg()
        ffmpeg_bin = self.ffmpeg_path()
        opts = {
            "outtmpl": {"default": ""},  # 每个链接单独设置
            "format": "bv*+ba/best" if ffmpeg_ok else "best",
            "merge_output_format": "mp4",
            "retries": 5,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": 8,
            "http_chunk_size": 1024 * 1024,
            "continuedl": True,
            "ignoreerrors": True,   # 单个分P失败不中断整个合集
            "noplaylist": False,
            "yesplaylist": True,    # 强制把合集/多P 当播放列表下载
            "noprogress": True,     # 用进度回调代替内置进度条
            "quiet": True,
            "no_warnings": False,
            "logger": _YdlLogger(self._on_log),
        }
        if cookies_path and os.path.isfile(cookies_path):
            opts["cookiefile"] = cookies_path
        if ffmpeg_bin:
            # yt-dlp 需要 ffmpeg 所在目录或可执行文件路径
            opts["ffmpeg_location"] = os.path.dirname(ffmpeg_bin)
        return opts

    def _make_hook(self, idx, total):
        def hook(d):
            if self._should_stop():
                raise StopDownload("用户取消")
            # 暂停：在进度回调处阻塞，直到继续或停止（实现「暂停/继续」）
            if self._paused:
                first = False
                with self._pause_lock:
                    if not self._pause_reported:
                        self._pause_reported = True
                        first = True
                        self._log("  ⏸ 已暂停（当前分P下载暂停，点「继续」恢复）", "info")
                # 阻塞：每 0.3s 检查一次，避免忙等；停止信号也能立即解除
                while self._paused and not self._stop:
                    time.sleep(0.3)
                with self._pause_lock:
                    if first:
                        self._pause_reported = False
                        self._log("  ▶ 已继续", "info")
                if self._should_stop():
                    raise StopDownload("用户取消")
            if self._on_progress:
                d = dict(d)
                d["_item_index"] = idx
                d["_item_total"] = total
                self._on_progress(d)
        return hook

    def _detect_playlist(self, url, opts):
        """用 extract_flat 快速判断是否为合集/多P（不拉取每个分P的完整信息）。"""
        det = dict(opts)
        det.update({
            "extract_flat": True,
            "dump_single_json": True,
            "simulate": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": {"default": "-"},
            "logger": _YdlLogger(lambda m, l: None),
        })
        try:
            with YoutubeDL(det) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:  # 检测失败则按普通视频处理
            self._log(f"  合集检测失败，按普通视频处理: {e}", "warn")
            return False, None
        if not info:
            return False, None
        is_pl = info.get("_type") == "playlist" or (
            "entries" in info and info.get("_type") != "url"
        )
        return is_pl, info

    # ---------- 对外接口 ----------
    def download(self, urls, out_dir, cookies_path=None, auto_collection=True,
                 on_log=None, on_progress=None, on_item=None):
        """
        urls: list[str]  B站链接
        out_dir: str     输出根目录
        cookies_path: str|None
        auto_collection: bool  粘贴单集时是否自动下载所在合集的其他视频
        on_log(msg, level)        level in info|ok|warn|error|debug
        on_progress(dict)         yt-dlp 进度字典，附带 _item_index/_item_total
        on_item(index, total, url) 开始处理某个链接时回调
        """
        self._stop = False
        self._paused = False
        self._pause_reported = False
        self._on_log = on_log
        self._on_progress = on_progress
        self._on_item = on_item

        urls = [u.strip() for u in urls if u and u.strip()]
        if not urls:
            self._log("没有有效的链接。", "warn")
            return

        os.makedirs(out_dir, exist_ok=True)
        base = self._base_opts(out_dir, cookies_path)
        total = len(urls)

        if cookies_path and os.path.isfile(cookies_path):
            self._log(f"已启用登录 Cookie: {cookies_path}", "ok")
        else:
            self._log("未找到 Cookie，使用匿名下载（画质可能受限）。", "warn")

        if not self.has_ffmpeg():
            self._log("未检测到 ffmpeg，将只下载「已合成」格式（画质略低，无法音视频合并）。\n"
                      "  如需最高画质，请点击状态栏的「下载 ffmpeg」按钮安装便携版。",
                      "warn")

        cookie_header = self._cookie_header(cookies_path)

        for idx, url in enumerate(urls, 1):
            if self._should_stop():
                self._log("已取消。", "warn")
                break
            self._log(f"[{idx}/{total}] 处理: {url}", "info")
            if self._on_item:
                self._on_item(idx, total, url)

            # 合集自动展开：粘贴单集链接 -> 下载整集合集
            resolved_url = url
            coll_title = None
            if auto_collection:
                try:
                    res = self._resolve_collection(url, cookie_header)
                except Exception as e:
                    res = None
                    self._log(f"  合集检测异常，按普通视频处理: {e}", "warn")
                if res:
                    resolved_url, coll_title = res
                    self._log(f"  -> 检测到合集《{coll_title}》，将自动下载全集", "info")

            try:
                is_pl, info = self._detect_playlist(resolved_url, base)
            except Exception as e:
                self._log(f"  解析失败，跳过: {e}", "error")
                continue

            if is_pl and info is not None:
                title = info.get("title") or coll_title or "合集"
                n = len(info.get("entries") or [])
                self._log(f"  -> 检测到合集/多P：《{title}》 共 {n} 个", "info")
                base["outtmpl"] = {
                    "default": os.path.join(
                        out_dir,
                        "%(playlist_title)s",
                        "%(playlist_index)02d - %(title)s [%(id)s].%(ext)s",
                    )
                }
            elif coll_title:
                # 合集已展开但播放列表探测失败：仍按合集目录落盘
                self._log(f"  -> 按合集《{coll_title}》目录保存", "info")
                base["outtmpl"] = {
                    "default": os.path.join(
                        out_dir, _safe_name(coll_title),
                        "%(title)s [%(id)s].%(ext)s",
                    )
                }
            else:
                base["outtmpl"] = {
                    "default": os.path.join(
                        out_dir, "%(title)s [%(id)s].%(ext)s"
                    )
                }

            base["progress_hooks"] = [self._make_hook(idx, total)]
            try:
                with YoutubeDL(base) as ydl:
                    ydl.download([resolved_url])
                self._log(f"  OK 完成", "ok")
            except StopDownload:
                self._log("用户取消下载。", "warn")
                break
            except DownloadError as e:
                self._log(f"  X 下载出错: {e}", "error")
            except Exception as e:
                self._log(f"  X 未知错误: {e}", "error")

        self._log("全部任务结束。", "info")


def _safe_name(s):
    """把合集标题转成安全的文件夹名。"""
    if not s:
        return "合集"
    bad = '/\\:*?"<>|'
    return "".join("_" if c in bad else c for c in s).strip() or "合集"
