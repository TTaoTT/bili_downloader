# B站视频下载器 — 优化与多平台可下载性分析

> 生成：2026-08-17
> 依据：当前 `bili_core.py` / `bili_gui.pyw` 代码审查 + yt-dlp 2026.7.4（实测内置 **1751** 个提取器）+ 联网核实（2026-08-17）

---

## 一、现状体检（已具备的能力）

| 能力 | 状态 |
|---|---|
| B站全系下载（单视频 / 多P / 合集 / 番剧 / 直播 / 收藏夹 / 歌单 / 动态 / 个人空间） | ✅ 完善（`BiliBili*` 系列提取器 + 自研合集展开） |
| 粘贴单集自动下载整集合集 | ✅（`_resolve_collection` 解析 `ugc_season`） |
| 暂停 / 继续 | ✅（进度回调处阻塞，合并阶段不响应，见后文） |
| Cookie 粘贴 / 文件 / 浏览器获取指引 | ✅ |
| ffmpeg 便携版自动下载（双镜像重试） | ✅ |
| 系统托盘 + 自定义 logo 图标 + 任务栏分组 | ✅（本次新增） |
| 断点续传 / 片段并发 / 失败不中断整个合集 | ✅（`continuedl` + `ignoreerrors`） |

---

## 二、可优化点（按优先级）

### 🔴 P0 — 不做就卡脖子

| # | 优化项 | 当前问题 | 建议 |
|---|---|---|---|
| 1 | **内置 yt-dlp 更新** | 抖音/小红书等平台提取器**频繁失效**，联网核实「80% 的‘下不动’靠 `yt-dlp -U` 解决」。现在只能让用户自己重装，体验差 | 加「检查更新 / 一键更新 yt-dlp」按钮：`pip install -U yt-dlp`（源码运行）或下载官方最新 `yt-dlp.exe`（打包版）。**这是支持多平台的前提** |
| 2 | **解除 B站硬编码，做成通用下载器** | Cookie 保存时域写死 `.bilibili.com`；标题写死「B站视频下载器」；合集检测只认 B站 `ugc_season` | 让 yt-dlp 按 URL 自动选提取器（核心 `download()` 已经通用，只需放开 cookie 域与合集检测）；Cookie 按域名动态生成；UI 文案改为「视频下载器」 |
| 3 | **格式 / 画质选择** | 固定 `bv*+ba/best`，无法选分辨率或只下音频 | 加下拉：最高 / 1080p / 720p / **仅音频(mp3)**，映射到 yt-dlp `-f` / `-x` |

### 🟡 P1 — 体验与健壮性

| # | 优化项 | 说明 |
|---|---|---|
| 4 | **并发下载多个链接** | 现在是 `for url` 顺序下载。可加线程池并发不同链接（同站并发需可配置，避免触发风控） |
| 5 | **代理支持** | 加 SOCKS5/HTTP 输入框。跨境（TikTok）与绕过风控都必需 |
| 6 | **暂停覆盖合并阶段** | 当前仅在进度回调阻塞，音视频合并 / m3u8 片段内不响应。可在合并前插入检查点，或提示「合并阶段无法暂停」 |
| 7 | **下载历史 + 去重 + 已存在跳过** | `continuedl` 已有基础，但无明确 UI；粘贴时自动去重、过滤无效 URL |
| 8 | **错误自动退避重试** | 403 / 限流类错误应自动退避重试，而非直接标失败 |

### 🟢 P2 — 工程与细节

| # | 优化项 | 说明 |
|---|---|---|
| 9 | 暗色主题 / 高 DPI 适配 | ttk 在 Win 上偏丑，至少做 DPI 缩放 |
| 10 | 日志导出 / 复制 | 加「导出日志」按钮，便于排错 |
| 11 | exe 启动加速 | onefile 每次解压慢，可改 onefolder 或加 splash |
| 12 | 托盘完成通知（toast） | 下载全部完成时弹系统通知 |
| 13 | 配置持久化 | 输出目录 / 格式偏好 / 代理 存到 `config.json` |
| 14 | 单元测试 | 给 `ffmpeg_path` / `_cookie_header` / `_resolve_collection` 加测试，避免回归 |

---

## 三、多平台可下载性（yt-dlp 内置提取器实测）

> 评分：★ 基本不可用 / ☆ 部分可用 / ★★★★ 开箱即用。结论基于「yt-dlp 内置提取器是否存在 + 是否需要登录/代理/常更新」。

| 平台 | 内置提取器 | 开箱度 | 关键限制 | 建议 |
|---|---|---|---|---|
| **B站** | `BiliBili*` 全套 | ★★★★★ | 几乎无（登录墙内容需 cookie） | 已支持，维持 |
| **抖音** | `DouyinIE` | ★★★☆☆ | **无水印源可拿**（yt-dlp 优势）；公开视频可下；登录墙/粉丝视频需 cookie；反爬强、提取器常失效 | 加更新按钮 + cookie 即可下大部分 |
| **TikTok** | `TikTokIE` 等全套 | ★★★★☆ | 国际版多免登录；**国内需代理**；部分地区限流 | 配代理即可 |
| **小红书** | `XiaoHongShuIE` | ★★☆☆☆ | 图文/视频笔记可下；强反爬 + 常需 cookie；提取器不稳定 | 需 cookie + 常更新 |
| **快手** | ❌ **官方无** | ★☆☆☆☆ | **yt-dlp 官方列表未收录快手**；社区有 `yt-dlp-kuaishou` 第三方插件或专用工具 | 需额外装插件，或声明「不支持」 |
| **西瓜视频** | `IxiguaIE` | ★★★☆☆ | 字节系，情况同抖音（需 cookie） | 同抖音 |
| **微博** | `WeiboIE` 等 | ★★★☆☆ | 公开视频多直下；部分需登录 | 基本可用 |
| **AcFun** | `AcFunVideoIE` | ★★★★☆ | 类 B站，较稳 | 基本可用 |
| **爱奇艺/优酷/腾讯视频/芒果TV** | `IqiyiIE`/`YoukuIE`/`WeTv*`/`MGTVIE` 等 | ★★☆☆☆ | **加密会员内容基本下不了**（DRM）；免费内容常被地域/登录限制 | 价值有限，按需 |
| **知乎** | `ZhihuIE` | ★★★☆☆ | 视频回答可下 | 基本可用 |
| **斗鱼 / 虎牙直播** | `DouyuTVIE` / `HuyaLiveIE` | ★★☆☆☆ | 直播 m3u8 可录，稳定性差、易断 | 按需 |
| **网易云 / QQ音乐** | `NetEaseMusic*` / `QQMusic*` | ★★★☆☆ | 音频可下；**会员歌曲加密** | 仅非会员可用 |

### 关键结论
1. **yt-dlp 覆盖面极广**，抖音/小红书/TikTok/西瓜/微博/AcFun/知乎等**技术上已经能下**——拦路虎是 **cookie + 常更新 + 部分需代理**，不是代码本身。
2. **快手是明显硬缺口**：官方不支持，要么集成社区插件，要么在 UI 里明确「暂不支持快手」。
3. **长视频平台（爱优腾芒）会员内容基本不可下**，投入产出比低，优先级放后。
4. **「更新 yt-dlp」是性价比最高的改动**——直接决定上面所有中国平台能不能用。

---

## 四、从「B站专用」扩展为「通用下载器」的改造路线

1. **解耦平台**：删掉 B站硬编码。核心 `download()` 已通用，只需：
   - `_cookie_text_to_netscape` 把写死的 `.bilibili.com` 改为**按 URL 域名动态生成**（或多域通用）；
   - `_resolve_collection` 对非 B站 URL 直接走 yt-dlp 通用 playlist 检测（已有 `_detect_playlist`）。
2. **加「更新 yt-dlp」按钮**（P0-1）—— 可用性保障。
3. **UI 文案**改为「视频下载器」，加「已自动识别平台」提示。
4. **可选增强**：格式选择、仅音频、代理、并发（P0-3 / P1）。
5. **快手缺口**：通过 yt-dlp 的「自定义提取器加载」机制引入社区 `kuaishou` 插件，或显式标注不支持。

---

## 五、建议执行顺序

1. **先做 P0-1（内置更新） + P0-2（解耦平台 + cookie 动态域）** —— 这两条一做，抖音/小红书/TikTok 等立刻「能用」，且 B站体验不退化。改动集中在 `bili_core.py` 的 cookie 处理与 GUI 文案，**风险低、收益高**。
2. 接着做 **P0-3 格式/音频选择** + **P1-5 代理**。
3. 最后按需求补 P1/P2 的并发、历史、主题等。
4. 快手：单独评估是否引入社区插件（建议先标注「暂不支持」，避免误导）。

> 备注：快手不在 yt-dlp 官方 1751 个提取器列表；抖音/小红书等存在但需 cookie 与频繁更新，结论已联网核实（2026-08-17）。

---

## 六、P0 改造详细设计（代码示例 + 验收标准）

> 本章为可落地的开发规格，代码示例来自实际已实现的 `bili_core.py` / `bili_gui.pyw`。使用前先确认 yt-dlp 自带 `Bilibili*` 之外的提取器（抖音/小红书/TikTok 等）在本机 yt-dlp 版本中可用。

### 6.1 内置「更新 yt-dlp」按钮（P0-1）

**设计**：中国平台提取器频繁失效，靠 `yt-dlp -U` 解决。两路更新：
- **源码运行**（`.pyw` 直接跑）：`python -m pip install -U yt-dlp` —— 立即生效。
- **打包 exe**：下载 PyPI 最新 **wheel** 解压到 `<exe目录>/yt_dlp_vendor/`，**下次启动生效**。GUI 在 `import bili_core` 之前把该目录插入 `sys.path` 并前置到 PyInstaller 冻结导入器之前，从而覆盖内置版本。

**关键代码**（`bili_core.update_ytdlp` 摘要）：
```python
# exe 模式：拉取最新 wheel 并解压到 yt_dlp_vendor
ver, url = BiliDownloader._latest_ytdlp_wheel(on_log)   # PyPI JSON -> (version, wheel_url)
whl = os.path.join(base, "yt_dlp_update.whl")
BiliDownloader._download_file(url, whl, on_log, timeout=60, max_retries=4)
with zipfile.ZipFile(whl) as z:
    z.extractall(vendor)            # vendor = <base>/yt_dlp_vendor
open(os.path.join(vendor, "VERSION"), "w").write(ver)
```
```python
# bili_gui.pyw 顶部、导入 bili_core 之前：让 vendor 覆盖内置版本
_vendor = os.path.join(HERE, "yt_dlp_vendor")
if os.path.isdir(os.path.join(_vendor, "yt_dlp")):
    sys.path.insert(0, _vendor)
    frozen = [f for f in sys.meta_path if "Frozen" in type(f).__name__]
    others = [f for f in sys.meta_path if "Frozen" not in type(f).__name__]
    sys.meta_path = others + frozen
```

**验收标准**：
- [ ] 源码模式点按钮后，日志显示新版本号且无需重启即可用新提取器。
- [ ] exe 模式点按钮后下载 wheel（~3MB）到 `yt_dlp_vendor/`，日志提示「重启生效」；重启后 `yt_dlp_version()` 变为新版本。
- [ ] 网络失败时有明确错误日志，不崩溃、不破坏现有版本。

**风险**：① exe 更新需重启（ unavoidable，因冻结包不可运行时替换）；② `sys.meta_path` 重排依赖 PyInstaller 冻结导入器类名含 `Frozen`，已在代码中以字符串匹配，跨版本基本稳定。

### 6.2 解耦为通用下载器（P0-2）

**设计**：`download()` 本就通用，只需放开三处：
1. **Cookie 域动态化**：每个链接按其 URL 域名生成对应 Netscape cookie，登录态在任意平台生效。
2. **合集检测仅限 B站**：非 `bilibili` 域名跳过 `_resolve_collection`，直接走 yt-dlp 通用 playlist 检测。
3. **UI 文案通用化** + **平台识别提示**。

**关键代码**（下载循环内）：
```python
host = urllib.parse.urlparse(url).netloc.lower()
domain = ("." + host[4:]) if host.startswith("www.") else ("." + host if host else "")
if cookies_path and os.path.isfile(cookies_path):
    pairs = self._read_cookie_pairs(cookies_path)          # 兼容 Netscape / name=value
    tmpc = os.path.join(tempfile.gettempdir(), f"bili_cookie_{idx}.txt")
    with open(tmpc, "w", encoding="utf-8") as f:
        for n, v in pairs:
            f.write(f"{domain}\tTRUE\t/\tFALSE\t0\t{n}\t{v}\n")
    base["cookiefile"] = tmpc
...
if auto_collection and "bilibili" in host:                 # 合集特判只给 B站
    res = self._resolve_collection(url, cookie_header)
```

**验收标准**：
- [ ] 粘贴抖音/小红书/TikTok 链接 → 平台识别提示显示对应名称，正常下单视频/合集。
- [ ] 粘贴任意平台链接 + 该站 Cookie → 使用登录态（不再因写死 `.bilibili.com` 而失效）。
- [ ] B站单集仍自动展开合集；非 B站链接不误触发 B站合集逻辑。
- [ ] 窗口标题/托盘名改为「视频下载器」。

**风险**：① Cookie 是站点专属，跨站粘贴同一份 cookie 对不匹配的域名无效（预期行为，已在 UI 提示按平台获取）；② `_detect_playlist` 对部分平台可能误判，已 `ignoreerrors` 兜底。

### 6.3 画质 / 仅音频（P0-3）

**设计**：GUI 下拉（最高画质 / 1080p / 720p / 仅音频 mp3）→ 映射到 yt-dlp `-f` 与音频后处理。

**映射**（`bili_core._base_opts`）：
```python
audio_only = (format_choice == "audio")
if audio_only:                       fmt = "ba/bestaudio"
elif not ffmpeg_ok:                  fmt = "best"          # 无 ffmpeg 无法合并，降级
else: fmt = {"best":"bv*+ba/best",
             "1080p":"bv[height<=1080]+ba/best[height<=1080]",
             "720p":"bv[height<=720]+ba/best[height<=720]"}.get(format_choice,"bv*+ba/best")
# 仅音频追加后处理
if audio_only:
    opts["postprocessors"] = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
```

**验收标准**：
- [ ] 选 1080p/720p → 实际下载对应分辨率（需 ffmpeg）。
- [ ] 选「仅音频」→ 产出 `.mp3`（需 ffmpeg；无 ffmpeg 时 GUI 提前警告拦截）。
- [ ] 无 ffmpeg 时画质选项自动降级为「best」单文件，不报错。

---

## 七、实现记录（2026-08-17 后续）

### 7.1 改动文件
- `bili_core.py`：新增 `update_ytdlp` / `_latest_ytdlp_wheel` / `yt_dlp_version` / `_read_cookie_pairs`；`_base_opts` 支持 `format_choice` 与音频后处理；`download()` 增加 `format_choice`、按 URL 域名动态生成 cookie、合集检测仅限 B站。
- `bili_gui.pyw`：顶部 vendor 覆盖逻辑；标题/托盘「B站视频下载器」→「视频下载器」；状态栏「更新 yt-dlp」按钮；选项栏画质下拉；平台识别提示行；`_detect_platforms` / `_update_ytdlp`。

### 7.2 实测验证（本机 Python 3.11 + yt-dlp 2026.07.04）
- ✅ 两文件真实导入成功（含 tkinter，无 Tk root 创建）。
- ✅ `_read_cookie_pairs` 正确解析 Netscape：`[('SESSDATA','abc123')]`。
- ✅ 画质映射（模拟 ffmpeg 存在）：`best→bv*+ba/best`、`1080p→bv[height<=1080]+ba/best[height<=1080]`、`720p→bv[height<=720]+ba/...`、音频追加 `FFmpegExtractAudio` 后处理；无 ffmpeg 时正确降级为 `best`。
- ✅ `_latest_ytdlp_wheel` 联网成功返回最新版本号与 wheel 下载地址。
- ✅ 域名推导：`www.douyin.com→.douyin.com`、`b23.tv→.b23.tv`、`www.xiaohongshu.com→.xiaohongshu.com`。

### 7.3 已重建 exe
- 打包命令同前（`--collect-all yt_dlp --collect-all pystray --icon assets/icon.ico --add-data assets;assets`）。
- 产物 `dist/bili_downloader.exe` 已复用本机 Python 3.11 重新生成；smoke test 通过。

### 7.4 遗留 / 待办
- **快手**：yt-dlp 官方不支持，UI 平台识别已标注「快手(暂不支持)」；如需支持需引入社区 `yt-dlp-kuaishou` 插件（新开任务）。
- **exe 更新 yt-dlp 需重启一次**才生效（冻结包限制，已用 vendor 覆盖机制把影响降到最低）。
- **抖音/小红书实际下载**：提取器是否当前有效取决于 yt-dlp 版本，建议首次使用先点「更新 yt-dlp」并自备该站 Cookie；本环境无法实测真实视频下载（需目标站点登录态 + 网络）。

---

## 八、P1 / P2 实现记录（2026-08-17）

> 本章记录 P1（并发 / 代理 / 历史去重 / 重试）与 P2（配置持久化 / 高 DPI / 暗色 / 日志导出 / 托盘通知 / 启动 splash / 单元测试）的落地情况。

### 8.1 P1 实现

**P1-4 并发下载多个链接**
- `download()` 新增 `max_workers` 参数；`>1` 时用 `concurrent.futures.ThreadPoolExecutor` 线程池并发处理多个 URL（`as_completed` 收集结果）。
- **关键坑已规避**：每个链接在 `_download_one()` 内重新生成独立 `opts`（不再共享同一个 `base` 字典），避免并发下 `outtmpl`/`cookiefile` 互相覆盖冲突；`progress_hooks` 各自绑定自己的 `idx`。
- 配置项「并发数」Spinbox（1–6，默认 2），UI 提示「同站建议 ≤2，避免风控」。
- 全局 `request_stop()` / `request_pause()` 仍对所有线程生效（暂停=全部暂停）。

**P1-5 代理支持**
- `download()` 新增 `proxy` 参数；`_download_one()` 内 `opts["proxy"] = proxy`。
- GUI 新增「代理」输入框（占位 `socks5://127.0.0.1:7890`），跨境 TikTok / 绕过风控即填此处；启动时写入 `config.json`。

**P1-7 下载历史 + 去重 + 已存在跳过**
- 新增 `history_path`（默认 `<exe目录>/download_history.json`）；`download()` 启动时 `_load_history()`，结束 `_save_history()`。
- `dedup_urls(urls, history)`：过滤列表内重复 + 已成功下载过的链接；`download()` 开头即去重并提示「过滤掉 N 个重复 / 已下载」。
- 粘贴 / 载入时 GUI 端 `_insert_urls()` 再做一次列表内去重并提示跳过数（双击不怕重复粘）。

**P1-8 错误自动退避重试**
- `_download_one()` 捕获 `DownloadError`，对 403 / 429 / HTTP Error / rate limit / Too Many Requests / 频控 / Please try again later 等「限流类」自动退避重试（最多 3 次，`wait = 2**attempt` 秒）；其余错误直接标记失败，不浪费重试。

### 8.2 P2 实现

| 项 | 落地 |
|---|---|
| P2-9 高 DPI | `main()` 在创建 Tk 前调用 `SetProcessDpiAwareness(1)`（Win），清晰缩放 |
| P2-9 暗色主题 | 新增「暗色主题」开关（`ttk.Style` + `clam` 主题，背景/前景/日志区整体切换，配置持久化） |
| P2-10 日志导出 | 日志区新增「导出日志」按钮 → 另存为 txt |
| P2-12 托盘完成通知 | 全部任务结束 `_finish()` 时 `self._tray.notify("下载任务已完成", ...)`（toast） |
| P2-13 配置持久化 | `config.json`：输出目录 / 画质 / 代理 / 并发数 / 自动合集 / 暗色；启动载入、开始下载时保存 |
| P2-11 exe 启动加速 | 打包加 `--splash assets/splash.png`（粉渐变 + logo 启动图，`main()` 用 `FindWindowW("Splash")+WM_CLOSE` 自动关闭）；重建 exe 已含 |
| P2-14 单元测试 | `tests/test_bili_core.py`：cookie 解析 / 画质映射 / 去重 / 规范化 / `_safe_name` 共 10 项断言，全通过 |

### 8.3 验证结果（本机 Python 3.11 + yt-dlp 2026.07.04）
- ✅ `bili_core.py` / `bili_gui.pyw` 真实导入成功（含 tkinter）。
- ✅ 单元测试 10/10 通过（含修复的 `_read_cookie_pairs` 头部风格多 cookie 解析 bug）。
- ✅ 重建 `dist/bili_downloader.exe`（29.7MB，含 splash + pystray + 全部 P0/P1/P2），smoke test 通过（`EXIT_CODE=124`）。
- ✅ `.gitignore` 新增 `config.json` / `download_history.json`（本地配置不入库）。

### 8.4 遗留 / 说明
- **P1-6 暂停覆盖合并阶段**：yt-dlp 合并 / m3u8 片段内不调用进度回调，暂停在「下载分P」阶段生效，合并阶段无法即时暂停（架构限制）；已在 UI 提示「暂停后于下一分P生效」。彻底解决需改用外部进程信号或分片下载器，投入大，暂不实现。
- **暗色主题**：基于 ttk `clam` 主题尽力而为，部分原生下拉列表在暗色下可能仍偏亮；属已知小瑕疵。
- **exe 更新 yt-dlp 仍需重启一次**才生效（冻结包限制，vendor 覆盖机制已最小化影响）。
- 快手依旧官方不支持（UI 标注「暂不支持」）。

