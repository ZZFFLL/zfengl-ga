@echo off
setlocal

REM 中文注释：Windows 开发模式脚本，分别打开前端与后端两个控制台窗口，方便同时看日志。

cd /d "%~dp0"

echo [WebUI-DEV] Working directory: %CD%
echo [WebUI-DEV] Starting backend window...
start "GA WebUI Backend" cmd /k "cd /d %CD% && python -m frontends.webui_server --host 127.0.0.1 --port 18601"

echo [WebUI-DEV] Starting frontend window...
start "GA WebUI Frontend" cmd /k "cd /d %CD%\frontends\webui && npm run dev"

echo [WebUI-DEV] Backend: http://127.0.0.1:18601
echo [WebUI-DEV] Frontend dev server is shown in the frontend window logs.

endlocal
