#!/usr/bin/bash
# =============================================================================
# LSP Troubleshooting Script 4: Test Definition Lookup
# =============================================================================
# Purpose: Test actual textDocument/definition functionality
# Usage:   ./04_test_definition_lookup.sh [FILE] [LINE] [COLUMN]
# Example: ./04_test_definition_lookup.sh src/parser.py 10 15
# =============================================================================

set -e

echo "============================================================"
echo "Testing textDocument/definition Lookup"
echo "============================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT/src"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Default test file if not specified
TEST_FILE="${1:-$PROJECT_ROOT/src/parser.py}"
TEST_LINE="${2:-1}"
TEST_COLUMN="${3:-0}"

if [ ! -f "$TEST_FILE" ]; then
    echo -e "${RED}Error: File not found: $TEST_FILE${NC}"
    exit 1
fi

echo "Test file: $TEST_FILE"
echo "Position:  Line $TEST_LINE, Column $TEST_COLUMN"
echo ""

cat > /tmp/test_definition.py << 'PYEOF'
import subprocess
import json
import os
import sys
import select

class LSPClient:
    """Minimal LSP client for testing definition lookup."""
    
    def __init__(self, workspace_root):
        self.workspace_root = workspace_root
        self.proc = None
        self.request_id = 0
        
    def start(self):
        self.proc = subprocess.Popen(
            ['python', '-m', 'pyright.langserver', '--stdio'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        # Initialize
        response = self._request('initialize', {
            'processId': os.getpid(),
            'rootUri': f'file://{self.workspace_root}',
            'capabilities': {
                'textDocument': {
                    'definition': {'dynamicRegistration': True}
                }
            }
        })
        
        if response and 'result' in response:
            self._notify('initialized', {})
            return True
        return False
        
    def stop(self):
        if self.proc:
            self._request('shutdown')
            self._notify('exit')
            self.proc.terminate()
            self.proc.wait()

    def open_document(self, file_path):
        """Notify server that document is open."""
        with open(file_path, 'r') as f:
            content = f.read()
        
        uri = f'file://{os.path.abspath(file_path)}'
        self._notify('textDocument/didOpen', {
            'textDocument': {
                'uri': uri,
                'languageId': 'python',
                'version': 1,
                'text': content
            }
        })
        return uri
    
    def get_definition(self, uri, line, character):
        """Get definition at position."""
        response = self._request('textDocument/definition', {
            'textDocument': {'uri': uri},
            'position': {'line': line, 'character': character}
        })
        return response.get('result') if response else None

    def _request(self, method, params=None):
        self.request_id += 1
        request = {'jsonrpc': '2.0', 'id': self.request_id, 'method': method}
        if params:
            request['params'] = params
            
        message = json.dumps(request)
        msg_bytes = message.encode('utf-8')
        header = f'Content-Length: {len(msg_bytes)}\r\n\r\n'
        
        self.proc.stdin.write((header.encode() + msg_bytes))
        self.proc.stdin.flush()
        
        return self._read_response()
    
    def _notify(self, method, params=None):
        notification = {'jsonrpc': '2.0', 'method': method}
        if params:
            notification['params'] = params
            
        message = json.dumps(notification)
        msg_bytes = message.encode('utf-8')
        header = f'Content-Length: {len(msg_bytes)}\r\n\r\n'
        
        self.proc.stdin.write((header.encode() + msg_bytes))
        self.proc.stdin.flush()
    
    def _read_response(self, timeout=10):
        """Read response, skipping server notifications."""
        while True:
            if not select.select([self.proc.stdout], [], [], timeout)[0]:
                return None
            
            headers = b''
            while not headers.endswith(b'\r\n\r\n'):
                byte = self.proc.stdout.read(1)
                if not byte:
                    return None
                headers += byte
            
            for line in headers.decode().split('\r\n'):
                if line.startswith('Content-Length:'):
                    length = int(line.split(':')[1].strip())
                    break
            
            body = self.proc.stdout.read(length)
            response = json.loads(body)
            
            # Skip notifications (no 'id' field)
            if 'id' in response:
                return response

def main():
    file_path = sys.argv[1]
    line = int(sys.argv[2]) - 1  # Convert to 0-based
    character = int(sys.argv[3])
    workspace = sys.argv[4]
    
    print(f'Opening LSP connection to workspace: {workspace}')
    print('')
    
    client = LSPClient(workspace)
    if not client.start():
        print('Failed to start LSP client')
        sys.exit(1)
    
    print('Opening document...')
    uri = client.open_document(file_path)
    
    print(f'Looking up definition at {file_path}:{line+1}:{character}')
    print('')
    
    result = client.get_definition(uri, line, character)
    
    if result:
        print('Definition found:')
        if isinstance(result, list):
            for loc in result:
                print(f"  URI: {loc.get('uri', loc.get('targetUri', 'unknown'))}")
                if 'range' in loc:
                    r = loc['range']
                    print(f"  Range: {r['start']['line']+1}:{r['start']['character']} - {r['end']['line']+1}:{r['end']['character']}")
                elif 'targetRange' in loc:
                    r = loc['targetRange']
                    print(f"  Range: {r['start']['line']+1}:{r['start']['character']} - {r['end']['line']+1}:{r['end']['character']}")
        else:
            print(f'  Result: {json.dumps(result, indent=2)}')
    else:
        print('No definition found at this position')
    
    client.stop()
    print('')
    print('Done.')

if __name__ == '__main__':
    main()
PYEOF

echo "Starting LSP client for definition lookup..."
echo ""

if timeout 30 uv run python /tmp/test_definition.py "$TEST_FILE" "$TEST_LINE" "$TEST_COLUMN" "$PROJECT_ROOT/src"; then
    echo -e "${GREEN}✓ Definition lookup test completed${NC}"
else
    echo -e "${RED}✗ Definition lookup test failed${NC}"
    exit 1
fi

rm -f /tmp/test_definition.py
