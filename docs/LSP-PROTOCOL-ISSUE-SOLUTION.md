# LSP Protocol Issue - SOLUTION

## 🎯 Root Cause Identified

The issue was a **incorrect Pyright invocation command**. 

| What we used | What should be used |
|--------------|---------------------|
| `python -m pyright --langserver` | `python -m pyright.langserver --stdio` |

## 📋 Technical Explanation

### Why `--langserver` Doesn't Work

1. **Pyright Python package** (`pip install pyright`) is a Python wrapper around the Node.js-based Pyright
2. Running `python -m pyright --help` shows **no `--langserver` flag** - it simply doesn't exist!
3. The Pyright Python package has a **separate module** for the language server:
   - `pyright/cli.py` - For normal pyright CLI (type checking)
   - `pyright/langserver.py` - For the Language Server Protocol

### The Correct Invocation

```python
# WRONG (what we had)
subprocess.Popen(['python', '-m', 'pyright', '--langserver'], ...)

# CORRECT (what it should be)
subprocess.Popen(['python', '-m', 'pyright.langserver', '--stdio'], ...)
```

### Key Points

1. **Module path**: `pyright.langserver` not `pyright`
2. **Flag required**: `--stdio` must be passed (tells server to use stdin/stdout)
3. **Binary mode**: Use `text=False` for proper buffering control
4. **Content-Length**: Must be byte count, not character count (UTF-8)

## 🔧 Code Fix

### File: `src/lsp_client.py`

#### Change 1: Subprocess Invocation (around line 114-121)

```python
# BEFORE
self.process = subprocess.Popen(
    ['python', '-m', 'pyright', '--langserver'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=0
)

# AFTER
self.process = subprocess.Popen(
    ['python', '-m', 'pyright.langserver', '--stdio'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    # Binary mode for proper LSP protocol handling
    # bufsize=0 is only effective with binary mode
)
```

#### Change 2: Message Encoding (around line 108)

```python
# BEFORE
message = json.dumps(request)
content = f"Content-Length: {len(message)}\r\n\r\n{message}"
self.process.stdin.write(content)

# AFTER
message = json.dumps(request)
message_bytes = message.encode('utf-8')
header = f"Content-Length: {len(message_bytes)}\r\n\r\n"
content = header.encode('utf-8') + message_bytes
self.process.stdin.write(content)
```

#### Change 3: Response Reading (around line 137)

```python
# BEFORE (text mode)
line = self.process.stdout.readline()

# AFTER (binary mode, with proper header parsing)
# Read headers until \r\n\r\n
headers = b''
while not headers.endswith(b'\r\n\r\n'):
    byte = self.process.stdout.read(1)
    if not byte:
        return None
    headers += byte

# Parse Content-Length
for line in headers.decode().split('\r\n'):
    if line.startswith('Content-Length:'):
        length = int(line.split(':')[1].strip())
        break

# Read exact number of bytes
body = self.process.stdout.read(length)
return json.loads(body.decode('utf-8'))
```

## ✅ Verification

After applying the fix, run the test:

```bash
cd src
uv run python test_lsp_client.py
```

Expected output:
```
============================================================
LSP Client Integration Tests
============================================================
✓ Pyright available: True
✓ Location parsing works
✓ Location list parsing works
✓ TypeInfo parsing works
✓ LSP lifecycle works
✓ Definition lookup works
============================================================
All tests passed!
```

## 🧪 Troubleshooting Scripts

Created automated scripts in `scripts/lsp-troubleshoot/`:

| Script | Purpose |
|--------|---------|
| `01_check_prerequisites.sh` | Verify Node.js, Python, Pyright installation |
| `02_test_langserver_invocation.sh` | Test correct server startup command |
| `03_test_json_rpc_protocol.sh` | Validate JSON-RPC message format |
| `04_test_definition_lookup.sh` | Test actual code navigation |
| `05_diagnose_strace.sh` | Deep I/O debugging with strace |
| `run_all.sh` | Execute all tests in sequence |

### Quick Test

```bash
cd scripts/lsp-troubleshoot
chmod +x *.sh
./run_all.sh --quick
```

## 📚 References

- [Pyright Python package source](https://github.com/RobertCraigie/pyright-python)
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [JSON-RPC 2.0 Spec](https://www.jsonrpc.org/specification)

## 🎓 Lessons Learned

1. **Don't assume CLI flags** - always check `--help` or source code
2. **Python wrappers may have separate modules** - `pyright` ≠ `pyright.langserver`
3. **Binary mode is essential** for proper buffering control with subprocess pipes
4. **Content-Length must be in bytes** not characters (matters for non-ASCII)
