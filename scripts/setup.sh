#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$SKILL_DIR/.venv"
REQ_FILE="$SKILL_DIR/requirements.txt"
MIN_MAJOR=3
MIN_MINOR=9

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${BOLD}$1${NC}"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
fail()  { echo -e "  ${RED}✗${NC} $1"; }
warn()  { echo -e "  ${YELLOW}!${NC} $1"; }

# ── Step 1: Find Python 3.9+ ──
info "检查 Python..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
        minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
        if [ "$major" -ge "$MIN_MAJOR" ] && [ "$minor" -ge "$MIN_MINOR" ]; then
            PYTHON="$cmd"
            ok "Python $ver ($(command -v "$cmd"))"
            break
        else
            warn "$cmd 版本 $ver 太低（需要 ${MIN_MAJOR}.${MIN_MINOR}+）"
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "未找到 Python ${MIN_MAJOR}.${MIN_MINOR}+"
    echo ""
    echo "安装方式："
    echo "  macOS:   brew install python"
    echo "  Ubuntu:  sudo apt install python3"
    echo "  其他:    https://www.python.org/downloads/"
    exit 1
fi

# ── Step 2: Create venv ──
info "创建虚拟环境..."

if [ -d "$VENV_DIR" ] && [ -x "$VENV_DIR/bin/python3" ]; then
    ok "venv 已存在，跳过创建"
else
    "$PYTHON" -m venv "$VENV_DIR"
    ok "venv 创建完成 → .venv/"
fi

VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTHON="$VENV_DIR/bin/python3"

# ── Step 3: Install Python deps ──
info "安装 Python 依赖..."

"$VENV_PIP" install --quiet --upgrade pip 2>/dev/null || true
if "$VENV_PIP" install --quiet -r "$REQ_FILE"; then
    pw_ver=$("$VENV_PYTHON" -c "from importlib.metadata import version; print(version('playwright'))" 2>/dev/null || echo "installed")
    ok "playwright $pw_ver"
    ok "playwright-stealth"
else
    fail "pip install 失败"
    echo ""
    echo "重试："
    echo "  $VENV_PIP install -r $REQ_FILE"
    exit 1
fi

# ── Step 4: Install Playwright browsers ──
info "安装 Chromium 浏览器..."

if "$VENV_DIR/bin/playwright" install chromium 2>&1; then
    ok "chromium 安装完成"
else
    fail "Chromium 下载失败（通常是网络问题）"
    echo ""
    echo "重试："
    echo "  $VENV_DIR/bin/playwright install chromium"
    exit 1
fi

# ── Step 5: Health check ──
info "验证安装..."

errors=0

if "$VENV_PYTHON" -c "from playwright.async_api import async_playwright" 2>/dev/null; then
    ok "playwright 可导入"
else
    fail "playwright 导入失败"
    errors=$((errors + 1))
fi

if "$VENV_PYTHON" -c "from playwright_stealth import Stealth" 2>/dev/null; then
    ok "playwright-stealth 可导入"
else
    fail "playwright-stealth 导入失败"
    errors=$((errors + 1))
fi

if [ "$errors" -gt 0 ]; then
    echo ""
    fail "安装验证失败（$errors 个问题）"
    echo "  运行诊断：$SKILL_DIR/scripts/doctor.sh"
    exit 1
fi

# ── Done ──
echo ""
py_ver=$("$VENV_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
pw_ver=$("$VENV_PYTHON" -c "from importlib.metadata import version; print(version('playwright'))" 2>/dev/null || echo "?")

echo -e "${GREEN}${BOLD}rent-ops 安装完成${NC}"
echo ""
echo "  Python:     $py_ver"
echo "  venv:       $VENV_DIR"
echo "  playwright: $pw_ver"
echo "  chromium:   已安装"
echo ""
echo "  运行: /rent"
