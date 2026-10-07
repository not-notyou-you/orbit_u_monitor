@echo off
REM run.bat - nyalakan Orbit-U: The Monitor (API + web UI).
REM Klik dua kali berkas ini, atau jalankan "run.bat" dari terminal.
REM Tidak butuh ubah PowerShell ExecutionPolicy.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv tidak ditemukan di %cd%\venv
    pause
    exit /b 1
)

echo.
echo   Landing  : http://localhost:8001
echo   Aplikasi : http://localhost:8001/app
echo   API docs : http://localhost:8001/docs
echo.
echo   Tekan Ctrl+C untuk mematikan server.
echo.

venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8001 %*

pause
