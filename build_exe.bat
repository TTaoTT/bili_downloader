@echo off
REM =============================================================
REM Build a standalone Windows exe for the Bilibili downloader.
REM IMPORTANT: Use a STANDARD Python 3.11 from python.org.
REM   Do NOT use Anaconda/conda Python - it breaks _ctypes after
REM   packaging (DLL load failure). The python.org installer ships
REM   tcl/tk and packages cleanly with PyInstaller.
REM Run this from the project folder (where bili_gui.pyw lives).
REM Output: dist\bili_downloader.exe  (no Python needed to run)
REM =============================================================
setlocal

where py >nul 2>nul
if errorlevel 1 (
    echo [ERR] Python not found. Install standard Python 3.11 from
    echo       https://www.python.org/downloads/  (tick "Add python.exe to PATH")
    pause
    exit /b 1
)

py -3.11 --version >nul 2>nul
if errorlevel 1 (
    echo [ERR] Standard Python 3.11 not found.
    echo       Anaconda will NOT work for packaging (breaks _ctypes).
    echo       Install python-3.11.x from python.org (keep "tcl/tk and IDLE" checked).
    pause
    exit /b 1
)

echo [1/3] Installing build dependencies ...
py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install pyinstaller "yt-dlp>=2024.1.0" pystray

echo [2/3] Building single-file executable (takes ~1 min) ...
REM 清理可能残留的只读 .spec / build 目录，避免 PyInstaller 改写被拒
if exist bili_downloader.spec del /F /Q bili_downloader.spec >nul 2>nul
if exist build rmdir /S /Q build >nul 2>nul
py -3.11 -m PyInstaller --noconfirm --onefile --windowed --name bili_downloader --icon assets/icon.ico --splash assets/splash.png --add-data assets;assets --collect-all yt_dlp --collect-all pystray bili_gui.pyw
if errorlevel 1 (
    echo [ERR] Build failed. See output above.
    pause
    exit /b 1
)

echo [3/3] Done. Executable at: dist\bili_downloader.exe
echo Copy bili_downloader.exe anywhere. Put cookies.txt next to it for
echo logged-in (higher quality) downloads. ffmpeg is auto-downloaded on first use.
pause
