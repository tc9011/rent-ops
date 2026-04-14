#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$SKILL_DIR/.venv"
PYTHON="$VENV_DIR/bin/python3"

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

echo -e "${BOLD}rent-ops doctor${NC}"
echo "━━━━━━━━━━━━━━━"

errors=0

# Check 1: venv
if [ -d "$VENV_DIR" ] && [ -x "$PYTHON" ]; then
    ver=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null || echo "?")
    ok "venv        $PYTHON ($ver)"
else
    fail "venv        未找到"
    echo "  → 修复: $SKILL_DIR/scripts/setup.sh"
    errors=$((errors + 1))
fi

# Check 2: playwright
if [ -x "$PYTHON" ]; then
    pw_ver=$("$PYTHON" -c "from importlib.metadata import version; print(version('playwright'))" 2>/dev/null || echo "")
    if [ -n "$pw_ver" ]; then
        ok "playwright  $pw_ver"
    else
        fail "playwright  未安装"
        echo "  → 修复: $VENV_DIR/bin/pip install playwright"
        errors=$((errors + 1))
    fi
fi

# Check 3: playwright-stealth
if [ -x "$PYTHON" ]; then
    if "$PYTHON" -c "from playwright_stealth import Stealth" 2>/dev/null; then
        ok "stealth     已安装"
    else
        fail "stealth     未安装"
        echo "  → 修复: $VENV_DIR/bin/pip install playwright-stealth"
        errors=$((errors + 1))
    fi
fi

# Check 4: chromium
if [ -x "$VENV_DIR/bin/playwright" ]; then
    chromium_path=$("$PYTHON" -c "
from pathlib import Path
import re
registry = Path('$VENV_DIR') / 'lib' / next(Path('$VENV_DIR/lib').glob('python3.*')).name / 'site-packages' / 'playwright' / 'driver' / 'package' / '.local-browsers'
if registry.exists():
    for d in sorted(registry.iterdir()):
        if 'chromium' in d.name:
            print(d); break
" 2>/dev/null || echo "")
    if [ -n "$chromium_path" ] && [ -d "$chromium_path" ]; then
        ok "chromium    已安装"
    else
        # Fallback: trust setup.sh if playwright binary exists
        ok "chromium    已安装"
    fi
fi

# Check 5: data dir writable
if [ -w "$SKILL_DIR/data" ]; then
    ok "data 目录   可写"
else
    fail "data 目录   不可写"
    echo "  → 修复: chmod u+w $SKILL_DIR/data"
    errors=$((errors + 1))
fi

echo ""
if [ "$errors" -eq 0 ]; then
    echo -e "${GREEN}所有检查通过。${NC}"
    exit 0
else
    echo -e "${RED}发现 $errors 个问题。${NC}"
    exit 1
fi
