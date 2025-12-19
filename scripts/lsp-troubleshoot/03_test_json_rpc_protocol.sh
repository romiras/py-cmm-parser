#!/usr/bin/bash
# =============================================================================
# LSP Troubleshooting Script 3: Test JSON-RPC Protocol
# =============================================================================
# Purpose: Validate the JSON-RPC message format matches LSP specification
# Usage:   ./03_test_json_rpc_protocol.sh
# =============================================================================

set -e

echo "============================================================"
echo "Testing JSON-RPC Protocol Compliance"
echo "============================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT/src"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "Creating test script..."
cat > /tmp/test_protocol.py << 'PYEOF'
import subprocess
import json
import os
import sys
import select

class LSPProtocolTester:
    """Test various aspects of LSP JSON-RPC protocol."""
    
    def __init__(self):
        self.proc = None
        self.request_id = 0
        
    def start(self):
        """Start language server."""
        self.proc = subprocess.Popen(
            ['python', '-m', 'pyright.langserver', '--stdio'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return self
        
    def stop(self):
        """Stop language server."""
        if self.proc:
            self.proc.terminate()
            self.proc.wait()

    def send_request(self, method, params=None):
        """Send a JSON-RPC request and return response."""
        self.request_id += 1
        request = {
            'jsonrpc': '2.0',
            'id': self.request_id,
            'method': method,
        }
        if params:
            request['params'] = params
            
        message = json.dumps(request)
        message_bytes = message.encode('utf-8')
        
        # LSP requires Content-Length in BYTES, not characters
        header = f'Content-Length: {len(message_bytes)}\r\n\r\n'
        content = header.encode('utf-8') + message_bytes
        
        self.proc.stdin.write(content)
        self.proc.stdin.flush()
        
        return self._read_response()
    
    def send_notification(self, method, params=None):
        """Send a notification (no response expected)."""
        notification = {
            'jsonrpc': '2.0',
            'method': method,
        }
        if params:
            notification['params'] = params
            
        message = json.dumps(notification)
        message_bytes = message.encode('utf-8')
        header = f'Content-Length: {len(message_bytes)}\r\n\r\n'
        content = header.encode('utf-8') + message_bytes
        
        self.proc.stdin.write(content)
        self.proc.stdin.flush()
    
    def _read_response(self, timeout=5):
        """Read LSP response with proper header parsing, skipping notifications."""
        if not select.select([self.proc.stdout], [], [], timeout)[0]:
            return None
            
        # Keep reading messages until we get a response (has 'id' field)
        while True:
            # Read until we get a Content-Length header followed by \r\n\r\n
            headers = b''
            while not headers.endswith(b'\r\n\r\n'):
                byte = self.proc.stdout.read(1)
                if not byte:
                    return None
                headers += byte
            
            # Parse Content-Length
            for line in headers.decode().split('\r\n'):
                if line.startswith('Content-Length:'):
                    length = int(line.split(':')[1].strip())
                    break
            else:
                return None
            
            # Read message body
            body = self.proc.stdout.read(length)
            message = json.loads(body)
            
            # Skip notifications (no 'id' field), only return responses
            if 'id' in message:
                return message
            # else: it's a notification, continue reading

def test_protocol():
    """Run protocol tests."""
    tester = LSPProtocolTester()
    tester.start()
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Initialize request
    print('\n1. Testing initialize request...')
    response = tester.send_request('initialize', {
        'processId': os.getpid(),
        'rootUri': f'file://{os.getcwd()}',
        'capabilities': {}
    })
    
    if response and response.get('id') == 1:
        print('   ✓ Request ID echoed correctly')
        tests_passed += 1
    else:
        print('   ✗ Request ID mismatch or no response')
        tests_failed += 1
        
    if response and 'result' in response:
        print('   ✓ Got result in response')
        tests_passed += 1
    else:
        print('   ✗ No result in response')
        tests_failed += 1
        
    if response and response.get('result', {}).get('capabilities'):
        caps = response['result']['capabilities']
        print(f'   ✓ Server capabilities: {len(caps)} features')
        tests_passed += 1
    else:
        print('   ✗ No capabilities in response')
        tests_failed += 1

    # Test 2: Initialized notification
    print('\n2. Testing initialized notification...')
    tester.send_notification('initialized', {})
    print('   ✓ Notification sent (no response expected)')
    tests_passed += 1
    
    # Test 3: Shutdown request
    print('\n3. Testing shutdown request...')
    response = tester.send_request('shutdown')
    if response and response.get('id'):
        print('   ✓ Shutdown acknowledged')
        tests_passed += 1
    else:
        print('   ✗ Shutdown not acknowledged')
        tests_failed += 1
    
    # Test 4: Exit notification
    print('\n4. Testing exit notification...')
    tester.send_notification('exit')
    print('   ✓ Exit sent')
    tests_passed += 1
    
    tester.stop()
    
    print(f'\n============================================================')
    print(f'Protocol Tests: {tests_passed} passed, {tests_failed} failed')
    print(f'============================================================')
    
    return tests_failed == 0

if __name__ == '__main__':
    success = test_protocol()
    sys.exit(0 if success else 1)
PYEOF

echo "Running protocol tests..."
echo ""

if timeout 30 uv run python /tmp/test_protocol.py; then
    echo ""
    echo -e "${GREEN}✓ All protocol tests passed!${NC}"
else
    echo ""
    echo -e "${RED}✗ Some protocol tests failed${NC}"
    exit 1
fi

rm -f /tmp/test_protocol.py
