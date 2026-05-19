@echo off
setlocal

REM Start Yunju OpenWebUI adapter with server defaults.
cd /d "%~dp0..\.."
python -m frontends.yunju_openwebui_adapter.server

echo.
pause
