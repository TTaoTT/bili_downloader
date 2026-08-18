@echo off
REM =============================================================
REM Build a standalone Windows exe for the video downloader.
REM IMPORTANT: Use STANDARD Python 3.10 (python.org or MS Store).
REM   Do NOT use Anaconda/conda Python - it breaks _ctypes after
REM   packaging (DLL load failure). Standard Python ships tcl/tk
REM   and packages cleanly with PyInstaller.
REM Run by double-clicking from the project folder.
REM Output: dist\bili_downloader.exe  (no Python needed to run)
REM =============================================================
setlocal
cd /d %~dp0

where py >nul 2>nul
if errorlevel 1 (
    echo [ERR] Python not found. Install standard Python 3.10 from
    echo       https://www.python.org/downloads/  (tick "Add python.exe to PATH")
    pause
    exit /b 1
)

py -3.10 --version >nul 2>nul
if errorlevel 1 (
    echo [ERR] Standard Python 3.10 not found.
    echo       Anaconda will NOT work for packaging (breaks _ctypes).
    echo       Install python-3.10.x from python.org (keep "tcl/tk and IDLE" checked).
    pause
    exit /b 1
)

echo [1/3] Installing build dependencies ...
py -3.10 -m pip install --upgrade pip
py -3.10 -m pip install pyinstaller "yt-dlp>=2024.1.0" pystray

echo [2/3] Building single-file executable (takes ~1 min) ...
REM remove stale read-only .spec / build dir to avoid PyInstaller rewrite denial
if exist bili_downloader.spec del /F /Q bili_downloader.spec >nul 2>nul
if exist build rmdir /S /Q build >nul 2>nul
if exist dist\bili_downloader.exe del /F /Q dist\bili_downloader.exe >nul 2>nul
py -3.10 -m PyInstaller --noconfirm --onefile --windowed --name bili_downloader --icon assets/icon.ico --splash assets/splash.png --add-data "assets;assets" --collect-all yt_dlp --collect-all pystray bili_gui.pyw
if errorlevel 1 (
    echo [ERR] Build failed. See output above.
    pause
    exit /b 1
)

echo [3/3] Done. Executable at: dist\bili_downloader.exe
echo Copy bili_downloader.exe anywhere. Put cookies.txt next to it for
echo logged-in (higher quality) downloads. ffmpeg is auto-downloaded on first use.
pause
