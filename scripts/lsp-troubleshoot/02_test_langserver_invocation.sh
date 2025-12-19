#!/usr/bin/bash
# =============================================================================
# LSP Troubleshooting Script 2: Test Language Server Invocation
# =============================================================================
# Purpose: Verify the correct command to start Pyright language server
# Usage:   ./02_test_langserver_invocation.sh
# =============================================================================

set -e

echo "============================================================"
echo "Testing Pyright Language Server Invocation"
echo "============================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT/src"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Test 1: WRONG invocation (what was documented)"
echo "------------------------------------------------"
echo "Command: python -m pyright --langserver"
echo ""
if uv run python -m pyright --help 2>&1 | grep -q "\-\-langserver"; then
    echo -e "${RED}The --langserver flag exists but doesn't work as expected${NC}"
else
    echo -e "${YELLOW}The --langserver flag is NOT listed in help:${NC}"
    echo ""
    uv run python -m pyright --help 2>&1 | grep -E "^\s{2}-" | head -10
    echo "   ... (truncated)"
fi
echo ""

echo "Test 2: CORRECT invocation for language server"
echo "------------------------------------------------"
echo "Command: python -m pyright.langserver --stdio"
echo ""
echo "Testing if it starts and accepts connections..."

# Create a temporary test script
cat > /tmp/test_langserver.py << 'PYEOF'
import subprocess
import json
import os
import sys
import select

# Start the Pyright language server with --stdio
proc = subprocess.Popen(
    ['python', '-m', 'pyright.langserver', '--stdio'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

# Construct initialize request
init_request = {
    'jsonrpc': '2.0',
    'id': 1,
    'method': 'initialize',
    'params': {
        'processId': os.getpid(),
        'rootUri': f'file://{os.getcwd()}',
        'capabilities': {}
    }
}

# Encode as JSON-RPC over LSP
message = json.dumps(init_request)
message_bytes = message.encode('utf-8')
content = f'Content-Length: {len(message_bytes)}\r\n\r\n'.encode('utf-8') + message_bytes

# Send
proc.stdin.write(content)
proc.stdin.flush()

# Try to read response with timeout, skipping notifications
if select.select([proc.stdout], [], [], 5)[0]:
    # Keep reading messages until we get a response (has 'id' field)
    while True:
        # Read Content-Length header
        header = b''
        while True:
            byte = proc.stdout.read(1)
            if not byte:
                print('ERROR: Connection closed')
                sys.exit(1)
            header += byte
            if header.endswith(b'\r\n\r\n'):
                break
        
        # Parse Content-Length
        length = int(header.decode().split(':')[1].strip().split('\r')[0])
        
        # Read message body
        body = proc.stdout.read(length)
        response = json.loads(body)
        
        # Skip notifications (no 'id' field), only process responses
        if 'id' not in response:
            continue  # It's a notification, skip it
        
        # Got a response with 'id'
        if 'result' in response:
            print('SUCCESS: Language server responded!')
            print(f'Server capabilities detected: {len(response["result"]["capabilities"])} capabilities')
            sys.exit(0)
        else:
            print(f'ERROR: Unexpected response: {response}')
            sys.exit(1)
else:
    print('ERROR: No response within 5 seconds')
    stderr = proc.stderr.read()
    print(f'Stderr: {stderr.decode()}')
    sys.exit(1)

proc.terminate()
PYEOF

if timeout 10 uv run python /tmp/test_langserver.py; then
    echo -e "${GREEN}✓ Language server invocation works correctly!${NC}"
else
    echo -e "${RED}✗ Language server invocation failed${NC}"
    exit 1
fi
echo ""

echo "Test 3: Available transport modes"
echo "------------------------------------------------"
echo "The Pyright language server supports these modes:"
echo "  --stdio       : Use stdin/stdout (recommended for scripting)"
echo "  --node-ipc    : Use Node.js IPC (for Node.js clients)"
echo "  --socket=PORT : Use TCP socket (for network clients)"
echo ""
echo -e "${GREEN}✓ Use --stdio for Python-based LSP clients${NC}"
echo ""

echo "============================================================"
echo "DIAGNOSIS COMPLETE"
echo "============================================================"
echo ""
echo "ROOT CAUSE IDENTIFIED:"
echo "  The lsp_client.py uses: python -m pyright --langserver"
echo "  But it should use:      python -m pyright.langserver --stdio"
echo ""
echo "FIX: Update the subprocess invocation in lsp_client.py:"
echo "  FROM: ['python', '-m', 'pyright', '--langserver']"
echo "  TO:   ['python', '-m', 'pyright.langserver', '--stdio']"
echo ""

rm -f /tmp/test_langserver.py
