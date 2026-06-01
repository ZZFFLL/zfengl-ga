#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export HEROUI_BRIDGE_PORT="${HEROUI_BRIDGE_PORT:-14169}"
export GA_HEROUI_API_TARGET="${GA_HEROUI_API_TARGET:-http://127.0.0.1:$HEROUI_BRIDGE_PORT}"

echo "Starting GenericAgent HeroUI bridge: $GA_HEROUI_API_TARGET"

if [ -d "/Applications/Utilities/Terminal.app" ] || [ -d "/System/Applications/Utilities/Terminal.app" ]; then
    osascript -e "tell application \"Terminal\" to do script \"cd '$REPO_ROOT' && python3 frontends/heroui/bridge.py\""
else
    nohup python3 "$REPO_ROOT/frontends/heroui/bridge.py" > "$HOME/heroui-bridge.log" 2>&1 &
    echo "Bridge started in background (pid $!), logs: ~/heroui-bridge.log"
fi

sleep 2

echo "Starting GenericAgent HeroUI frontend: http://127.0.0.1:5178"
cd "$SCRIPT_DIR"

if [ -x "node_modules/.bin/vite" ]; then
    ./node_modules/.bin/vite --host 127.0.0.1
else
    node "node_modules/vite/bin/vite.js" --host 127.0.0.1
fi

echo ""
echo "Open http://127.0.0.1:5178"