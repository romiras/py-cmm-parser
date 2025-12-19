#!/usr/bin/bash
# =============================================================================
# LSP Troubleshooting: Run All Scripts
# =============================================================================
# Purpose: Execute all troubleshooting scripts in sequence
# Usage:   ./run_all.sh [--quick] [--verbose]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║       LSP Troubleshooting Suite - Complete Analysis        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Date: $(date)"
echo "Directory: $SCRIPT_DIR"
echo ""

QUICK_MODE=false
VERBOSE=false

for arg in "$@"; do
    case $arg in
        --quick)
            QUICK_MODE=true
            ;;
        --verbose)
            VERBOSE=true
            ;;
    esac
done

run_script() {
    local script="$1"
    local name="$2"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Running: $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if bash "$SCRIPT_DIR/$script"; then
        echo ""
        echo "✓ $name completed successfully"
    else
        echo ""
        echo "✗ $name failed"
        return 1
    fi
    echo ""
}

# Run scripts in order
run_script "01_check_prerequisites.sh" "Prerequisites Check"

run_script "02_test_langserver_invocation.sh" "Language Server Invocation Test"

run_script "03_test_json_rpc_protocol.sh" "JSON-RPC Protocol Test"

if [ "$QUICK_MODE" = false ]; then
    run_script "04_test_definition_lookup.sh" "Definition Lookup Test"
fi

# Only run strace if verbose mode is enabled
if [ "$VERBOSE" = true ]; then
    run_script "05_diagnose_strace.sh" "System Call Diagnostics"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                 All Tests Completed                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Summary of findings:"
echo "  • Python pyright package wraps Node.js pyright"
echo "  • Language server must be started with: python -m pyright.langserver --stdio"
echo "  • NOT with: python -m pyright --langserver (wrong!)"
echo ""
echo "Next steps:"
echo "  1. Review the LSP-PROTOCOL-ISSUE-SOLUTION.md document"
echo "  2. Apply the fix to src/lsp_client.py"
echo "  3. Run unit tests to verify the fix"
