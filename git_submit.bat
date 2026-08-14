@echo off
REM =============================================================
REM Local git init + commit + push to GitHub (TTaoTT/bili_downloader)
REM Prerequisites:
REM   1. git installed (https://git-scm.com)
REM   2. GitHub credentials: use a Personal Access Token (PAT) for the
REM      password prompt (GitHub no longer accepts account password).
REM      Or set up SSH / Git Credential Manager beforehand.
REM Run by double-clicking, or from the project folder in a terminal.
REM =============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

where git >nul 2>nul || (echo [ERR] git not found. Install from https://git-scm.com ; pause & exit /b 1)

if not exist .git (
    git init
    git branch -M main
)

REM Clear any leftover merge/rebase conflict state from a previous failed run
git merge --abort 2>nul
git rebase --abort 2>nul

git add .
git status --short

set "msg=Bilibili downloader: GUI/CLI, auto collection download, pause/resume, cookie paste"
set /p input="Commit message (Enter to use default): "
if not "%input%"=="" set "msg=%input%"

git commit -m "%msg%" || (echo [WARN] nothing new to commit. Continuing. ; )

git remote get-url origin >nul 2>nul || git remote add origin https://github.com/TTaoTT/bili_downloader.git

REM If the remote already has files (e.g. a default README from GitHub),
REM merge them in. -X ours auto-resolves conflicts in our favor so the
REM push won't be rejected for an unrelated/conflicting history.
echo [INFO] Pulling remote history (if any)...
git pull origin main --allow-unrelated-histories -X ours --no-edit
if errorlevel 1 (
    echo [INFO] Pull skipped/failed (remote may be empty or no common history). Proceeding to push.
)

echo [INFO] Pushing to origin/main...
git push -u origin main
if errorlevel 1 (
    echo [ERR] push failed. Trying once more with rebase.
    git pull --rebase origin main
    git push -u origin main
)
if errorlevel 1 (
    echo.
    echo [ERR] Push still failed. Common causes and fixes:
    echo   1) Authentication: GitHub requires a Personal Access Token (PAT),
    echo      not your account password. Create one at:
    echo      https://github.com/settings/tokens  (tick 'repo')
    echo   2) Then retry: git pull --rebase origin main   then   git push -u origin main
    echo   3) If you want to overwrite the remote (fresh personal repo only):
    echo      git push -u origin main --force
    pause & exit /b 1
)

echo Done. Pushed to https://github.com/TTaoTT/bili_downloader
pause
