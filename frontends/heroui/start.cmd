@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "REPO_ROOT=%SCRIPT_DIR%..\.."

if not defined HEROUI_BRIDGE_PORT set "HEROUI_BRIDGE_PORT=14169"
if not defined GA_HEROUI_API_TARGET set "GA_HEROUI_API_TARGET=http://127.0.0.1:%HEROUI_BRIDGE_PORT%"

echo Starting GenericAgent HeroUI bridge: %GA_HEROUI_API_TARGET%
start "GenericAgent HeroUI Bridge" cmd /k "cd /d ""%REPO_ROOT%"" && python frontends\heroui\bridge.py"

timeout /t 2 /nobreak >nul

echo Starting GenericAgent HeroUI frontend: http://127.0.0.1:5178
start "GenericAgent HeroUI Frontend" cmd /k "cd /d ""%SCRIPT_DIR%"" && pnpm dev"

echo.
echo Open http://127.0.0.1:5178
