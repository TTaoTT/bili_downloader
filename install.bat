@echo off
setlocal
REM ---------------------------------------------------------------
REM Bilibili downloader - dependency installer (ASCII only)
REM Double-click runs this; window stays open until you press a key.
REM ---------------------------------------------------------------

echo ============================================
echo  Bilibili Downloader - install dependencies
echo ============================================
echo.

REM --- pick a python interpreter ---
set "PY="
where python >nul 2>nul
if not errorlevel 1 ( set "PY=python" ) else (
    where py >nul 2>nul
    if not errorlevel 1 ( set "PY=py" )
)

if "%PY%"=="" (
    echo [ERROR] Python not found. Install Python 3 from python.org and check "Add to PATH".
    echo          Then run this installer again.
    pause
    exit /b 1
)
echo Using interpreter: %PY%
echo.

REM --- install yt-dlp ---
echo [1/2] Installing yt-dlp ...
%PY% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your network / Python environment.
    pause
    exit /b 1
)
echo yt-dlp installed OK.
echo.

REM --- verify yt-dlp works ---
echo Verifying yt-dlp ...
%PY% -m yt_dlp --version 2>nul
if errorlevel 1 (
    echo [WARN] yt-dlp installed but not runnable. Try restarting the terminal.
) else (
    echo yt-dlp is working.
)
echo.

REM --- check ffmpeg (optional, for best quality) ---
echo [2/2] Checking ffmpeg ...
where ffmpeg >nul 2>nul
if not errorlevel 1 (
    echo ffmpeg found - best quality 1080P+ supported.
) else (
    echo ffmpeg NOT found. Best quality needs it to merge audio+video.
    echo   Option A:  winget install ffmpeg
    echo   Option B:  download portable build from https://www.gyan.dev/ffmpeg/builds/
    echo              unzip, put bin\ffmpeg.exe into .\tools\ffmpeg\bin\
    echo   Without ffmpeg it still works, but downloads pre-merged lower quality.
)
echo.
echo Done. Double-click bili_gui.pyw to start.
pause
