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
import subprocess
import tempfile
import threading
import urllib.request
import urllib.parse
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
    # 域名 -> 平台 key（用于按平台分别保存 / 查找 cookie 文件）
    DOMAIN_TO_PLATFORM = {
        "bilibili.com": "bilibili", "b23.tv": "bilibili",
        "douyin.com": "douyin",
        "tiktok.com": "tiktok",
        "xiaohongshu.com": "xiaohongshu", "xhslink.com": "xiaohongshu",
        "weibo.com": "weibo", "weibo.cn": "weibo",
        "acfun.cn": "acfun",
        "ixigua.com": "ixigua",
        "iqiyi.com": "iqiyi",
        "youku.com": "youku",
        "v.qq.com": "qq", "y.qq.com": "qq",
        "mgtv.com": "mgtv",
        "zhihu.com": "zhihu",
        "douyu.com": "douyu",
        "huya.com": "huya",
        "music.163.com": "netease",
    }
    COOKIE_DIR_NAME = "cookies"

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
    def platform_of(host):
        """根据域名返回平台 key（用于 cookie 文件名）；未知返回 None。"""
        host = (host or "").lower()
        for dom, key in BiliDownloader.DOMAIN_TO_PLATFORM.items():
            if host == dom or host.endswith("." + dom):
                return key
        return None

    @staticmethod
    def find_cookies_for(host, base_dir=None):
        """按平台查找专用 cookie 文件，回退通用 cookies.txt。返回路径或 None。

        查找顺序：<dir>/cookies/<platform>.txt（平台专用）-> <dir>/cookies.txt（通用）
        其中 <dir> 依次取 base_dir、脚本/exe 目录、当前目录。
        """
        platform = BiliDownloader.platform_of(host)
        dirs = []
        if base_dir:
            dirs.append(base_dir)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dirs.append(script_dir)
        if getattr(sys, "frozen", False):
            dirs.append(os.path.dirname(sys.executable))
        dirs.append(os.getcwd())
        candidates = []
        if platform:
            for d in dirs:
                candidates.append(os.path.join(d, BiliDownloader.COOKIE_DIR_NAME, f"{platform}.txt"))
        for d in dirs:
            candidates.append(os.path.join(d, "cookies.txt"))
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

    # ---------- yt-dlp 更新 ----------
    @staticmethod
    def yt_dlp_version():
        """返回当前 yt-dlp 版本号，失败返回 None。"""
        try:
            import yt_dlp
            return yt_dlp.version.__version__
        except Exception:
            return None

    @staticmethod
    def _latest_ytdlp_wheel(on_log=None):
        """从 PyPI 获取最新 yt-dlp 的版本号与 wheel 下载地址。"""
        import json
        api = "https://pypi.org/pypi/yt-dlp/json"
        try:
            req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            ver = data["info"]["version"]
            for f in data["urls"]:
                if f.get("packagetype") == "bdist_wheel" and f["filename"].endswith("py3-none-any.whl"):
                    return ver, f["url"]
            for f in data["urls"]:
                if f.get("packagetype") == "bdist_wheel":
                    return ver, f["url"]
        except Exception as e:
            if on_log:
                on_log(f"获取 yt-dlp 版本信息失败: {e}", "warn")
        return None, None

    @staticmethod
    def update_ytdlp(on_log=None, bin_dir=None):
        """更新 yt-dlp。
        - 源码运行（未打包）：`pip install -U yt-dlp`，立即生效。
        - 打包 exe：下载最新 wheel 解压到 <bin_dir>/yt_dlp_vendor，下次启动生效
          （bili_gui 会在导入前把该目录插入 sys.path 并前置，覆盖内置版本）。
        返回 (ok: bool, msg: str)。"""
        if getattr(sys, "frozen", False):
            base = bin_dir or os.path.dirname(sys.executable)
            vendor = os.path.join(base, "yt_dlp_vendor")
            ver, url = BiliDownloader._latest_ytdlp_wheel(on_log)
            if not url:
                return False, "无法获取最新 yt-dlp 下载地址"
            if on_log:
                on_log(f"下载 yt-dlp {ver}（wheel，约 3MB）...", "info")
            whl = os.path.join(base, "yt_dlp_update.whl")
            if not BiliDownloader._download_file(url, whl, on_log, timeout=60, max_retries=4):
                return False, "yt-dlp wheel 下载失败"
            try:
                import shutil as _sh
                if os.path.isdir(vendor):
                    _sh.rmtree(vendor)
                os.makedirs(vendor, exist_ok=True)
                with zipfile.ZipFile(whl) as z:
                    z.extractall(vendor)
                os.remove(whl)
                with open(os.path.join(vendor, "VERSION"), "w", encoding="utf-8") as f:
                    f.write(ver)
                if on_log:
                    on_log(f"yt-dlp 已更新到 {ver}，重启程序后生效。", "ok")
                return True, f"yt-dlp {ver}（重启生效）"
            except Exception as e:
                return False, f"解压失败: {e}"
        # 源码模式
        py = sys.executable
        if on_log:
            on_log("正在通过 pip 更新 yt-dlp ...", "info")
        try:
            cp = subprocess.run([py, "-m", "pip", "install", "-U", "yt-dlp"],
                                capture_output=True, text=True, timeout=300)
            if cp.returncode != 0:
                if on_log:
                    on_log("pip 更新失败:\n" + (cp.stderr or cp.stdout)[-800:], "error")
                return False, "pip 更新失败"
            v = BiliDownloader.yt_dlp_version()
            if on_log:
                on_log(f"yt-dlp 已更新到 {v}。", "ok")
            return True, f"yt-dlp {v}"
        except Exception as e:
            return False, f"更新异常: {e}"

    @staticmethod
    def check_app_update(repo="TTaoTT/bili_downloader", on_log=None):
        """检查 GitHub 仓库最新 release（用于程序自身更新提示）。
        返回 (latest_tag, html_url)；失败返回 (None, None)。"""
        import json
        api = f"https://api.github.com/repos/{repo}/releases/latest"
        try:
            req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            return data.get("tag_name"), data.get("html_url")
        except Exception as e:
            if on_log:
                on_log(f"检查程序更新失败: {e}", "warn")
            return None, None

    @staticmethod
    def ytdlp_update_available(on_log=None):
        """返回 (current, latest, has_update)。
        has_update: True=有更新可用, False=已是最新, None=检查失败。"""
        cur = BiliDownloader.yt_dlp_version()
        latest, _ = BiliDownloader._latest_ytdlp_wheel(on_log)
        has = None
        if cur and latest:
            has = latest != cur
        return cur, latest, has

    # ---------- Cookie / 合集检测 ----------
    @staticmethod
    def _read_cookie_pairs(cookies_path):
        """读取 cookies.txt，返回 [(name, value), ...]，兼容 Netscape 与
        name=value; name2=value2 两种格式（每行可能含多个 cookie）。"""
        pairs = []
        try:
            with open(cookies_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    cols = line.split("\t")
                    if len(cols) >= 7:
                        pairs.append((cols[5].strip(), cols[6].strip()))
                    elif "=" in line:
                        # 头部风格：SESSDATA=abc; bili_jct=xyz（每行可能多个）
                        for part in line.split(";"):
                            part = part.strip()
                            if "=" not in part:
                                continue
                            name, _, value = part.partition("=")
                            pairs.append((name.strip(), value.strip().strip(chr(34))))
        except Exception:
            pass
        return pairs
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

    def _base_opts(self, out_dir, cookies_path, format_choice="best"):
        ffmpeg_ok = self.has_ffmpeg()
        ffmpeg_bin = self.ffmpeg_path()
        audio_only = (format_choice == "audio")
        if audio_only:
            fmt = "ba/bestaudio"
        elif not ffmpeg_ok:
            fmt = "best"
        else:
            fmt = {
                "best": "bv*+ba/best",
                "1080p": "bv[height<=1080]+ba/best[height<=1080]",
                "720p": "bv[height<=720]+ba/best[height<=720]",
            }.get(format_choice, "bv*+ba/best")
        opts = {
            "outtmpl": {"default": ""},  # 每个链接单独设置
            "format": fmt,
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
        if audio_only:
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
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

    # ---------- 历史 / 去重 ----------
    @staticmethod
    def _load_history(history_path):
        """载入下载历史（记录已成功/失败的链接）；文件不存在或损坏返回空结构。"""
        if not history_path or not os.path.isfile(history_path):
            return {"done": [], "errors": []}
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
            data.setdefault("done", [])
            data.setdefault("errors", [])
            return data
        except Exception:
            return {"done": [], "errors": []}

    @staticmethod
    def _save_history(history_path, history):
        if not history_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(history_path)), exist_ok=True)
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _preprocess_url(u):
        """把平台专属的非标准分享/精选链接改写为 yt-dlp 可识别的标准链接。

        例：抖音精选页 https://www.douyin.com/jingxuan?modal_id=xxx
            → https://www.douyin.com/video/xxx
        """
        u = (u or "").strip()
        try:
            p = urllib.parse.urlparse(u)
            host = p.netloc.lower()
            q = urllib.parse.parse_qs(p.query)
            # 抖音精选页：/jingxuan?modal_id=xxx → /video/xxx
            if "douyin.com" in host and "modal_id" in q:
                vid = q["modal_id"][0]
                return f"https://www.douyin.com/video/{vid}"
            # 抖音图文/笔记页：/note/{id} 或 /discover?modal_id= 同样取 video
            if "douyin.com" in host and ("/note/" in p.path or "/discover" in p.path) and "modal_id" in q:
                vid = q["modal_id"][0]
                return f"https://www.douyin.com/video/{vid}"
        except Exception:
            pass
        return u

    @staticmethod
    def _norm_url(u):
        """把链接规范化为比较键：小写 host + 去尾部斜杠的 path。"""
        u = (u or "").strip()
        try:
            p = urllib.parse.urlparse(u)
            host = p.netloc.lower()
            path = p.path.rstrip("/")
            return f"{host}{path}"
        except Exception:
            return u.strip().lower()

    @classmethod
    def dedup_urls(cls, urls, history=None):
        """去重：去掉列表内重复 + （若提供 history）已成功下载过的链接。
        返回 (干净列表, 跳过数)。"""
        seen = set()
        out = []
        dup = 0
        done = set()
        if history:
            done = {cls._norm_url(x) for x in history.get("done", [])}
        for u in urls:
            u = u.strip()
            if not u:
                continue
            n = cls._norm_url(u)
            if n in seen or n in done:
                dup += 1
                continue
            seen.add(n)
            out.append(u)
        return out, dup

    # ---------- 对外接口 ----------
    def download(self, urls, out_dir, cookies_path=None, auto_collection=True,
                 format_choice="best", proxy=None, max_workers=1,
                 history_path=None, cookies_base_dir=None,
                 on_log=None, on_progress=None, on_item=None):
        """
        urls: list[str]  视频链接（任意 yt-dlp 支持的平台：B站/抖音/小红书/TikTok/...）
        out_dir: str     输出根目录
        cookies_path: str|None
        auto_collection: bool  粘贴单集时是否自动下载所在合集的其他视频（仅 B站）
        format_choice: str  best | 1080p | 720p | audio（仅音频 mp3）
        proxy: str|None  代理地址，如 http://127.0.0.1:7890 或 socks5://127.0.0.1:7890
        max_workers: int  并发下载链接数（>1 时用线程池；同站建议保守，避免风控）
        history_path: str|None  历史记录 json 路径；提供则自动去重已下载项
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
        urls = [self._preprocess_url(u) for u in urls]
        if not urls:
            self._log("没有有效的链接。", "warn")
            return

        # 历史 + 去重（过滤重复与已下载项）
        history = self._load_history(history_path)
        urls, skipped = self.dedup_urls(urls, history)
        if skipped:
            self._log(f"去重：过滤掉 {skipped} 个重复 / 已下载链接。", "info")
        if not urls:
            self._log("没有新的链接需要下载（均已下载过）。", "warn")
            return

        os.makedirs(out_dir, exist_ok=True)

        if cookies_path and os.path.isfile(cookies_path):
            self._log(f"已启用登录 Cookie: {cookies_path}", "ok")
        else:
            self._log("未找到 Cookie，使用匿名下载（画质可能受限）。", "warn")

        ffmpeg_ok = self.has_ffmpeg()
        if not ffmpeg_ok:
            self._log("未检测到 ffmpeg，将只下载「已合成」格式（画质略低，无法音视频合并）。\n"
                      "  如需最高画质，请点击状态栏的「下载 ffmpeg」按钮安装便携版。",
                      "warn")
        if format_choice == "audio" and not ffmpeg_ok:
            self._log("「仅音频(mp3)」需要 ffmpeg 提取音频，未检测到 ffmpeg，请先安装。", "warn")
        if proxy:
            self._log(f"已启用代理: {proxy}", "info")

        total = len(urls)
        cookie_header = self._cookie_header(cookies_path)

        def run_one(idx, url):
            return self._download_one(url, idx, total, out_dir, cookies_path,
                                      auto_collection, format_choice, proxy,
                                      cookie_header, history, history_path,
                                      cookies_base_dir)

        results = []
        if max_workers and max_workers > 1 and total > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            self._log(f"并发下载模式：{max_workers} 个线程同时下载 {total} 个链接。", "info")
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                fut_map = {}
                for idx, url in enumerate(urls, 1):
                    if self._should_stop():
                        break
                    fut_map[ex.submit(run_one, idx, url)] = (idx, url)
                for fut in as_completed(list(fut_map.keys())):
                    if self._should_stop():
                        for f in fut_map:
                            f.cancel()
                        break
                    idx, url = fut_map[fut]
                    try:
                        ok, err = fut.result()
                    except Exception as e:
                        ok, err = False, str(e)
                    results.append((idx, url, ok, err))
        else:
            for idx, url in enumerate(urls, 1):
                if self._should_stop():
                    self._log("已取消。", "warn")
                    break
                ok, err = run_one(idx, url)
                results.append((idx, url, ok, err))

        # 汇总
        ok_n = sum(1 for r in results if r[2])
        fail_n = sum(1 for r in results if not r[2])
        self._save_history(history_path, history)
        self._log(f"全部任务结束：成功 {ok_n} / 失败 {fail_n} / 共 {total}。", "ok")

    def _download_one(self, url, idx, total, out_dir, cookies_path, auto_collection,
                      format_choice, proxy, cookie_header, history, history_path,
                      cookies_base_dir=None):
        """处理单个链接（含合集展开、动态 cookie、限流重试）。返回 (ok, err)。"""
        self._log(f"[{idx}/{total}] 处理: {url}", "info")
        if self._on_item:
            self._on_item(idx, total, url)

        host = urllib.parse.urlparse(url).netloc.lower()
        domain = ("." + host[4:]) if host.startswith("www.") else ("." + host if host else "")

        # 每条链接独立生成 opts（并发时避免共享字典冲突）；proxy 在此注入
        opts = self._base_opts(out_dir, cookies_path, format_choice)
        if proxy:
            opts["proxy"] = proxy

        # 按 URL 域名动态生成 Netscape cookie（让登录态在任意平台生效）
        # 优先用手动指定的 cookie 文件；否则按 URL 平台自动查找对应平台的 cookie
        ck = cookies_path
        if not (ck and os.path.isfile(ck)):
            ck = self.find_cookies_for(host, base_dir=cookies_base_dir)
        if ck and os.path.isfile(ck):
            pairs = self._read_cookie_pairs(ck)
            if pairs:
                tmpc = os.path.join(tempfile.gettempdir(), f"bili_cookie_{idx}.txt")
                try:
                    with open(tmpc, "w", encoding="utf-8") as f:
                        f.write("# Netscape HTTP Cookie File\n")
                        for n, v in pairs:
                            f.write(f"{domain}\tTRUE\t/\tFALSE\t0\t{n}\t{v}\n")
                    opts["cookiefile"] = tmpc
                except Exception:
                    pass

        # 合集自动展开：仅 B站 单集 -> 下载整集合集；其他平台走通用 playlist 检测
        resolved_url = url
        coll_title = None
        if auto_collection and "bilibili" in host:
            try:
                res = self._resolve_collection(url, cookie_header)
            except Exception as e:
                res = None
                self._log(f"  合集检测异常，按普通视频处理: {e}", "warn")
            if res:
                resolved_url, coll_title = res
                self._log(f"  -> 检测到合集《{coll_title}》，将自动下载全集", "info")

        try:
            is_pl, info = self._detect_playlist(resolved_url, opts)
        except Exception as e:
            self._log(f"  解析失败，跳过: {e}", "error")
            return False, str(e)

        if is_pl and info is not None:
            title = info.get("title") or coll_title or "合集"
            n = len(info.get("entries") or [])
            self._log(f"  -> 检测到合集/多P：《{title}》 共 {n} 个", "info")
            opts["outtmpl"] = {
                "default": os.path.join(
                    out_dir,
                    "%(playlist_title)s",
                    "%(playlist_index)02d - %(title)s [%(id)s].%(ext)s",
                )
            }
        elif coll_title:
            # 合集已展开但播放列表探测失败：仍按合集目录落盘
            self._log(f"  -> 按合集《{coll_title}》目录保存", "info")
            opts["outtmpl"] = {
                "default": os.path.join(
                    out_dir, _safe_name(coll_title),
                    "%(title)s [%(id)s].%(ext)s",
                )
            }
        else:
            opts["outtmpl"] = {
                "default": os.path.join(out_dir, "%(title)s [%(id)s].%(ext)s")
            }

        opts["progress_hooks"] = [self._make_hook(idx, total)]

        # 限流/403 类错误自动退避重试（其他错误直接失败）
        RETRY_KEYS = ("403", "429", "HTTP Error", "rate limit", "Rate Limit",
                      "Too Many Requests", "请求过于频繁", "频控", "Please try again later")
        max_retry = 3
        for attempt in range(1, max_retry + 1):
            try:
                with YoutubeDL(opts) as ydl:
                    ydl.download([resolved_url])
                self._log(f"  OK 完成 [{idx}/{total}]", "ok")
                if history is not None:
                    history.setdefault("done", [])
                    nu = self._norm_url(url)
                    if nu not in {self._norm_url(x) for x in history["done"]}:
                        history["done"].append(url)
                return True, None
            except StopDownload:
                self._log("用户取消下载。", "warn")
                raise
            except DownloadError as e:
                emsg = str(e)
                retryable = any(k in emsg for k in RETRY_KEYS)
                if retryable and attempt < max_retry and not self._should_stop():
                    wait = 2 ** attempt
                    self._log(f"  [限流/403] 第 {attempt}/{max_retry} 次失败，{wait}s 后重试...",
                              "warn")
                    time.sleep(wait)
                    continue
                self._log(f"  X 下载出错: {e}", "error")
                if history is not None:
                    history.setdefault("errors", []).append({"url": url, "err": emsg[:300]})
                return False, emsg
            except Exception as e:
                self._log(f"  X 未知错误: {e}", "error")
                if history is not None:
                    history.setdefault("errors", []).append({"url": url, "err": str(e)[:300]})
                return False, str(e)
        return False, "retries exhausted"


def _safe_name(s):
    """把合集标题转成安全的文件夹名。"""
    if not s:
        return "合集"
    bad = '/\\:*?"<>|'
    return "".join("_" if c in bad else c for c in s).strip() or "合集"
