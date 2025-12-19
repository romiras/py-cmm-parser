# LSP Fix - Quick Reference Card

## 🚨 The Problem
LSP client hangs when trying to communicate with Pyright

## ✅ The Fix

### One-Line Change
```python
# In src/lsp_client.py line ~114
['python', '-m', 'pyright.langserver', '--stdio']  # ← Add .langserver and --stdio
```

### Full Fix (3 changes needed)

#### 1. Subprocess Command
```python
# BEFORE
subprocess.Popen(['python', '-m', 'pyright', '--langserver'], ...)

# AFTER  
subprocess.Popen(['python', '-m', 'pyright.langserver', '--stdio'], ...)
```

#### 2. Binary Mode
```python
# BEFORE
text=True, bufsize=0

# AFTER
# Remove text=True, use binary mode (default)
```

#### 3. Content-Length in Bytes
```python
# BEFORE
message = json.dumps(request)
content = f"Content-Length: {len(message)}\r\n\r\n{message}"

# AFTER
message = json.dumps(request)
message_bytes = message.encode('utf-8')
header = f"Content-Length: {len(message_bytes)}\r\n\r\n"
content = header.encode('utf-8') + message_bytes
```

## 🧪 Quick Test

```bash
# Run automated tests
cd scripts/lsp-troubleshoot
./run_all.sh --quick

# Or test manually
cd src
uv run python test_lsp_client.py
```

## 📖 Full Documentation

- **Summary**: `docs/LSP-ISSUE-SUMMARY.md`
- **Detailed Analysis**: `docs/LSP-PROTOCOL-ISSUE.md`
- **Complete Solution**: `docs/LSP-PROTOCOL-ISSUE-SOLUTION.md`
- **Script Guide**: `scripts/lsp-troubleshoot/README.md`

## 💰 AI Model Recommendations

| Task | Model |
|------|-------|
| Apply this fix | Sonnet/GPT-4o mini ⚡ |
| New debugging | Opus/GPT-4 🧠 |
| Run scripts | No AI needed 🤖 |

---
**TL;DR**: Change `pyright --langserver` → `pyright.langserver --stdio`
