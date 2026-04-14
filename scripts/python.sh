#!/usr/bin/env bash
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$SKILL_DIR/.venv/bin/python3"

if [ -x "$VENV_PYTHON" ]; then
    exec "$VENV_PYTHON" "$@"
else
    echo "rent-ops 环境未安装。请运行：$SKILL_DIR/scripts/setup.sh" >&2
    exit 1
fi
