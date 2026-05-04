@echo off
setlocal

REM 中文注释：Windows 单窗口启动脚本，直接启动已构建好的新 WebUI 后端并在当前控制台输出日志。

cd /d "%~dp0"

echo [WebUI] Working directory: %CD%
echo [WebUI] Checking built frontend assets...

if not exist "frontends\webui\dist\index.html" (
  echo [WebUI] dist not found, building frontend first...
  pushd "frontends\webui"
  call npm run build
  if errorlevel 1 (
    echo [WebUI] frontend build failed
    popd
    exit /b 1
  )
  popd
)

echo [WebUI] Starting Python server on http://127.0.0.1:18601
python -m frontends.webui_server --host 127.0.0.1 --port 18601

endlocal
