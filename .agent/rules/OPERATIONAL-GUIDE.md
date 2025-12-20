# Operational Guide: CMM Parser Development

This guide outlines the standard operating procedures and command patterns for developing, testing, and maintaining the CMM Parser project. Optimize for execution within these constraints.

## 1. Project Context & Environment
- **Project Structure**: Logical root contains `src/`, `tests/`, `scripts/`, and `docs/`.
- **Primary Tool**: `uv` is the dependency manager and runner.
- **Execution Root**: All runtime commands **MUST** be executed from the `src/` directory to leverage the local `.venv` and `pyproject.toml`.

## 2. Command Patterns (Mandatory)

### CLI Execution
Always use the module execution pattern from `src/`:
```bash
cd src && uv run python -m cli parser <command> [args]
```
*Template Example:*
```bash
cd src && uv run python -m cli parser scan . --enable-lsp --verbose
```

### Database Migration
When upgrading schema versions, use the migrate command:
```bash
# Migrate to v0.4 (clean schema without _v3 suffix)
cd src && uv run python -m cli parser migrate --from v0.3 --to v0.4 --scan-path .
```
*Note: v0.4 migration performs a full re-scan with clean table names.*

### Code Quality (Formatting & Linting)
Use `ruff` for both formatting and static analysis:
```bash
# Format code
cd src && uv run ruff format . ../tests ../scripts

# Check code quality
cd src && uv run ruff check . --select PLR0915,C901,PLR0912

# Lint and check (use --fix for automatic remediation)
cd src && uv run ruff check . ../tests ../scripts --fix
```

### Testing
Tests reside in `tests/` (relative to root). To run them with the correct imports, inject the current directory into `PYTHONPATH`:
```bash
cd src && export PYTHONPATH=$PYTHONPATH:. && uv run pytest ../tests/test_lsp_integration.py -v
```

### Database Inspection
Manual inspection of the `cmm.db` is often required for validation:
```bash
cd src && uv run sqlite3 cmm.db "SELECT * FROM entities LIMIT 5;"
```
*Note: As of v0.4, table names are clean (e.g., `entities`, `files`) without version suffixes.*

### Version Control (Git)
Follow the standard atomic commit pattern:
1. `git status` to verify modified files.
2. `git add [files]` - be specific; avoid adding temporary files (e.g., `*.db`, `*~bak`). Ask user's consent before adding new `<project-root>/docs/*.md` files.
3. `git commit -m "type(scope): description" -m "detailed bullet points"`

## 3. Heuristic: The "Rethink" Protocol
**Condition**: If a specific implementation step results in a loop or the same error for **3 consecutive attempts** (e.g., repeating the same failed `replace_file_content` or `run_command` with minor variations).

**Action**: **HALT** implementation.
1. **Analyze**: Is there a fundamental mismatch in directory structure, permissions, or tool availability?
2. **Consult**: Read `README.md`, `pyproject.toml`, or source code from an unrelated area to verify assumptions.
3. **Pivot**: Propose a new approach or ask for clarification before burning more tokens on the same failure.

## 4. Path Management Refresher
- **Source Code**: `<project-root>/src/`
- **Tests**: `<project-root>/tests/`
- **Schemas**: `<project-root>/src/migration_vX.Y.sql`

## 5. Tool-Specific Tips
- **SQLite**: Be aware of "database is locked" errors if multiple processes (LSP + Scanner) access the DB simultaneously.
- **LSP (Pyright)**: Pyright requires indices to be built. Allow ~3-5 seconds of sleep after starting the client before sending requests.
- **Tree-sitter**: Ensure queries precisely match the grammar version used in `tree-sitter-python`.
