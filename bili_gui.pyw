# -*- coding: utf-8 -*-
"""
bili_gui.pyw — B站视频下载器（图形界面）
双击运行（无需安装 Python；ffmpeg 可在界面内一键下载）。
支持：粘贴链接 / 从文件载入；合集与多P视频自动全下（粘贴单集也会下全集）；
Cookie 可粘贴字符串或放 cookies.txt 到同目录。
"""
import os
import sys
import json
import queue
import threading

# 打包成 exe 后，需显式指定 Tcl/Tk 库路径（打包时把 tcl8.6/tk8.6 一并打进了 _MEIPASS）
if getattr(sys, "frozen", False):
    _base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ.setdefault("TCL_LIBRARY", os.path.join(_base, "tcl8.6"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(_base, "tk8.6"))

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

# 打包成 exe 后 __file__ 指向临时解压目录，这里统一用「exe 所在目录」作为基准
if getattr(sys, "frozen", False):
    HERE = os.path.dirname(sys.executable)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

APP_VERSION = "1.0.0"  # 程序版本（用于更新检查，对比 GitHub release tag；升级时手动改这里）

# 让用户通过「更新 yt-dlp」下载的更新包（yt_dlp_vendor）优先于打包内置版本：
# 插入 sys.path 并把标准路径查找器前置到 PyInstaller 冻结导入器之前。
_vendor = os.path.join(HERE, "yt_dlp_vendor")
if os.path.isdir(os.path.join(_vendor, "yt_dlp")):
    sys.path.insert(0, _vendor)
    _frozen = [f for f in sys.meta_path if "Frozen" in type(f).__name__]
    _others = [f for f in sys.meta_path if "Frozen" not in type(f).__name__]
    sys.meta_path = _others + _frozen

from bili_core import BiliDownloader  # noqa: E402


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("视频下载器")
        self.root.geometry("860x680")
        self.root.minsize(720, 560)

        self.downloader = BiliDownloader()
        self.worker = None
        self.running = False
        self.paused = False
        self._updating = False
        self.platform_var = tk.StringVar(value="")
        self.cookies_path = None  # 默认自动按平台查找；手动「选择文件」时再赋值
        self.config = self._load_config()
        self.history_path = os.path.join(HERE, "download_history.json")

        self.log_q = queue.Queue()
        self.prog_q = queue.Queue()

        self._build_ui()
        self._apply_theme()
        self._set_icon()
        self._start_tray()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_status()
        self._pump()
        threading.Thread(target=self._bg_check_updates, daemon=True).start()

    # ---------------- UI ----------------
    def _build_ui(self):
        # 主操作按钮强调样式（B站粉），需在创建按钮前注册
        try:
            style = ttk.Style()
            style.configure("Accent.TButton", font=("Microsoft YaHei", 10, "bold"),
                            padding=(14, 6))
            style.map("Accent.TButton",
                      foreground=[("disabled", "#ffffff")],
                      background=[("active", "#fc8bab"), ("disabled", "#f3b9c9")])
        except Exception:
            pass

        # 顶部标题（含 logo）
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=8, pady=(8, 0))
        try:
            logo_p = os.path.join(self._assets_dir(), "logo_64.png")
            if os.path.isfile(logo_p):
                self._logo_img = tk.PhotoImage(file=logo_p)
                ttk.Label(header, image=self._logo_img).pack(side="left", padx=(0, 8))
        except Exception:
            pass
        ttk.Label(header, text="视频下载器",
                  font=("Microsoft YaHei", 15, "bold"),
                  foreground="#FB7299").pack(side="left")
        ttk.Label(header, text="B站 · 抖音 · 小红书 等多平台视频下载",
                  font=("Microsoft YaHei", 9),
                  foreground="#8a919f").pack(side="left", padx=(8, 0))

        # 标题分隔线
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=8, pady=(8, 0))

        # 状态栏（版本信息 + 操作按钮）
        status = ttk.Frame(self.root)
        status.pack(fill="x", padx=8, pady=(8, 0))
        self.cookie_var = tk.StringVar()
        self.ffmpeg_var = tk.StringVar()
        self.app_ver_var = tk.StringVar(value=f"程序 v{APP_VERSION}")
        self.ytdlp_ver_var = tk.StringVar(value="yt-dlp: 检测中…")
        # 第一行：版本 / 状态信息
        info = ttk.Frame(status)
        info.pack(fill="x")
        ttk.Label(info, textvariable=self.app_ver_var).pack(side="left", padx=(0, 10))
        ttk.Label(info, textvariable=self.ytdlp_ver_var).pack(side="left", padx=(0, 10))
        ttk.Label(info, text="Cookie:").pack(side="left")
        ttk.Label(info, textvariable=self.cookie_var, foreground="#1a7f37").pack(side="left", padx=(2, 10))
        ttk.Label(info, text="ffmpeg:").pack(side="left")
        ttk.Label(info, textvariable=self.ffmpeg_var, foreground="#1a7f37").pack(side="left", padx=(2, 4))
        # 第二行：操作按钮
        btns = ttk.Frame(status)
        btns.pack(fill="x", pady=(4, 0))
        self.ffmpeg_btn = ttk.Button(btns, text="下载 ffmpeg", command=self._download_ffmpeg)
        self.ffmpeg_btn.pack(side="left")
        self.update_btn = ttk.Button(btns, text="更新 yt-dlp", command=self._update_ytdlp)
        self.update_btn.pack(side="left", padx=(6, 0))
        self.app_update_btn = ttk.Button(btns, text="检查程序更新", command=self._check_app_update)
        self.app_update_btn.pack(side="left", padx=(6, 0))

        # Cookie 输入（按平台分别保存）
        cookie_f = ttk.LabelFrame(self.root, text="平台 Cookie（按平台分别保存，下载时自动取用；也可放通用 cookies.txt 到同目录）")
        cookie_f.pack(fill="x", padx=8, pady=(6, 0))
        self.cookie_text_var = tk.StringVar()
        plat_values = list(self.PLAT_CN2KEY.keys())
        self.cookie_platform_var = tk.StringVar(value="自动")
        # 第一行：输入框 + 平台下拉
        row1 = ttk.Frame(cookie_f)
        row1.pack(fill="x", padx=4, pady=(2, 2))
        ttk.Label(row1, text="Cookie:").pack(side="left", padx=(2, 0))
        ttk.Entry(row1, textvariable=self.cookie_text_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(row1, text="平台:").pack(side="left", padx=(4, 0))
        ttk.Combobox(row1, textvariable=self.cookie_platform_var, values=plat_values,
                     state="readonly", width=10).pack(side="left", padx=2)
        # 第二行：操作按钮
        row2 = ttk.Frame(cookie_f)
        row2.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(row2, text="保存 Cookie", command=self._save_cookie).pack(side="left")
        ttk.Button(row2, text="清除", command=self._clear_cookie).pack(side="left", padx=2)
        ttk.Button(row2, text="选择文件", command=self._select_cookie).pack(side="left", padx=2)
        ttk.Button(row2, text="如何获取?", command=self._howto_cookie).pack(side="left", padx=2)

        # 输出目录
        out_f = ttk.Frame(self.root)
        out_f.pack(fill="x", padx=8, pady=(6, 0))
        ttk.Label(out_f, text="保存目录:").pack(side="left")
        self.out_var = tk.StringVar(value=self.config.get("out_dir", os.path.join(HERE, "downloads")))
        ttk.Entry(out_f, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out_f, text="浏览", command=self._browse_out).pack(side="left")

        # 下载选项（分组）
        opt_lf = ttk.LabelFrame(self.root, text="下载选项")
        opt_lf.pack(fill="x", padx=8, pady=(4, 0))
        opt_f = ttk.Frame(opt_lf)
        opt_f.pack(fill="x", padx=4, pady=4)
        self.auto_coll_var = tk.BooleanVar(value=self.config.get("auto_collection", True))
        ttk.Checkbutton(opt_f, text="自动下载合集/多P 全部（粘贴单集也下全集）",
                        variable=self.auto_coll_var).pack(side="left")
        ttk.Label(opt_f, text="  画质:").pack(side="left")
        self.fmt_var = tk.StringVar(value=self.config.get("format", "最高画质"))
        self.fmt_cb = ttk.Combobox(opt_f, textvariable=self.fmt_var, width=12,
                                   values=["最高画质", "1080p", "720p", "仅音频(mp3)"],
                                   state="readonly")
        self.fmt_cb.pack(side="left", padx=(2, 0))

        adv_f = ttk.Frame(opt_lf)
        adv_f.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Label(adv_f, text="并发数:").pack(side="left")
        self.workers_var = tk.IntVar(value=self.config.get("max_workers", 2))
        self.workers_sp = ttk.Spinbox(adv_f, from_=1, to=6, width=4,
                                      textvariable=self.workers_var, state="readonly")
        self.workers_sp.pack(side="left", padx=(2, 0))
        ttk.Label(adv_f, text="(同站建议≤2，避免风控)").pack(side="left")
        ttk.Label(adv_f, text="  代理:").pack(side="left")
        self.proxy_var = tk.StringVar(value=self.config.get("proxy", ""))
        ttk.Entry(adv_f, textvariable=self.proxy_var, width=26).pack(side="left", padx=2)
        ttk.Label(adv_f, text="如 socks5://127.0.0.1:7890", foreground="#8a919f").pack(side="left")

        # 平台识别提示
        plat_f = ttk.Frame(self.root)
        plat_f.pack(fill="x", padx=8, pady=(0, 0))
        ttk.Label(plat_f, textvariable=self.platform_var, foreground="#FB7299").pack(side="left")

        # 链接输入
        link_f = ttk.LabelFrame(self.root, text="链接（每行一个；支持 B站/抖音/小红书/TikTok/微博/AcFun 等 yt-dlp 支持的平台；合集/多P 自动全下）")
        link_f.pack(fill="both", expand=True, padx=8, pady=(6, 0))
        self.links = scrolledtext.ScrolledText(link_f, height=8, wrap="word")
        self.links.pack(fill="both", expand=True, padx=4, pady=4)
        btn_f = ttk.Frame(link_f)
        btn_f.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(btn_f, text="从文件载入", command=self._load_file).pack(side="left")
        ttk.Button(btn_f, text="粘贴", command=self._paste).pack(side="left", padx=4)
        ttk.Button(btn_f, text="清空", command=lambda: self.links.delete("1.0", "end")).pack(side="left")

        # 进度
        prog_f = ttk.Frame(self.root)
        prog_f.pack(fill="x", padx=8, pady=(6, 0))
        self.overall = ttk.Progressbar(prog_f, maximum=100, mode="determinate")
        self.overall.pack(fill="x", side="left", expand=True, padx=(0, 8))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(prog_f, textvariable=self.status_var, width=42, anchor="w").pack(side="left")

        # 日志
        log_f = ttk.LabelFrame(self.root, text="日志")
        log_f.pack(fill="both", expand=True, padx=8, pady=(6, 0))
        log_bar = ttk.Frame(log_f)
        log_bar.pack(fill="x", padx=4, pady=(2, 0))
        self.dark_var = tk.BooleanVar(value=self.config.get("dark", False))
        ttk.Checkbutton(log_bar, text="暗色主题", variable=self.dark_var,
                        command=self._apply_theme).pack(side="left")
        ttk.Button(log_bar, text="导出日志", command=self._export_log).pack(side="right")
        self.log = scrolledtext.ScrolledText(log_f, height=10, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)
        self.log.tag_config("info", foreground="#333333")
        self.log.tag_config("ok", foreground="#1a7f37")
        self.log.tag_config("warn", foreground="#b58100")
        self.log.tag_config("error", foreground="#c0392b")
        self.log.tag_config("debug", foreground="#888888")

        # 操作按钮
        act = ttk.Frame(self.root)
        act.pack(fill="x", padx=8, pady=(6, 8))
        self.start_btn = ttk.Button(act, text="开始下载", command=self._start,
                                 style="Accent.TButton")
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(act, text="停止", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.pause_btn = ttk.Button(act, text="暂停", command=self._pause, state="disabled")
        self.pause_btn.pack(side="left", padx=6)
        ttk.Label(act, text="用法：粘贴/载入链接 → 开始。ffmpeg 缺失时点上方「下载 ffmpeg」；Cookie 可粘贴。",
                  foreground="#8a919f").pack(side="right")

    # ---------------- 图标 / 任务栏 / 托盘 ----------------
    def _assets_dir(self):
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            base = HERE
        return os.path.join(base, "assets")

    def _set_icon(self):
        ad = self._assets_dir()
        ico = os.path.join(ad, "icon.ico")
        png = os.path.join(ad, "logo.png")
        try:
            if os.path.isfile(ico):
                self.root.wm_iconbitmap(ico)   # Windows 标题栏 + 任务栏
                return
        except Exception:
            pass
        try:
            if os.path.isfile(png):
                img = tk.PhotoImage(file=png)
                self.root.wm_iconphoto(True, img)
                self._iconphoto_img = img
        except Exception:
            pass

    def _start_tray(self):
        # 任务栏通知区托盘图标（可选；pystray 缺失则跳过，不影响主程序）
        self._tray = None
        try:
            import pystray
            from PIL import Image as _PILImage
        except Exception:
            return
        png = os.path.join(self._assets_dir(), "logo.png")
        if not os.path.isfile(png):
            return
        try:
            tray_img = _PILImage.open(png)
            menu = pystray.Menu(
                pystray.MenuItem("显示窗口", self._tray_show),
                pystray.MenuItem("退出", self._tray_quit),
            )
            self._tray = pystray.Icon("bili_downloader", tray_img, "视频下载器", menu)
            threading.Thread(target=self._tray.run, daemon=True).start()
        except Exception:
            self._tray = None

    def _on_close(self):
        # 有托盘时：点 X 最小化到托盘（不退出）；无托盘则直接退出
        if self._tray is not None:
            self.root.withdraw()
        else:
            self.root.destroy()

    def _tray_show(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)

    def _tray_quit(self, icon=None, item=None):
        try:
            if self._tray is not None:
                self._tray.stop()
        except Exception:
            pass
        self.root.after(0, self.root.destroy)

    def _refresh_status(self):
        self._refresh_cookie_status()
        ffmpeg_ok = self.downloader.has_ffmpeg()
        self.ffmpeg_var.set("已安装" if ffmpeg_ok else "未安装")
        if hasattr(self, "ffmpeg_btn"):
            self.ffmpeg_btn.config(state="disabled" if ffmpeg_ok else "normal")

    def _refresh_cookie_status(self):
        """扫描 cookies/ 与各平台文件 + 通用 cookies.txt，显示已配置平台。"""
        configured = []
        d = os.path.join(HERE, "cookies")
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".txt"):
                    configured.append(f[:-4])
        if os.path.isfile(os.path.join(HERE, "cookies.txt")):
            configured.append("通用")
        if configured:
            self.cookie_var.set("已配置: " + "、".join(configured))
        else:
            self.cookie_var.set("未配置(匿名)")

    # ---------------- 配置 / 主题 / 日志 ----------------
    def _config_path(self):
        return os.path.join(HERE, "config.json")

    def _load_config(self):
        default = {
            "out_dir": os.path.join(HERE, "downloads"),
            "format": "最高画质",
            "proxy": "",
            "max_workers": 2,
            "auto_collection": True,
            "dark": False,
        }
        cfg = dict(default)
        try:
            p = self._config_path()
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for k in default:
                        if k in data:
                            cfg[k] = data[k]
        except Exception:
            pass
        return cfg

    def _save_config(self):
        try:
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _apply_theme(self):
        """高 DPI 已在 main() 设置；提供浅色 / 深色两套一致配色。"""
        style = ttk.Style()

        if self.dark_var.get():
            try:
                style.theme_use("clam")
            except Exception:
                pass
            bg, surface, field = "#1e1e24", "#26262e", "#16161a"
            fg, muted, border = "#e6e6e6", "#9a9aa5", "#3a3a44"
            accent, accent_text, success = "#FB7299", "#ffffff", "#4ecb71"
        else:
            try:
                style.theme_use("vista")   # 还原 Windows 原生外观
            except Exception:
                try:
                    style.theme_use("default")
                except Exception:
                    pass
            bg, surface, field = "#f5f6f8", "#ffffff", "#ffffff"
            fg, muted, border = "#1f2329", "#8a919f", "#e3e5e7"
            accent, accent_text, success = "#FB7299", "#ffffff", "#1a7f37"

        # 容器 / 文本
        style.configure(".", background=bg, foreground=fg)
        for opt in ("TFrame", "TLabel", "TLabelFrame", "TLabelFrame.Label",
                    "TCheckbutton", "TRadiobutton"):
            style.configure(opt, background=bg, foreground=fg)
        # 输入框（含下拉框）
        style.configure("TEntry", fieldbackground=field, foreground=fg, bordercolor=border)
        style.configure("TCombobox", fieldbackground=field, foreground=fg,
                        selectbackground=accent, selectforeground=accent_text,
                        background=field, bordercolor=border)
        style.configure("TSpinbox", fieldbackground=field, foreground=fg, bordercolor=border)
        # 普通按钮
        style.configure("TButton", background=surface, foreground=fg, bordercolor=border)
        style.map("TButton", background=[("active", field), ("disabled", bg)])
        # 主操作按钮配色（在 _build_ui 已注册布局/字体）
        style.configure("Accent.TButton", background=accent, foreground=accent_text,
                        bordercolor=accent)
        # 进度条（品牌粉）
        style.configure("Accent.Horizontal.TProgressbar",
                        troughcolor=border, background=accent, borderwidth=0)

        self.root.configure(bg=bg)

        # Text 控件（链接输入 + 日志）单独配置，避免深色下出现刺眼白框
        for tw in (getattr(self, "links", None), getattr(self, "log", None)):
            if tw:
                try:
                    tw.configure(bg=field, fg=fg, insertbackground=fg,
                                selectbackground=accent, selectforeground=accent_text,
                                relief="flat", borderwidth=1,
                                highlightbackground=border, highlightcolor=accent)
                except Exception:
                    pass
        if hasattr(self, "log"):
            self.log.tag_config("info", foreground=fg)
            self.log.tag_config("debug", foreground=muted)
            self.log.tag_config("ok", foreground=success)

        # 进度条控件套用强调样式
        if hasattr(self, "overall"):
            try:
                self.overall.configure(style="Accent.Horizontal.TProgressbar")
            except Exception:
                pass

    def _insert_urls(self, text):
        """拆分文本为链接列表并去重（列表内），插入到链接框；返回 (新增数, 跳过重复数)。"""
        import re
        raw = re.split(r"[\s,]+", text or "")
        urls = [u for u in raw if u.strip()]
        seen = set()
        uniq = []
        for u in urls:
            n = BiliDownloader._norm_url(u)
            if n not in seen:
                seen.add(n)
                uniq.append(u)
        if uniq:
            self.links.insert("end", "\n".join(uniq) + "\n")
        self._detect_platforms()
        return len(uniq), len(urls) - len(uniq)

    def _export_log(self):
        text = self.log.get("1.0", "end")
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile="download_log.txt")
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            self._log(f"日志已导出: {p}", "ok")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ---------------- 动作 ----------------
    def _browse_out(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get())
        if d:
            self.out_var.set(d)

    def _load_file(self):
        p = filedialog.askopenfilename(
            filetypes=[("文本文件", "*.txt *.csv *.url"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return
        n, dup = self._insert_urls(text)
        self._log(f"已从文件载入 {n} 个链接" +
                  (f"（跳过 {dup} 个重复）" if dup else "") + "。", "info")

    def _paste(self):
        try:
            text = self.root.clipboard_get()
        except Exception:
            text = ""
        if text:
            n, dup = self._insert_urls(text)
            if dup:
                self._log(f"粘贴：新增 {n} 个，跳过 {dup} 个重复。", "info")

    PLAT_CN2KEY = {
        "自动": "auto", "抖音": "douyin", "小红书": "xiaohongshu", "TikTok": "tiktok",
        "B站": "bilibili", "微博": "weibo", "AcFun": "acfun", "西瓜视频": "ixigua",
        "爱奇艺": "iqiyi", "优酷": "youku", "腾讯视频": "qq", "芒果TV": "mgtv",
        "知乎": "zhihu", "网易云音乐": "netease", "QQ音乐": "qq",
    }

    PLATFORM_HINTS = {
        "bilibili.com": "B站", "b23.tv": "B站",
        "douyin.com": "抖音", "tiktok.com": "TikTok",
        "xiaohongshu.com": "小红书", "xhslink.com": "小红书",
        "kuaishou.com": "快手(暂不支持)",
        "weibo.com": "微博", "acfun.cn": "AcFun",
        "ixigua.com": "西瓜视频", "iqiyi.com": "爱奇艺",
        "youku.com": "优酷", "v.qq.com": "腾讯视频", "mgtv.com": "芒果TV",
        "zhihu.com": "知乎", "douyu.com": "斗鱼", "huya.com": "虎牙",
        "music.163.com": "网易云音乐", "y.qq.com": "QQ音乐",
    }

    def _detect_platforms(self):
        """根据已粘贴链接识别平台，显示在提示行。"""
        text = self.links.get("1.0", "end").lower()
        found = []
        for key, name in self.PLATFORM_HINTS.items():
            if key in text:
                found.append(name)
        seen = set()
        uniq = []
        for n in found:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        self.platform_var.set("已识别平台：" + "、".join(uniq) if uniq else "")

    def _update_ytdlp(self):
        if self._updating:
            return
        self._updating = True
        self.update_btn.config(state="disabled")
        self._log("开始更新 yt-dlp ...", "info")

        def work():
            try:
                ok, msg = self.downloader.update_ytdlp(self._log, HERE)
                self._log(("更新成功: " if ok else "更新失败: ") + msg,
                          "ok" if ok else "error")
                if ok:
                    cur = self.downloader.yt_dlp_version()
                    self.root.after(0, lambda: self.ytdlp_ver_var.set(
                        f"yt-dlp: {cur or '?'} ✓最新（重启生效）"))
                    self.root.after(0, lambda: self.update_btn.config(text="更新 yt-dlp"))
            except Exception as e:
                self._log(f"更新异常: {e}", "error")
            finally:
                self._updating = False
                self.log_q.put(("__update_done__", "info"))

        threading.Thread(target=work, daemon=True).start()

    def _bg_check_updates(self):
        """启动时后台检查 yt-dlp 最新版本与程序更新，更新状态栏/提示（不阻塞 UI）。"""
        try:
            cur, latest, has = self.downloader.ytdlp_update_available()
            if has is True:
                self.root.after(0, lambda: self.ytdlp_ver_var.set(
                    f"yt-dlp: {cur} → 有更新 {latest}"))
                self.root.after(0, lambda: self.update_btn.config(
                    text=f"更新 yt-dlp ({latest})"))
            elif has is False:
                self.root.after(0, lambda: self.ytdlp_ver_var.set(
                    f"yt-dlp: {cur} ✓最新"))
            else:
                self.root.after(0, lambda: self.ytdlp_ver_var.set(
                    f"yt-dlp: {cur or '?'}（无法检查更新）"))
            tag, url = self.downloader.check_app_update()
            if tag and self._app_has_update(tag):
                self.root.after(0, lambda: self._notify_app_update(tag, url))
        except Exception:
            pass

    @staticmethod
    def _app_has_update(latest_tag):
        """简单版本比较：去掉 v 前缀后字符串不同即视为有更新。"""
        def norm(v):
            return (v or "").lstrip("vV").strip()
        return norm(latest_tag) != norm(APP_VERSION)

    def _notify_app_update(self, tag, url):
        msg = f"发现新版本 {tag}！\n\n当前版本：v{APP_VERSION}\n"
        if url:
            msg += f"下载地址：{url}\n\n（exe 无法自动更新，请前往下载最新版并覆盖本程序）"
        else:
            msg += "请前往 GitHub 仓库下载最新版并覆盖本程序。"
        messagebox.showinfo("程序更新可用", msg)

    def _check_app_update(self):
        if self.app_update_btn["state"] == "disabled":
            return
        self.app_update_btn.config(state="disabled")
        self._log("正在检查程序更新 ...", "info")

        def work():
            try:
                tag, url = self.downloader.check_app_update()
                if not tag:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "程序更新", "检查失败，或未发布任何 release（GitHub 暂无可用版本）。"))
                elif self._app_has_update(tag):
                    self.root.after(0, lambda: self._notify_app_update(tag, url))
                else:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "程序更新", f"已是最新版本：v{APP_VERSION}"))
            finally:
                self.root.after(0, lambda: self.app_update_btn.config(state="normal"))

        threading.Thread(target=work, daemon=True).start()

    def _select_cookie(self):
        p = filedialog.askopenfilename(filetypes=[("Cookie 文件", "*.txt"), ("所有文件", "*.*")])
        if p:
            self.cookies_path = p
            self._refresh_status()
            self._log(f"已选择 Cookie: {p}", "ok")

    def _cookie_text_to_netscape(self, text):
        text = (text or "").strip()
        if not text:
            return None
        if text.startswith("# Netscape") or "\t" in text:
            return text
        parts = [p.strip() for p in text.split(";") if p.strip()]
        lines = ["# Netscape HTTP Cookie File", "# cookies exported by 视频下载器（按平台分别保存）"]
        for p in parts:
            if "=" not in p:
                continue
            name, _, value = p.partition("=")
            name = name.strip()
            value = value.strip().strip(chr(34))
            lines.append(f".douyin.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
        return "\n".join(lines) + "\n"

    def _detect_first_platform_key(self):
        """从已粘贴链接里识别第一个平台 key（用于「自动」保存时定位文件）。"""
        text = self.links.get("1.0", "end").lower()
        for dom, key in BiliDownloader.DOMAIN_TO_PLATFORM.items():
            if dom in text:
                return key
        return None

    def _cookie_path_for(self, plat_cn):
        """根据下拉选中的平台中文名，返回要保存/清除的 cookie 文件路径。"""
        plat = self.PLAT_CN2KEY.get(plat_cn, "auto")
        if plat == "auto":
            plat = self._detect_first_platform_key() or "common"
        if plat == "common":
            return os.path.join(HERE, "cookies.txt")
        d = os.path.join(HERE, "cookies")
        return os.path.join(d, f"{plat}.txt")

    def _save_cookie(self):
        text = self.cookie_text_var.get().strip()
        if not text:
            messagebox.showwarning("空", "请先粘贴 Cookie 字符串。")
            return
        netscape = self._cookie_text_to_netscape(text)
        if not netscape:
            messagebox.showerror("无效", "无法解析 Cookie 内容。")
            return
        plat_cn = self.cookie_platform_var.get()
        path = self._cookie_path_for(plat_cn)
        try:
            if path.endswith(os.path.join("cookies", "x")) or os.path.dirname(path).endswith("cookies"):
                os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(netscape)
            # 注意：保存后不锁定 self.cookies_path，保持下载时按链接平台自动选
            self._refresh_status()
            self._log(f"Cookie 已保存到：{path}（下载对应平台时自动取用）。", "ok")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _clear_cookie(self):
        self.cookie_text_var.set("")
        plat_cn = self.cookie_platform_var.get()
        path = self._cookie_path_for(plat_cn)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass
        self.cookies_path = None
        self._refresh_status()
        self._log(f"已清除「{plat_cn}」Cookie。", "info")

    def _howto_cookie(self):
        msg = (
            "如何获取平台 Cookie（用于登录态 / 更高画质 / 绕过限流）：\n\n"
            "原理：大多数平台（尤其抖音）现在要求请求带 Cookie，否则会拒绝下载。\n"
            "本程序按平台分别保存 Cookie（如 cookies/douyin.txt、cookies/bilibili.txt），"
            "下载对应平台时自动取用，互不污染。\n\n"
            "通用步骤（以 Chrome / Edge 为例）：\n"
            "1. 浏览器访问对应平台网站（douyin.com / bilibili.com / xiaohongshu.com ...）\n"
            "   —— 抖音无需登录，访问即自动下发 ttwid Cookie\n"
            "2. 按 F12 打开开发者工具 -> Network（网络）标签，刷新页面\n"
            "3. 在请求列表点任意一个该网站的请求\n"
            "4. 在 Headers（标头）里找到 Request Headers 的 \"Cookie:\" 一行，复制整行值\n"
            "   （形如 ttwid=xxx; msToken=yyy; ... 或 SESSDATA=xxx; bili_jct=yyy; ...）\n"
            "5. 回到本程序：上方「平台」下拉选对应平台（或选「自动」按链接识别）\n"
            "6. 粘贴 Cookie 到输入框，点「保存 Cookie」\n\n"
            "也可用扩展：安装 Cookie-Editor -> 访问平台 -> 导出 Netscape 格式 -> 粘贴保存，\n"
            "或直接把内容存成对应文件放本程序同目录的 cookies/ 子目录。\n\n"
            "注意：Cookie 含登录凭证，请勿泄露；抖音 Cookie 有时效，失效请重新获取。"
        )
        messagebox.showinfo("如何获取 Cookie", msg)

    def _download_ffmpeg(self):
        if self.downloader.has_ffmpeg():
            self._log("ffmpeg 已安装。", "info")
            return
        self.ffmpeg_btn.config(state="disabled")
        self._log("开始下载 ffmpeg（便携版，约几十 MB）...", "info")

        def work():
            try:
                p = self.downloader._ensure_ffmpeg(self._log)
                if p:
                    self._log("ffmpeg 安装完成，已可下载最高画质。", "ok")
                else:
                    self._log("ffmpeg 下载失败，可手动放置 ffmpeg.exe 到 tools/ffmpeg/bin。", "warn")
            except Exception as e:
                self._log(f"ffmpeg 下载异常: {e}", "warn")
            finally:
                self.log_q.put(("__ffmpeg_done__", "info"))

        threading.Thread(target=work, daemon=True).start()

    def _start(self):
        if self.running:
            return
        urls = [u.strip() for u in self.links.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning("没有链接", "请先粘贴或载入视频链接。")
            return
        out_dir = self.out_var.get().strip() or os.path.join(HERE, "downloads")
        cookies = self.cookies_path
        fmt_choice = {"最高画质": "best", "1080p": "1080p", "720p": "720p",
                      "仅音频(mp3)": "audio"}.get(self.fmt_var.get(), "best")
        proxy = (self.proxy_var.get() or "").strip()
        try:
            workers = int(self.workers_var.get())
        except Exception:
            workers = 1
        workers = max(1, min(workers, 6))
        if fmt_choice == "audio" and not self.downloader.has_ffmpeg():
            messagebox.showwarning("需要 ffmpeg",
                                   "「仅音频(mp3)」需要 ffmpeg 才能提取音频，请先点击「下载 ffmpeg」。")
            return
        # 持久化配置
        self.config.update({
            "out_dir": out_dir,
            "format": self.fmt_var.get(),
            "proxy": proxy,
            "max_workers": workers,
            "auto_collection": self.auto_coll_var.get(),
            "dark": self.dark_var.get(),
        })
        self._save_config()
        self._detect_platforms()
        self.running = True
        self.paused = False
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.pause_btn.config(state="normal", text="暂停")
        self.overall["value"] = 0
        self.worker = threading.Thread(
            target=self._run, args=(urls, out_dir, cookies, fmt_choice, proxy, workers),
            daemon=True)
        self.worker.start()

    def _run(self, urls, out_dir, cookies, format_choice="best", proxy=None, max_workers=1):
        try:
            self.downloader.download(
                urls, out_dir, cookies_path=cookies,
                cookies_base_dir=HERE,
                auto_collection=self.auto_coll_var.get(),
                format_choice=format_choice,
                proxy=proxy or None,
                max_workers=max_workers,
                history_path=self.history_path,
                on_log=self._log,
                on_progress=self._on_progress,
                on_item=self._on_item,
            )
        except Exception as e:
            self._log(f"运行异常: {e}", "error")
        finally:
            self.running = False
            self.log_q.put(("__done__", "info"))

    def _stop(self):
        if self.downloader:
            self.downloader.request_stop()
            self.paused = False
            self.pause_btn.config(state="disabled", text="暂停")
            self._log("正在停止……（当前分P完成后中止）", "warn")

    def _pause(self):
        if not self.running:
            return
        if not self.paused:
            self.downloader.request_pause()
            self.paused = True
            self.pause_btn.config(text="继续")
            self.status_var.set("已暂停")
        else:
            self.downloader.request_resume()
            self.paused = False
            self.pause_btn.config(text="暂停")

    # ---------------- 回调（来自下载线程）----------------
    def _log(self, msg, level="info"):
        self.log_q.put((msg, level))

    def _on_progress(self, d):
        self.prog_q.put(d)

    def _on_item(self, idx, total, url):
        self.log_q.put((f"-- 项目 {idx}/{total} --", "debug"))

    # ---------------- UI 更新 ----------------
    def _pump(self):
        # 日志
        try:
            while True:
                msg, level = self.log_q.get_nowait()
                if msg == "__done__":
                    self._finish()
                    continue
                if msg == "__ffmpeg_done__":
                    self._refresh_status()
                    continue
                if msg == "__update_done__":
                    self.update_btn.config(state="normal")
                    self._refresh_status()
                    continue
                self.log.config(state="normal")
                self.log.insert("end", msg + "\n", level)
                self.log.config(state="disabled")
                self.log.see("end")
        except queue.Empty:
            pass

        # 进度
        try:
            while True:
                d = self.prog_q.get_nowait()
                self._apply_progress(d)
        except queue.Empty:
            pass

        self.root.after(80, self._pump)

    def _apply_progress(self, d):
        idx = d.get("_item_index", 1)
        total = d.get("_item_total", 1)
        st = d.get("status")
        if st == "downloading":
            total_b = d.get("total_bytes") or d.get("total_bytes_estimate")
            down_b = d.get("downloaded_bytes", 0)
            pct = (down_b / total_b * 100) if total_b else 0
            fname = os.path.basename(d.get("filename", ""))
            self.status_var.set(f"[{idx}/{total}] {pct:.0f}%  {fname}")
            overall_pct = ((idx - 1) + (pct / 100)) / total * 100
            self.overall["value"] = min(overall_pct, 100)
        elif st == "finished":
            self.status_var.set(f"[{idx}/{total}] 已完成: {os.path.basename(d.get('filename', ''))}")
            self.overall["value"] = idx / total * 100

    def _finish(self):
        self.running = False
        self.paused = False
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.pause_btn.config(state="disabled", text="暂停")
        self.status_var.set("就绪")
        self.overall["value"] = 100
        # 托盘完成通知（toast）
        if self._tray is not None:
            try:
                self._tray.notify("下载任务已完成", "视频下载器")
            except Exception:
                pass


def main():
    # 高 DPI 适配：需在创建任何窗口前设置，让 tkinter 按系统缩放清晰显示
    if sys.platform.startswith("win"):
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        # Windows 任务栏分组：用本程序图标而非 pythonw 默认图标
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "com.ttao.bilidownloader.app.1")
        except Exception:
            pass
    root = tk.Tk()
    # 先隐藏主窗口：避免与 splash 错位闪现，待构建完成并居中后再显示
    root.withdraw()
    App(root)

    # 精确居中主窗口，使其与 PyInstaller --splash（屏幕正中）对齐
    root.update_idletasks()
    w = root.winfo_reqwidth()
    h = root.winfo_reqheight()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # 关闭 PyInstaller --splash 启动图（官方 API，比 FindWindowW 可靠；
    # 非打包环境 import 失败则忽略）
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass

    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
