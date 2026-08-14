# B站视频下载器 (Bilibili Downloader)

基于 yt-dlp 的 B站视频下载工具，提供图形界面与命令行两种使用方式。

## 功能特性
- 支持单视频 / 多P视频 / 合集 / 收藏夹 / 频道，粘贴一个链接自动下载全集，无需逐个输入
- 图形界面 bili_gui.pyw 与命令行 bili_cli.py 两套入口
- 支持暂停 / 继续 / 停止
- 登录 Cookie：界面粘贴字符串或放置 cookies.txt 到同目录，登录态更高画质
- ffmpeg 缺失时可在界面一键下载便携版
- 可打包为单文件 exe（见 build_exe.bat）

## 快速开始（源码）
1. 安装依赖：python -m pip install -r requirements.txt
2. 运行界面：双击 bili_gui.pyw，或命令行 python bili_cli.py links.txt
3. 粘贴 B站链接（每行一个），点击开始下载

## 打包 exe
见 build_exe.bat。注意：必须使用标准 Python 3.11，不要用 Anaconda，否则打包后运行报 _ctypes 加载失败。

## 文件说明
- bili_core.py  下载核心逻辑（GUI/CLI 共用）
- bili_gui.pyw  Tkinter 图形界面
- bili_cli.py   命令行入口
- install.bat   Windows 依赖安装
- build_exe.bat 打包单文件 exe
- requirements.txt  依赖

## 免责声明
下载内容版权归原作者所有，请遵守 B站及当地法律法规，仅用于个人学习研究。
