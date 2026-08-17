# 上传到 GitHub 本地教程（bili_downloader）

> 目标仓库：https://github.com/TTaoTT/bili_downloader
> 适用目录：`T:\bi站视频下载`
> 本教程**全程在你的电脑上手动操作**，不涉及自动提交。

---

## 0. 前置准备

1. **安装 Git**：https://git-scm.com/downloads （安装时默认选项即可，建议勾选 "Git Bash"）。
2. **GitHub 账号**已注册，且仓库 `TTaoTT/bili_downloader` 已创建（若还没建：GitHub 右上角 ➜ New repository ➜ 名字填 `bili_downloader` ➜ 不要勾选 Add README，创建）。
3. **生成 Personal Access Token（PAT）**（用来代替密码推送）：
   - GitHub 网页 ➜ 右上角头像 ➜ **Settings** ➜ 左侧 **Developer settings** ➜ **Personal access tokens** ➜ **Tokens (classic)** ➜ **Generate new token (classic)**
   - Note 随便填（如 `bili-upload`），Expiration 选 `90 days` 或自定义
   - 勾选 **`repo`**（整项）
   - 最底部 **Generate token** ➜ **复制保存**（只显示这一次！）
   - ⚠️ 推送时「密码」处粘贴的就是这个 token，不是你的 GitHub 登录密码。

---

## 1. 打开项目目录的终端

- 文件管理器进 `T:\bi站视频下载`
- 在**地址栏**清空并输入 `cmd` 回车（或右键空白处 ➜「在终端中打开」/ Git Bash）
- 确认路径正确：
  ```bat
  cd /d T:\bi站视频下载
  ```

---

## 2. 关联远程仓库（只需做一次）

先看看有没有已经关联的远程：

```bat
git remote -v
```

- **如果输出为空**（没有 origin）：
  ```bat
  git remote add origin https://github.com/TTaoTT/bili_downloader.git
  ```
- **如果 origin 指向错误地址**：
  ```bat
  git remote set-url origin https://github.com/TTaoTT/bili_downloader.git
  ```
- 如果已正确指向 `TTaoTT/bili_downloader.git`，跳过本步。

---

## 3. 首次同步远程（避免冲突，很重要）

如果远程仓库**已经有 README / LICENSE 等文件**，本地没有，直接 push 会被拒。先拉一次：

```bat
git pull origin main --allow-unrelated-histories
```

- 若提示冲突，用「以本地为准」的策略合并：
  ```bat
  git pull origin main -X ours --allow-unrelated-histories
  ```
- 如果远程默认分支叫 `master` 而不是 `main`，把上面命令里的 `main` 换成 `master`。
- 若远程是**空仓库**（刚建好啥也没有），跳过本步。

---

## 4. 暂存与提交

```bat
git add -A
git commit -m "feat: B站视频下载器 - 多平台支持 + 新 logo 图标 + 暂停/托盘"
```

> ✅ 安全说明：`.gitignore` 已排除 `dist/`（打包 exe）、`build/`、`__pycache__/`、`.pkg/`、`cookies.txt`、`下载/`（你的视频目录）、`*.mp4 / *.crdownload / *.mkv / *.flv` 等媒体文件。**你的下载视频和大体积 exe 都不会被上传**，只传源码、assets 图标、脚本和文档。

---

## 5. 推送

```bat
git push -u origin main
```

- 用户名填你的 GitHub 账号名；**密码处粘贴第 0 步生成的 PAT**（不是登录密码）。
- 若远程分支是 `master`，把 `main` 换成 `master`。
- `-u` 只需第一次加，之后直接 `git push` 即可。

---

## 6. 验证

打开 https://github.com/TTaoTT/bili_downloader ，应该能看到：
`bili_core.py`、`bili_gui.pyw`、`bili_cli.py`、`build_exe.bat`、`git_submit.bat`、`install.bat`、`requirements.txt`、`README.md`、`assets/`、`analysis_report.md`、`github_upload_guide.md`、`.gitignore` 等。
**不会**出现 `下载/` 里的视频、`dist/` 的 exe。

---

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| `failed to push some refs` | 远程有本地没有的提交（README 等） | 先执行第 3 步 `git pull`，再 `git push` |
| 推送时密码错误 / 401 | 用了登录密码而非 PAT | 用 PAT；若已缓存错误凭据，Windows 凭据管理器删掉 `git:https://github.com` 再试 |
| `src refspec main does not match` | 本地分支叫 `master` | 命令里 `main` 全换成 `master` |
| 想传 exe 给用户下载 | exe 29MB 且每次打包会变，不适合进 git | 用 GitHub **Releases** 上传 `dist/bili_downloader.exe`，或用本机复制 |
| 误 add 了视频想撤回 | 还没 commit | `git reset` 撤回暂存，确认 `.gitignore` 含 `下载/` 后重来 |

---

## 备选：用 GitHub Desktop（图形界面，更省心）

1. 下载安装 GitHub Desktop：https://desktop.github.com/
2. File ➜ **Add local repository** ➜ 选 `T:\bi站视频下载` ➜ Add
3. 首次会提示 Publish（发布）：选你的账号、仓库名 `bili_downloader`、选 **Private/Public**
4. 左侧写 Summary（如 `initial commit`），点 **Commit to main**
5. 点 **Publish branch** 即可（认证用 GitHub 登录，无需 PAT）

> GitHub Desktop 同样受 `.gitignore` 约束，视频和大 exe 不会被上传。
