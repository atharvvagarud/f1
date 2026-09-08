#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

osascript <<EOF
tell application "Terminal"
    do script "cd '$ROOT' && source venv/bin/activate && python -m uvicorn api.main:app --reload --reload-dir api"
    do script "cd '$ROOT/frontend' && npm run dev"
end tell
EOF