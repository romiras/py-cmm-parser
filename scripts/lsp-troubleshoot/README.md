# LSP Troubleshooting Scripts - User Guide

## Overview

This directory contains automated troubleshooting scripts for diagnosing and fixing LSP (Language Server Protocol) communication issues with Pyright.

**Created**: 2025-12-19  
**Session**: LSP Protocol Issue Diagnosis and Resolution  
**Status**: ✅ Complete - All tests passing

## Quick Start

```bash
cd scripts/lsp-troubleshoot
chmod +x *.sh

# Run all checks in quick mode
./run_all.sh --quick

# Run with verbose strace diagnostics
./run_all.sh --verbose
```

## Documentation Suite

All documentation created during this troubleshooting session is located in `docs/`:

### For Human Readers

| Document | Purpose | When to Read |
|----------|---------|--------------|
| **LSP-PROTOCOL-ISSUE.md** | Original detailed analysis of the hanging issue | Understanding the problem context |
| **LSP-PROTOCOL-ISSUE-SOLUTION.md** | Complete solution with code fixes | Applying the fix to similar issues |
| **LSP-FIX-QUICKREF.md** | Quick reference card | Fast lookup during implementation |
| **LSP-ISSUE-SUMMARY.md** | Executive summary with AI model recommendations | Project overview and decision-making |
| **LSP-FIX-APPLIED.md** | Final completion report with test results | Verification and handoff |

### For LLM Comprehension

When an AI model needs to understand this LSP issue in future sessions, the documents serve these purposes:

#### 1. **LSP-PROTOCOL-ISSUE.md** - Problem Context
- **Purpose**: Provides complete diagnostic history
- **Contains**: 
  - Communication flow diagrams
  - Implementation details with line numbers
  - Test results showing the hang
  - 5 hypotheses about root cause
  - Debugging steps performed
- **LLM Use Case**: Understanding "what was tried" and "why it failed"
- **Key Insight**: Documents the journey from symptom to diagnosis

#### 2. **LSP-PROTOCOL-ISSUE-SOLUTION.md** - Implementation Guide
- **Purpose**: Canonical fix documentation
- **Contains**:
  - Root cause explanation
  - Before/after code comparisons
  - Three critical code changes
  - Verification steps
- **LLM Use Case**: Applying the fix or similar fixes
- **Key Insight**: The "how to fix it" reference

#### 3. **LSP-FIX-QUICKREF.md** - Fast Reference
- **Purpose**: One-page cheat sheet
- **Contains**:
  - The problem in one line
  - The fix in one line
  - Quick test commands
- **LLM Use Case**: Quick context loading for simple queries
- **Key Insight**: Minimal token consumption for routine tasks

#### 4. **LSP-ISSUE-SUMMARY.md** - Strategic Overview
- **Purpose**: Executive summary with AI model economics
- **Contains**:
  - Problem/solution summary
  - Impact analysis (before/after)
  - AI model selection guidance
  - Cost optimization strategies
- **LLM Use Case**: Understanding when to use premium vs. lighter models
- **Key Insight**: Meta-knowledge about efficient AI usage

#### 5. **LSP-FIX-APPLIED.md** - Completion Report
- **Purpose**: Final status and test results
- **Contains**:
  - All changes made
  - Test results (unit + integration)
  - Deliverables checklist
  - Success metrics
- **LLM Use Case**: Verifying work completion and handoff
- **Key Insight**: "What was actually done" vs. "what was planned"

### Document Relationships

```
LSP-PROTOCOL-ISSUE.md (Problem Analysis)
         ↓
LSP-PROTOCOL-ISSUE-SOLUTION.md (Solution Design)
         ↓
LSP-FIX-QUICKREF.md (Quick Reference)
         ↓
LSP-FIX-APPLIED.md (Implementation)
         ↓
LSP-ISSUE-SUMMARY.md (Strategic Summary)
```

**For Future LLM Sessions:**
- Start with `LSP-FIX-QUICKREF.md` for quick context
- Read `LSP-PROTOCOL-ISSUE-SOLUTION.md` for implementation details
- Consult `LSP-PROTOCOL-ISSUE.md` only if debugging similar issues
- Use `LSP-ISSUE-SUMMARY.md` for AI model selection decisions

## Scripts Description

### 1. `01_check_prerequisites.sh`

**Purpose**: Verify all required dependencies are installed

**Checks**:
- ✓ Node.js installation and version (>= 14)
- ✓ Python 3 and UV package manager
- ✓ Pyright package and CLI
- ✓ Virtual environment setup

**When to use**: First step when setting up or debugging LSP issues

```bash
./01_check_prerequisites.sh
```

**Exit codes**:
- `0`: All prerequisites satisfied
- `1`: Some prerequisites missing

---

### 2. `02_test_langserver_invocation.sh`

**Purpose**: Identify the correct command to start Pyright's language server

**Tests**:
- ✗ Wrong: `python -m pyright --langserver` (flag doesn't exist!)
- ✓ Correct: `python -m pyright.langserver --stdio`

**When to use**: When the language server doesn't start or hangs

```bash
./02_test_langserver_invocation.sh
```

**What it validates**:
- Server starts and accepts connections
- Initialize request/response cycle works
- Server capabilities are received

---

### 3. `03_test_json_rpc_protocol.sh`

**Purpose**: Validate JSON-RPC message format compliance

**Tests**:
- Initialize request/response (with notification skipping)
- Initialized notification
- Shutdown request
- Exit notification

**When to use**: When messages are sent but no response is received

```bash
./03_test_json_rpc_protocol.sh
```

**Key validation**:
- Content-Length is in bytes (not characters)
- Headers use `\r\n` line endings
- Server notifications are properly skipped

---

### 4. `04_test_definition_lookup.sh`

**Purpose**: Test actual `textDocument/definition` functionality

**Usage**:
```bash
# Default test (uses parser.py)
./04_test_definition_lookup.sh

# Custom file and position
./04_test_definition_lookup.sh /path/to/file.py LINE COLUMN
```

**Example**:
```bash
./04_test_definition_lookup.sh ../src/parser.py 50 10
```

**When to use**: To verify LSP is working end-to-end

**What it tests**:
- Document opening notification
- Definition lookup request
- Response parsing

---

### 5. `05_diagnose_strace.sh`

**Purpose**: Deep system call tracing for I/O debugging

**Requires**: `strace` (install with `sudo apt install strace`)

**Output**: Trace file saved to `test_results/lsp_diagnostics/`

**When to use**: As a last resort for debugging pipe/buffering issues

```bash
./05_diagnose_strace.sh
```

**What it captures**:
- All `read()` and `write()` system calls
- Pipe I/O operations
- Potential blocking or buffering issues

---

### 6. `run_all.sh`

**Purpose**: Run all scripts in sequence

**Options**:
- `--quick`: Skip definition lookup test (~30s faster)
- `--verbose`: Include strace diagnostics (requires strace)

```bash
# Full suite (~1 minute)
./run_all.sh

# Quick check (~30 seconds)
./run_all.sh --quick

# Full with extra diagnostics (~1.5 minutes)
./run_all.sh --verbose
```

**Exit codes**:
- `0`: All tests passed
- `1`: One or more tests failed

## Output Locations

- Strace logs: `test_results/lsp_diagnostics/strace_YYYYMMDD_HHMMSS.log`

## Troubleshooting Common Issues

### "Node.js not installed"
```bash
# Using asdf
asdf install nodejs 20.18.3
asdf global nodejs 20.18.3

# Or via package manager
sudo apt install nodejs npm
```

### "Pyright not found"
```bash
cd src
uv add pyright
uv sync
```

### "Language server hangs"
1. Run `./02_test_langserver_invocation.sh`
2. Check if using the correct command: `python -m pyright.langserver --stdio`
3. Verify binary mode is used (not text mode)
4. Ensure notification skipping is implemented in `_read_response()`

### "No response from server"
1. Run `./03_test_json_rpc_protocol.sh`
2. Check Content-Length header is in bytes, not characters
3. Ensure `\r\n` line endings in headers
4. Verify server notifications are being skipped

### "Definition lookup fails"
1. Ensure document is opened with `textDocument/didOpen` notification
2. Check file URI format: `file:///absolute/path/to/file.py`
3. Verify line/character positions are 0-based
4. Run `./04_test_definition_lookup.sh` with verbose output

## Integration with CI/CD

These scripts can be integrated into CI pipelines:

```yaml
# GitHub Actions example
jobs:
  lsp-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - uses: astral-sh/setup-uv@v4
      - run: cd src && uv sync
      - run: ./scripts/lsp-troubleshoot/run_all.sh --quick
```

## When to Switch to a Lighter AI Model

For routine troubleshooting tasks, consider using a lighter AI model when:

| Task | Model Recommendation | Reason |
|------|---------------------|---------|
| Running these scripts | No AI needed | Scripts are fully automated |
| Reading script output | Lighter model (Claude Sonnet, GPT-4o mini) | Simple interpretation |
| Interpreting errors | Lighter model | Well-documented error patterns |
| Applying documented fixes | Lighter model | Solution already documented |
| Debugging new/undocumented issues | Premium model (Claude Opus, GPT-4) | Requires deep analysis |
| Architectural decisions | Premium model | Requires strategic thinking |
| Complex multi-file refactoring | Premium model | High complexity |

**Cost Optimization**: Using lighter models for routine tasks can save ~90% on API costs while maintaining quality.

## Script Maintenance

All scripts pass **shellcheck** validation. When modifying:

```bash
# Validate changes
shellcheck scripts/lsp-troubleshoot/*.sh

# Test individually
./scripts/lsp-troubleshoot/01_check_prerequisites.sh

# Test full suite
./scripts/lsp-troubleshoot/run_all.sh --quick
```

## Related Documentation

### In This Repository
- [LSP-PROTOCOL-ISSUE.md](../../docs/LSP-PROTOCOL-ISSUE.md) - Original issue analysis
- [LSP-PROTOCOL-ISSUE-SOLUTION.md](../../docs/LSP-PROTOCOL-ISSUE-SOLUTION.md) - Complete solution
- [LSP-FIX-QUICKREF.md](../../docs/LSP-FIX-QUICKREF.md) - Quick reference card
- [LSP-ISSUE-SUMMARY.md](../../docs/LSP-ISSUE-SUMMARY.md) - Executive summary
- [LSP-FIX-APPLIED.md](../../docs/LSP-FIX-APPLIED.md) - Completion report

### External References
- [LSP Specification](https://microsoft.github.io/language-server-protocol/)
- [Pyright GitHub](https://github.com/microsoft/pyright)
- [Pyright Python Wrapper](https://github.com/RobertCraigie/pyright-python)
- [JSON-RPC 2.0 Spec](https://www.jsonrpc.org/specification)

---

**Session Summary**: This troubleshooting suite was created to diagnose and fix an LSP communication issue where the Pyright language server was hanging indefinitely. The root cause was an incorrect invocation command (`pyright --langserver` instead of `pyright.langserver --stdio`). All scripts and documentation were created in a single session on 2025-12-19.
