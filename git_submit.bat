@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 goto :nogit

if exist .git goto :havegit
git init
git branch -M main
:havegit

git merge --abort 2>nul
git rebase --abort 2>nul

git add .
git status --short

set "msg=Bilibili downloader: GUI/CLI, auto collection download, pause/resume, cookie paste"
set /p input="Commit message - Enter to use default: "
if not "%input%"=="" set "msg=%input%"

git commit -m "%msg%"
if errorlevel 1 echo [WARN] nothing new to commit. Continuing.

git remote get-url origin >nul 2>nul
if errorlevel 1 git remote add origin https://github.com/TTaoTT/bili_downloader.git

echo [INFO] Pulling remote history if any...
git pull origin main --allow-unrelated-histories -X ours --no-edit
if errorlevel 1 echo [INFO] Pull skipped or failed, remote may be empty. Proceeding to push.

echo [INFO] Pushing to origin/main...
git push -u origin main
if errorlevel 1 goto :retry

echo Done. Pushed to https://github.com/TTaoTT/bili_downloader
goto :end

:retry
echo [ERR] push failed. Trying once more with rebase.
git pull --rebase origin main
git push -u origin main
if errorlevel 1 goto :fail
echo Done. Pushed to https://github.com/TTaoTT/bili_downloader
goto :end

:fail
echo.
echo [ERR] Push still failed. Common causes and fixes.
echo   1. Authentication: GitHub requires a Personal Access Token, not your account password.
echo      Create one at https://github.com/settings/tokens and tick repo.
echo   2. Then retry: git pull --rebase origin main  then  git push -u origin main
echo   3. To overwrite the remote on a fresh personal repo only: git push -u origin main --force
goto :end

:nogit
echo [ERR] git not found. Install from https://git-scm.com
goto :end

:end
pause
