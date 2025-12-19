#!/usr/bin/bash
# =============================================================================
# LSP Troubleshooting Script 1: Check Prerequisites
# =============================================================================
# Purpose: Verify all required dependencies are installed and accessible
# Usage:   ./01_check_prerequisites.sh
# =============================================================================

echo "============================================================"
echo "LSP Prerequisites Check"
echo "============================================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    local expected="$3"
    
    echo -n "Checking $name... "
    if result=$(eval "$cmd" 2>/dev/null); then
        if [ -n "$expected" ]; then
            if echo "$result" | grep -q "$expected"; then
                echo -e "${GREEN}✓ PASS${NC} ($result)"
                ((PASS++))
                return 0
            else
                echo -e "${RED}✗ FAIL${NC} (expected: $expected, got: $result)"
                ((FAIL++))
                return 1
            fi
        else
            echo -e "${GREEN}✓ PASS${NC} ($result)"
            ((PASS++))
            return 0
        fi
    else
        echo -e "${RED}✗ FAIL${NC}"
        ((FAIL++))
        return 1
    fi
}

echo "1. Node.js (required for Pyright)"
echo "-----------------------------------"
check "Node.js installation" "node --version" ""
check "Node.js version >= 14" "node -e 'console.log(parseInt(process.version.substring(1)) >= 14)'" "true"
echo ""

echo "2. Python Environment"
echo "-----------------------------------"
check "Python 3" "python3 --version" "Python 3"
check "UV (package manager)" "uv --version" ""
echo ""

echo "3. Pyright Installation"
echo "-----------------------------------"
# Change to src directory for uv context
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT/src"
check "Pyright package" "uv run python -c 'import pyright; print(pyright.__pyright_version__)'" ""
check "Pyright CLI" "uv run python -m pyright --version" "pyright"
check "Pyright langserver module" "uv run python -c 'import pyright.langserver; print(\"available\")'" "available"
echo ""

echo "4. Virtual Environment"
echo "-----------------------------------"
if [ -d "$PROJECT_ROOT/src/.venv" ]; then
    echo -e "Virtual environment: ${GREEN}✓ FOUND${NC} ($PROJECT_ROOT/src/.venv)"
    ((PASS++))
else
    echo -e "Virtual environment: ${RED}✗ NOT FOUND${NC}"
    echo "   Run: cd src && uv sync"
    ((FAIL++))
fi

# Check dist folder (where Node.js pyright is installed)
if [ -d "$PROJECT_ROOT/src/.venv/lib/python3.12/site-packages/pyright/dist" ]; then
    echo -e "Pyright dist folder: ${GREEN}✓ FOUND${NC}"
    ((PASS++))
else
    echo -e "Pyright dist folder: ${YELLOW}⚠ NOT FOUND${NC} (will be auto-downloaded on first use)"
fi
echo ""

echo "============================================================"
echo "Summary: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "============================================================"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "⚠️  Some prerequisites are missing. Please fix them before proceeding."
    exit 1
else
    echo ""
    echo "✅ All prerequisites are satisfied!"
    exit 0
fi
