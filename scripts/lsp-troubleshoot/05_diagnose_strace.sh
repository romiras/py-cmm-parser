#!/usr/bin/bash
# =============================================================================
# LSP Troubleshooting Script 5: Deep Diagnostics with strace
# =============================================================================
# Purpose: Use strace to capture system calls for debugging I/O issues
# Usage:   ./05_diagnose_strace.sh
# Note:    May require running as root or with CAP_SYS_PTRACE capability
# =============================================================================

echo "============================================================"
echo "Deep Diagnostics: System Call Tracing"
echo "============================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="$PROJECT_ROOT/test_results/lsp_diagnostics"

mkdir -p "$OUTPUT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if strace is available
if ! command -v strace &> /dev/null; then
    echo -e "${YELLOW}strace not installed. Install with: sudo apt install strace${NC}"
    echo "Skipping system call tracing..."
    exit 0
fi

cd "$PROJECT_ROOT/src" || exit

cat > /tmp/simple_lsp_test.py << 'PYEOF'
import subprocess
import json
import os
import select

# Start the Pyright language server
proc = subprocess.Popen(
    ['python', '-m', 'pyright.langserver', '--stdio'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Simple initialize request
request = {
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'initialize',
    'params': {
        'processId': os.getpid(),
        'rootUri': f'file://{os.getcwd()}',
        'capabilities': {}
    }
}

message = json.dumps(request)
msg_bytes = message.encode('utf-8')
content = f'Content-Length: {len(msg_bytes)}\r\n\r\n'.encode() + msg_bytes

proc.stdin.write(content)
proc.stdin.flush()

# Wait for response
if select.select([proc.stdout], [], [], 5)[0]:
    print('Response received')
else:
    print('Timeout waiting for response')

proc.terminate()
PYEOF

echo "Capturing system calls during LSP communication..."
echo "This may take a few seconds..."
echo ""

STRACE_OUTPUT="$OUTPUT_DIR/strace_$(date +%Y%m%d_%H%M%S).log"

if timeout 15 strace -f -e trace=read,write,poll,select \
    -o "$STRACE_OUTPUT" \
    uv run python /tmp/simple_lsp_test.py 2>&1; then
    echo -e "${GREEN}✓ Trace captured successfully${NC}"
else
    echo -e "${YELLOW}⚠ Trace completed (may have been interrupted)${NC}"
fi

echo ""
echo "Analyzing trace..."
echo ""

if [ -f "$STRACE_OUTPUT" ]; then
    echo "Key I/O operations:"
    echo "-------------------"
    
    # Count pipe operations
    PIPE_WRITES=$(grep -c "write(" "$STRACE_OUTPUT" 2>/dev/null || echo "0")
    PIPE_READS=$(grep -c "read(" "$STRACE_OUTPUT" 2>/dev/null || echo "0")
    
    echo "  Total write() calls: $PIPE_WRITES"
    echo "  Total read() calls:  $PIPE_READS"
    echo ""
    
    # Show sample of actual data written
    echo "Sample of write operations (first 5):"
    grep "write(" "$STRACE_OUTPUT" | head -5 | while read -r line; do
        echo "  $line" | cut -c1-100
    done
    echo ""
    
    echo "Sample of read operations (first 5):"
    grep "read(" "$STRACE_OUTPUT" | head -5 | while read -r line; do
        echo "  $line" | cut -c1-100
    done
    echo ""
    
    echo "Full trace saved to: $STRACE_OUTPUT"
else
    echo -e "${RED}No trace output captured${NC}"
fi

rm -f /tmp/simple_lsp_test.py

echo ""
echo "============================================================"
echo "Diagnostic Tips"
echo "============================================================"
echo ""
echo "If the issue persists, check the trace file for:"
echo "  1. EAGAIN errors: Indicates non-blocking I/O issues"
echo "  2. EPIPE errors: Indicates broken pipe (process died)"
echo "  3. Blocked read(): Process waiting for input that never arrives"
echo ""
echo "Common fixes:"
echo "  - Ensure --stdio flag is passed to language server"
echo "  - Use binary mode (not text mode) for subprocess pipes"
echo "  - Content-Length must be byte count, not character count"
