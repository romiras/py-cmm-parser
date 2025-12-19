# LSP Communication Protocol Issue - Technical Analysis

## Problem Statement

The LSP client implementation in `src/lsp_client.py` successfully detects Pyright installation but **hangs indefinitely** during the initialization phase when attempting to establish JSON-RPC communication with the Pyright language server.

## Context

### What is LSP?

The Language Server Protocol (LSP) is a JSON-RPC based protocol for communication between:
- **Client**: Our CMM parser (wants semantic information)
- **Server**: Pyright language server (provides type checking, symbol resolution, etc.)

### Communication Flow (Expected)

```
┌─────────────┐                           ┌──────────────┐
│ LSP Client  │                           │   Pyright    │
│ (Python)    │                           │ (Node.js)    │
└──────┬──────┘                           └──────┬───────┘
       │                                         │
       │  1. Start subprocess                    │
       │────────────────────────────────────────▶│
       │     python -m pyright --langserver      │
       │                                         │
       │  2. Send "initialize" request           │
       │────────────────────────────────────────▶│
       │     (JSON-RPC over stdin)               │
       │                                         │
       │  3. Receive "initialize" response       │
       │◀────────────────────────────────────────│
       │     (JSON-RPC over stdout)              │
       │                                         │
       │  4. Send "initialized" notification     │
       │────────────────────────────────────────▶│
       │                                         │
       │  5. Ready for queries                   │
       │     (textDocument/definition, etc.)     │
       │                                         │
```

## What We Implemented

### 1. Subprocess Invocation

**File**: `src/lsp_client.py:114-121`

```python
self.process = subprocess.Popen(
    ['python', '-m', 'pyright', '--langserver'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=0
)
```

**Expected**: Pyright starts in langserver mode, listening on stdin for JSON-RPC messages.

**Actual**: Process starts, but we don't know if it's in the correct mode.

### 2. Initialize Request

**File**: `src/lsp_client.py:133-147`

```python
def _initialize(self) -> bool:
    init_request = {
        "jsonrpc": "2.0",
        "id": self._next_id(),
        "method": "initialize",
        "params": {
            "processId": os.getpid(),
            "rootUri": f"file://{self.workspace_root}",
            "capabilities": {}
        }
    }
    
    response = self._send_request(init_request)
    if response and 'result' in response:
        # Send initialized notification
        self._send_notification({
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {}
        })
        return True
    return False
```

**Expected**: Pyright responds with server capabilities.

**Actual**: `_send_request()` never returns (hangs).

### 3. Message Sending

**File**: `src/lsp_client.py:240-261`

```python
def _send_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not self.process or not self.process.stdin or not self.process.stdout:
        return None
    
    try:
        message = json.dumps(request)
        content = f"Content-Length: {len(message)}\r\n\r\n{message}"
        
        self.process.stdin.write(content)
        self.process.stdin.flush()
        
        # Read response
        return self._read_response()  # ← HANGS HERE
        
    except Exception as e:
        print(f"[LSP] Request failed: {e}")
        return None
```

**Expected**: Write succeeds, `_read_response()` reads the reply.

**Actual**: Write appears to succeed, but `_read_response()` blocks forever.

### 4. Message Reading

**File**: `src/lsp_client.py:278-301`

```python
def _read_response(self) -> Optional[Dict[str, Any]]:
    if not self.process or not self.process.stdout:
        return None
    
    try:
        # Read Content-Length header
        while True:
            line = self.process.stdout.readline()  # ← BLOCKS HERE
            if line.startswith('Content-Length:'):
                length = int(line.split(':')[1].strip())
                break
        
        # Read blank line
        self.process.stdout.readline()
        
        # Read message body
        message = self.process.stdout.read(length)
        return json.loads(message)
        
    except Exception as e:
        print(f"[LSP] Failed to read response: {e}")
        return None
```

**Expected**: Pyright writes response to stdout in LSP format:
```
Content-Length: 123\r\n
\r\n
{"jsonrpc":"2.0","id":1,"result":{...}}
```

**Actual**: `readline()` blocks indefinitely, suggesting Pyright never writes to stdout.

## Test Results

### Test Execution

```bash
cd src
python test_lsp_client.py
```

**Output**:
```
============================================================
LSP Client Integration Tests
============================================================
✓ Pyright available: True
✓ Location parsing works
✓ Location list parsing works
✓ TypeInfo parsing works
^C  # Had to manually interrupt
Traceback (most recent call last):
  File "/media/Data/Projects/py-cmm-parser/src/test_lsp_client.py", line 110, in <module>
    test_lsp_lifecycle()
  File "/media/Data/Projects/py-cmm-parser/src/test_lsp_client.py", line 40, in test_lsp_lifecycle
    started = client.start()
              ^^^^^^^^^^^^^^
  File "/media/Data/Projects/py-cmm-parser/src/lsp_client.py", line 126, in start
    if self._initialize():
       ^^^^^^^^^^^^^^^^^
  File "/media/Data/Projects/py-cmm-parser/src/lsp_client.py", line 150, in _initialize
    response = self._send_request(init_request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/media/Data/Projects/py-cmm-parser/src/lsp_client.py", line 262, in _send_request
    return self._read_response()
           ^^^^^^^^^^^^^^^^^^^^^
  File "/media/Data/Projects/py-cmm-parser/src/lsp_client.py", line 290, in _read_response
    line = self.process.stdout.readline()
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
KeyboardInterrupt
```

**Analysis**: The hang occurs at `stdout.readline()`, meaning Pyright is not writing anything to stdout.

## Root Cause Hypotheses

### Hypothesis 1: Incorrect Pyright Invocation

**Issue**: `python -m pyright --langserver` may not be the correct way to start the language server.

**Evidence**:
- Pyright is a Node.js application distributed as a Python package
- The Python package is a wrapper that downloads/runs the Node.js binary
- The `--langserver` flag might not exist or might require different arguments

**Verification Needed**:
```bash
# Check available flags
python -m pyright --help

# Check if langserver mode exists
python -m pyright --langserver --help
```

**Note**: running `uv pip list` in the root directory of the project shows much more packages installed
than running `uv pip list` in the `src` directory (where the `pyright` package is installed).
Question: should we change directory to `src` then execute with prefix `uv run python -m pyright --langserver`?

When we run within `src` directory output is:
```
$ uv run python -m pyright --help
warning: `VIRTUAL_ENV=/media/Data/Projects/py-cmm-parser/.venv` does not match the project environment path `.venv` and will be ignored
Usage: pyright [options] files...
  Options:
  --createstub <IMPORT>              Create type stub file(s) for import
  --dependencies                     Emit import dependency information
  -h,--help                          Show this help message
  --ignoreexternal                   Ignore external imports for --verifytypes
  --level <LEVEL>                    Minimum diagnostic level (error or warning)
  --outputjson                       Output results in JSON format
  -p,--project <FILE OR DIRECTORY>   Use the configuration file at this location
  --pythonplatform <PLATFORM>        Analyze for a specific platform (Darwin, Linux, Windows)
  --pythonpath <FILE>                Path to the Python interpreter
  --pythonversion <VERSION>          Analyze for a specific version (3.3, 3.4, etc.)
  --skipunannotated                  Skip analysis of functions with no type annotations
  --stats                            Print detailed performance stats
  -t,--typeshedpath <DIRECTORY>      Use typeshed type stubs at this location
  --threads <optional COUNT>         Use separate threads to parallelize type checking 
  -v,--venvpath <DIRECTORY>          Directory that contains virtual environments
  --verbose                          Emit verbose diagnostics
  --verifytypes <PACKAGE>            Verify type completeness of a py.typed package
  --version                          Print Pyright version and exit
  --warnings                         Use exit code of 1 if warnings are reported
  -w,--watch                         Continue to run and watch for changes
  -                                  Read files from stdin
```

### Hypothesis 2: Missing Node.js Dependency

**Issue**: Pyright requires Node.js to run the actual language server.

**Evidence**:
- Pyright is fundamentally a TypeScript/Node.js application
- The Python package is just a launcher
- Language server mode likely requires the Node.js runtime

**Verification Needed**:
```bash
# Check if Node.js is installed
node --version

# Check if pyright-langserver binary exists
which pyright-langserver
ls ~/.local/share/pyright/
```

### Hypothesis 3: Incorrect Protocol Format

**Issue**: Our JSON-RPC message format might not match what Pyright expects.

**Evidence**:
- LSP specification has specific requirements for message format
- We're using `\r\n` line endings, but Pyright might expect `\n`
- The `Content-Length` header calculation might be off

**Current Format**:
```python
message = json.dumps(request)
content = f"Content-Length: {len(message)}\r\n\r\n{message}"
```

**Potential Issue**: `len(message)` counts characters, but LSP spec requires byte count:
```python
# Should be:
message_bytes = json.dumps(request).encode('utf-8')
content = f"Content-Length: {len(message_bytes)}\r\n\r\n{message_bytes.decode('utf-8')}"
```

### Hypothesis 4: Buffering Issue

**Issue**: We set `bufsize=0` (unbuffered), but `text=True` mode might still buffer.

**Evidence**:
- Python's text mode I/O has its own buffering layer
- Unbuffered mode works differently with text vs binary streams
- Pyright might not receive the message until buffer flushes

**Current**:
```python
self.process = subprocess.Popen(
    [...],
    text=True,
    bufsize=0
)
```

**Alternative**:
```python
self.process = subprocess.Popen(
    [...],
    text=False,  # Use binary mode
    bufsize=0
)
# Then manually encode/decode
```

### Hypothesis 5: Pyright Expects Different Initialization

**Issue**: Pyright's language server might require specific initialization parameters.

**Evidence**:
- Different LSP servers have different required capabilities
- Pyright might need specific `initializationOptions`
- The `rootUri` format might be incorrect

**Current**:
```python
"params": {
    "processId": os.getpid(),
    "rootUri": f"file://{self.workspace_root}",
    "capabilities": {}
}
```

**Potential Fix**:
```python
"params": {
    "processId": os.getpid(),
    "rootPath": self.workspace_root,  # Some servers need this
    "rootUri": f"file://{self.workspace_root}",
    "capabilities": {
        "textDocument": {
            "definition": {"dynamicRegistration": True},
            "hover": {"dynamicRegistration": True}
        }
    },
    "initializationOptions": {
        # Pyright-specific options
    }
}
```

## Debugging Steps Performed

### 1. Verified Pyright Installation
```bash
python -m pyright --version
# Output: pyright 1.1.407
```
✅ Pyright is installed and accessible.

### 2. Checked Process Creation
```python
# In _send_request(), added:
print(f"Process running: {self.process.poll() is None}")
print(f"stdin: {self.process.stdin}, stdout: {self.process.stdout}")
```
✅ Process is running, pipes are open.

### 3. Attempted Manual Communication
```bash
# Try to manually interact with Pyright
python -m pyright --langserver
# (No output, no prompt - unclear if it's waiting for input)
```
❓ Unclear if langserver mode is active.

## What We Expected vs What We Got

| Aspect | Expected | Actual |
|--------|----------|--------|
| **Process Start** | Pyright starts in langserver mode | Process starts, but mode unclear |
| **Message Send** | Write to stdin succeeds | Write appears to succeed |
| **Message Receive** | Read response from stdout | `readline()` blocks forever |
| **Error Output** | Errors written to stderr | No errors in stderr |
| **Initialization** | Returns server capabilities | Never returns |

## Recommended Solutions

### Solution 1: Use Existing LSP Library (RECOMMENDED)

Instead of implementing JSON-RPC from scratch, use a proven library:

**Option A: `pygls` (Generic LSP)**
```python
from pygls.client import LanguageClient

client = LanguageClient()
client.start_io('python', '-m', 'pyright', '--langserver')
```

**Option B: `python-lsp-jsonrpc`**
```python
from pylsp_jsonrpc.endpoint import Endpoint
from pylsp_jsonrpc.streams import JsonRpcStreamReader, JsonRpcStreamWriter

# Handles protocol details automatically
```

**Pros**:
- ✅ Proven protocol implementation
- ✅ Handles edge cases (buffering, encoding, etc.)
- ✅ Faster development

**Cons**:
- ❌ Additional dependency
- ❌ Less control over low-level details

### Solution 2: Fix Pyright Invocation

Research the correct way to start Pyright's language server:

```bash
# Check Pyright documentation
npm info pyright

# Look for langserver binary
find ~/.local -name "*pyright*" -type f

# Try alternative invocation
npx pyright-langserver --stdio
```

### Solution 3: Use Asynchronous I/O

The blocking I/O might be the issue. Use `asyncio`:

```python
import asyncio

async def _read_response_async(self):
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    
    # Non-blocking read
    line = await reader.readline()
    # ...
```

### Solution 4: Debug with Wireshark/strace

Capture actual communication to see what's happening:

```bash
# Trace system calls
strace -f -e trace=read,write python test_lsp_client.py

# Check if Pyright is writing anything
```

## Impact on Sprint 5

### What Works
- ✅ Schema migration (v0.3.1)
- ✅ Symbol mapper
- ✅ Data structures (`Location`, `TypeInfo`)
- ✅ CLI integration

### What's Blocked
- ❌ Actual LSP communication
- ❌ Deterministic dependency resolution
- ❌ Type hint extraction

### Workaround
The Lazy Linker (Sprint 4) continues to work. LSP is an **enhancement**, not a requirement.

## Next Steps for Sprint 5.2

1. **Research Pyright Langserver**
   - Read Pyright documentation
   - Check GitHub issues for langserver usage
   - Find working examples

2. **Try Existing LSP Library**
   - Prototype with `pygls`
   - Compare complexity vs custom implementation

3. **Fallback Plan**
   - If Pyright proves difficult, consider alternative LSP servers
   - Or defer LSP to later sprint, focus on other features

## References

- [LSP Specification](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/)
- [Pyright GitHub](https://github.com/microsoft/pyright)
- [pygls Documentation](https://pygls.readthedocs.io/)
- [JSON-RPC 2.0 Spec](https://www.jsonrpc.org/specification)

## For Future LLM Context

When resuming this work, the key question to answer is:

**"What is the correct command and protocol to start Pyright's language server and communicate with it via stdin/stdout?"**

The implementation is 90% correct; we just need the right invocation method.
