@echo off
REM =============================================================
REM Local git init + commit + push to GitHub (TTaoTT/bili_downloader)
REM Prerequisites:
REM   1. git installed (https://git-scm.com)
REM   2. you are logged into GitHub on this machine (credential manager / SSH)
REM Run by double-clicking, or from the project folder in a terminal.
REM =============================================================
setlocal
cd /d "%~dp0"

where git >nul 2>nul || (echo [ERR] git not found. Install from https://git-scm.com ; pause & exit /b 1)

if not exist .git (
    git init
    git branch -M main
)

git add .
git status --short

set "msg=Bilibili downloader: GUI/CLI, auto collection download, pause/resume, cookie paste"
set /p input="Commit message (Enter to use default): "
if not "%input%"=="" set "msg=%input%"

git commit -m "%msg%" || (echo [WARN] nothing to commit or commit failed. ; pause & exit /b 0)

git remote get-url origin >nul 2>nul || git remote add origin https://github.com/TTaoTT/bili_downloader.git

REM If the remote already has files (e.g. a default README), pull first.
git pull origin main --allow-unrelated-histories --no-edit 2>nul

git push -u origin main
if errorlevel 1 (
    echo [ERR] push failed. Possible causes: conflict or missing credentials.
    echo   Fix: git pull --rebase origin main   then   git push -u origin main
    pause & exit /b 1
)

echo Done. Pushed to https://github.com/TTaoTT/bili_downloader
pause
