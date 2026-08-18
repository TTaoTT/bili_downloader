# 视频下载器（多平台 / Video Downloader）

![Logo](assets/logo.png)

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的多平台视频下载工具，支持 B站、抖音、小红书、TikTok 等主流站点，提供图形界面（GUI）与命令行（CLI）两种使用方式。

## 功能特性
- **多平台支持**：B站、抖音、小红书、TikTok、微博、AcFun 等（取决于 yt-dlp 提取器）
- **自动识别合集 / 多P**：粘贴一个视频链接，自动下载全集或整个播放列表
- **双击即用（exe）**：可打包为单文件 exe，免 Python 环境
- **分平台 Cookie**：按平台分别保存（`cookies/douyin.txt`、`cookies/bilibili.txt` …），互不污染，下载时按链接域名自动选用
- **抖音链接智能转换**：精选页 `jingxuan?modal_id=`、图文 `note/`、发现页 `discover?modal_id=` 等非常规链接自动转为标准视频链接
- **版本与更新提示**：状态栏显示程序版本与 yt-dlp 版本；支持「检查程序更新」与一键「更新 yt-dlp」
- **明暗双主题**：内置浅色 / 深色两套主题，深色下界面元素统一配色（含进度条、输入框）
- **ffmpeg 一键下载**：缺失时可在界面内直接获取便携版
- **单元测试**：`tests/` 下 13 项单测保障核心逻辑

## 快速开始

### 方式一：源码运行（需 Python）
1. 安装依赖：`python -m pip install -r requirements.txt`
2. 运行界面：双击 `bili_gui.pyw`，或 `python bili_gui.pyw`
3. 命令行：`python bili_cli.py links.txt`（`links.txt` 每行一个链接；也可参考 `links_example.txt`）
4. 粘贴链接（每行一个）→ 选画质 → 点「开始下载」

### 方式二：直接下载 exe（推荐）
从 [Releases](https://github.com/TTaoTT/bili_downloader/releases) 下载 `bili_downloader.exe` 双击即用；或自行打包（见下文）。首次启动会有约 1 秒的粉色启动图，随后主界面居中弹出。

## Cookie 配置（重要）
多数平台（尤其抖音）对匿名请求限流严格，建议配置 Cookie 以获得稳定下载与更高画质。

**获取方式（以抖音为例，需 fresh cookie）**：
1. 用 Chrome / Edge 打开 https://www.douyin.com（**无需登录**，访问即下发 `ttwid`）
2. 按 F12 → Network（网络）→ 刷新页面 → 点任意请求 → Request Headers 里的 `Cookie:` 整行
3. 复制该值（**必须包含 `ttwid=...`**）
4. 程序中：平台下拉选「抖音」→ 粘贴 → 点「保存 Cookie」→ 存为 `cookies/douyin.txt`

程序会按链接域名自动选用对应平台的 Cookie 文件；通用 `cookies.txt`（同目录）仍作兜底。
更详细的 B站 / 抖音 / 小红书 多平台教程见界面内「如何获取 Cookie」按钮。

> 注意：抖音要求「新鲜」cookie，换 IP 或隔太久可能失效，报错 `Fresh cookies are needed` 时重新获取一次即可。

## 常用站点与链接格式
- **B站**：`https://www.bilibili.com/video/BVxxxx` 或 `https://space.bilibili.com/uid/channel/series` 等
- **抖音**：标准 `https://www.douyin.com/video/xxx`，或分享短链 `https://v.douyin.com/xxxx/`；从 App 复制的精选页 `/jingxuan?modal_id=` 链接会被自动转换
- **小红书 / TikTok**：直接粘贴视频页链接即可

## 打包 exe
运行 `build_exe.bat`（需 **标准 CPython 3.10 或 3.11**，**不要用 Anaconda**——其 `_ctypes` 会导致打包后运行报加载失败）。产物在 `dist/bili_downloader.exe`。

如需手动打包，关键参数为：`--onefile --windowed --icon assets/icon.ico --splash assets/splash.png --add-data "assets;assets" --collect-all yt_dlp --collect-all pystray`。

## 文件说明
- `bili_core.py`    下载核心逻辑（GUI / CLI 共用）
- `bili_gui.pyw`    Tkinter 图形界面
- `bili_cli.py`     命令行入口
- `tests/`          单元测试（`python tests/test_bili_core.py` 运行）
- `install.bat`     Windows 依赖安装
- `git_submit.bat`  本地提交辅助脚本
- `build_exe.bat`   打包单文件 exe
- `requirements.txt` 依赖清单
- `links_example.txt` 示例链接
- `assets/`         图标与启动图（`icon.ico` / `logo.png` / `logo_64.png` / `splash.png` / `logo.svg`）

## 图标与主题
应用图标（窗口标题栏 / 任务栏 / exe 文件 / 系统托盘）统一位于 `assets/`，主题色为 B站粉 `#FB7299`，由生成脚本程序化绘制（需 Pillow）。启动图 `assets/splash.png` 在 exe 启动时显示，启动后自动关闭。

## 已知限制
- 暂停 / 停止不覆盖 ffmpeg 合并阶段（yt-dlp 架构限制），于下一分P 生效
- Windows 下 ttk 下拉框弹层为系统原生控件，深色模式下仍为浅色（框架限制）
- 快手等少数平台 yt-dlp 暂未提供稳定提取器，界面内仅作占位提示

## 免责声明
下载内容版权归原作者所有，请遵守各平台及当地法律法规，仅用于个人学习研究。
