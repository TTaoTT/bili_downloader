# -*- coding: utf-8 -*-
"""
bili_gui.pyw — B站视频下载器（图形界面）
双击运行（无需安装 Python；ffmpeg 可在界面内一键下载）。
支持：粘贴链接 / 从文件载入；合集与多P视频自动全下（粘贴单集也会下全集）；
Cookie 可粘贴字符串或放 cookies.txt 到同目录。
"""
import os
import sys
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

from bili_core import BiliDownloader  # noqa: E402


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("B站视频下载器")
        self.root.geometry("860x680")
        self.root.minsize(720, 560)

        self.downloader = BiliDownloader()
        self.worker = None
        self.running = False
        self.paused = False
        self.cookies_path = self.downloader.find_cookies(HERE)

        self.log_q = queue.Queue()
        self.prog_q = queue.Queue()

        self._build_ui()
        self._set_icon()
        self._start_tray()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_status()
        self._pump()

    # ---------------- UI ----------------
    def _build_ui(self):
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
        ttk.Label(header, text="B站视频下载器",
                  font=("Microsoft YaHei", 15, "bold"),
                  foreground="#FB7299").pack(side="left")

        # 状态栏
        status = ttk.Frame(self.root)
        status.pack(fill="x", padx=8, pady=(8, 0))
        self.cookie_var = tk.StringVar()
        self.ffmpeg_var = tk.StringVar()
        ttk.Label(status, text="Cookie:").pack(side="left")
        ttk.Label(status, textvariable=self.cookie_var, foreground="#1a7f37").pack(side="left", padx=(2, 12))
        ttk.Label(status, text="ffmpeg:").pack(side="left")
        ttk.Label(status, textvariable=self.ffmpeg_var, foreground="#1a7f37").pack(side="left", padx=(2, 4))
        self.ffmpeg_btn = ttk.Button(status, text="下载 ffmpeg", command=self._download_ffmpeg)
        self.ffmpeg_btn.pack(side="left")

        # Cookie 输入
        cookie_f = ttk.LabelFrame(self.root, text="登录 Cookie（粘贴字符串保存，或放 cookies.txt 到同目录）")
        cookie_f.pack(fill="x", padx=8, pady=(6, 0))
        self.cookie_text_var = tk.StringVar()
        ttk.Label(cookie_f, text="Cookie:").pack(side="left", padx=(2, 0))
        ttk.Entry(cookie_f, textvariable=self.cookie_text_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(cookie_f, text="保存 Cookie", command=self._save_cookie).pack(side="left")
        ttk.Button(cookie_f, text="清除", command=self._clear_cookie).pack(side="left", padx=2)
        ttk.Button(cookie_f, text="选择文件", command=self._select_cookie).pack(side="left", padx=2)
        ttk.Button(cookie_f, text="如何获取?", command=self._howto_cookie).pack(side="left", padx=2)

        # 输出目录
        out_f = ttk.Frame(self.root)
        out_f.pack(fill="x", padx=8, pady=(6, 0))
        ttk.Label(out_f, text="保存目录:").pack(side="left")
        self.out_var = tk.StringVar(value=os.path.join(HERE, "downloads"))
        ttk.Entry(out_f, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out_f, text="浏览", command=self._browse_out).pack(side="left")

        # 选项
        opt_f = ttk.Frame(self.root)
        opt_f.pack(fill="x", padx=8, pady=(4, 0))
        self.auto_coll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_f, text="自动下载合集/多P 全部（粘贴单集也下全集）",
                        variable=self.auto_coll_var).pack(side="left")

        # 链接输入
        link_f = ttk.LabelFrame(self.root, text="链接（每行一个；合集/多P 自动全下，粘贴单集也下全集）")
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
        self.start_btn = ttk.Button(act, text="开始下载", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(act, text="停止", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.pause_btn = ttk.Button(act, text="暂停", command=self._pause, state="disabled")
        self.pause_btn.pack(side="left", padx=6)
        ttk.Label(act, text="用法：粘贴/载入链接 → 开始。ffmpeg 缺失时点上方「下载 ffmpeg」；Cookie 可粘贴。",
                  foreground="#666666").pack(side="right")

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
            self._tray = pystray.Icon("bili_downloader", tray_img, "B站视频下载器", menu)
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
        self.cookie_var.set("已启用" if self.cookies_path else "未找到(匿名)")
        ffmpeg_ok = self.downloader.has_ffmpeg()
        self.ffmpeg_var.set("已安装" if ffmpeg_ok else "未安装")
        if hasattr(self, "ffmpeg_btn"):
            self.ffmpeg_btn.config(state="disabled" if ffmpeg_ok else "normal")

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
        import re
        urls = re.split(r"[\s,]+", text)
        urls = [u for u in urls if u.strip()]
        self.links.insert("end", "\n".join(urls) + "\n")
        self._log(f"已从文件载入 {len(urls)} 个链接。", "info")

    def _paste(self):
        try:
            text = self.root.clipboard_get()
        except Exception:
            text = ""
        if text:
            self.links.insert("end", text + "\n")

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
        lines = ["# Netscape HTTP Cookie File", "# bilibili.com cookies exported by B站下载器"]
        for p in parts:
            if "=" not in p:
                continue
            name, _, value = p.partition("=")
            name = name.strip()
            value = value.strip().strip(chr(34))
            lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}")
        return "\n".join(lines) + "\n"

    def _save_cookie(self):
        text = self.cookie_text_var.get().strip()
        if not text:
            messagebox.showwarning("空", "请先粘贴 Cookie 字符串。")
            return
        netscape = self._cookie_text_to_netscape(text)
        if not netscape:
            messagebox.showerror("无效", "无法解析 Cookie 内容。")
            return
        path = os.path.join(HERE, "cookies.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(netscape)
            self.cookies_path = path
            self._refresh_status()
            self._log("Cookie 已保存（同目录 cookies.txt），将用于登录态下载。", "ok")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _clear_cookie(self):
        self.cookie_text_var.set("")
        path = os.path.join(HERE, "cookies.txt")
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass
        self.cookies_path = None
        self._refresh_status()
        self._log("已清除 Cookie（删除同目录 cookies.txt），本次将匿名下载。", "info")

    def _howto_cookie(self):
        msg = (
            "如何获取 B站 Cookie（用于登录态 / 更高画质）：\n\n"
            "方法一（浏览器开发者工具，推荐）：\n"
            "1. 用 Chrome / Edge 登录 bilibili.com\n"
            "2. 按 F12 打开开发者工具 -> Network（网络）标签\n"
            "3. 刷新页面，在请求列表里点任意一个 bilibili.com 的请求\n"
            "4. 在 Headers（标头）里找到 Request Headers 的 \"Cookie:\" 一行\n"
            "5. 复制整行 Cookie 的值（形如 SESSDATA=xxx; bili_jct=yyy; ...）\n"
            "6. 回到本程序，粘贴到上方输入框，点「保存 Cookie」\n\n"
            "方法二（扩展导出 Netscape 格式）：\n"
            "安装 Cookie-Editor 等扩展 -> 访问 B站 -> 导出为 Netscape 格式\n"
            "-> 把内容粘贴保存（或直接存成 cookies.txt 放本程序同目录）\n\n"
            "注意：SESSDATA 是登录凭证，请勿泄露给他人。"
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
            messagebox.showwarning("没有链接", "请先粘贴或载入 B站链接。")
            return
        out_dir = self.out_var.get().strip() or os.path.join(HERE, "downloads")
        cookies = self.cookies_path
        self.running = True
        self.paused = False
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.pause_btn.config(state="normal", text="暂停")
        self.overall["value"] = 0
        self.worker = threading.Thread(
            target=self._run, args=(urls, out_dir, cookies), daemon=True)
        self.worker.start()

    def _run(self, urls, out_dir, cookies):
        try:
            self.downloader.download(
                urls, out_dir, cookies_path=cookies,
                auto_collection=self.auto_coll_var.get(),
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


def main():
    # Windows 任务栏分组：用本程序图标而非 pythonw 默认图标
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "com.ttao.bilidownloader.app.1")
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
