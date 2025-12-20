# CMM Parser

A Python-based Canonical Metadata Model (CMM) parser that extracts structured information from Python source code using Tree-sitter and stores it in SQLite.

## Features

- **Tree-sitter Parsing**: Uses Tree-sitter 0.25.x for robust Python code parsing.
- **Deep Method Analysis**: Traverses method bodies to extract internal calls and dependencies.
- **Normalization**: Maps Python-specific constructs (methods, decorators) to language-neutral CMM types.
- **Relational-Graph Model**: Stores entities in a hierarchical structure with typed relations (**v0.4**).
- **Semantic Layer**: High-fidelity LSP client foundation for deterministic linking via Pyright.
- **Hybrid Resolution**: Combines fast lazy resolution with compiler-grade accuracy for verified links.
- **Rich CLI**: Beautiful terminal output with progress indicators and typed dependency tables.

## Installation

```bash
# Install dependencies (using uv)
cd src
uv sync
```

## Usage

### Scan a Single File

```bash
cd src
uv run python -m cli parser scan-file <file-path>

# Example
uv run python -m cli parser scan-file parser.py

# JSON output
uv run python -m cli parser scan-file parser.py --json
```

### Scan a Directory

```bash
cd src
uv run python -m cli parser scan <directory-path>

# Example: scan current directory
uv run python -m cli parser scan .

# With verbose output
uv run python -m cli parser scan . --verbose

# Specify database location
uv run python -m cli parser scan . --db-path /path/to/database.db

# LSP-Enhanced Scanning (Deterministic Linking)
# Requires Pyright: uv add --dev pyright
uv run python -m cli parser scan . --enable-lsp

# With verbose output to see resolution details
uv run python -m cli parser scan . --enable-lsp --verbose
```

**LSP Benefits** (when `--enable-lsp` is used):
- 95%+ resolution accuracy (vs. 40-60% with lazy linking)
- Cross-file calls verified by Pyright
- Type hints captured from hover information
- Relations marked as `is_verified=1` in database

**Performance**: ~2-3x slower than syntax-only scan, but acceptable for accuracy gain.

### Resolve Dependencies

```bash
cd src
# Show all dependencies for a file (including call graph)
uv run python -m cli parser resolve <file-path>

# Filter by specific entity name
uv run python -m cli parser resolve <file-path> --entity <name>

# Output as JSON graph
uv run python -m cli parser resolve <file-path> --json
```

### Migrate Database

```bash
cd src
# Migrate from v0.3 to v0.4 (Full re-scan, clean table names)
uv run python -m cli parser migrate --from v0.3 --to v0.4 --scan-path .
```

**Supported Migration Paths**:
- **v0.2 → v0.3**: Full re-scan (backup, delete old DB, re-scan with new schema)
- **v0.3 → v0.4**: Full re-scan (clean schema without `_v3` suffix)
- **v0.3.1 → v0.4**: Full re-scan (clean schema without `_v3` suffix)

### Inspect the Database (v0.4)

```bash
# View stored files and schema versions
sqlite3 src/cmm.db "SELECT file_path, schema_version FROM files;"

# Count entities by type
sqlite3 src/cmm.db "SELECT type, COUNT(*) FROM entities GROUP BY type;"

# View relations (calls, inherits)
sqlite3 src/cmm.db "SELECT from_id, to_name, rel_type FROM relations LIMIT 10;"
```

## Testing

The project uses `pytest` for testing. All test commands should be executed from the `src/` directory to ensure proper dependency loading via `uv`.

### Run All Tests
```bash
cd src
export PYTHONPATH=$PYTHONPATH:.
uv run pytest .. -v
```

### Run Specific Test Suites

**Unit Tests (Parser, Storage, LSP Client)**:
```bash
cd src
uv run pytest test_sqlite_storage.py -v
uv run pytest test_lsp_client.py -v
```

**Integration Tests**:
```bash
cd src
PYTHONPATH=. uv run pytest ../tests/test_lsp_integration.py -v
```

## Architecture

### Hexagonal Architecture (Ports & Adapters)

- **Domain**: `CMMEntity` - Hierarchical container for parsed entities (**v0.4**)
- **Ports**: 
  - `ParserPort` - Interface for file parsing
  - `StoragePort` - Interface for entity storage
- **Adapters**:
  - `TreeSitterParser` - Tree-sitter implementation with deep traversal
  - `SQLiteStorage` - Relational SQLite implementation
- **Services**:
  - `PythonNormalizer` - Maps Python constructs to CMM types
  - `DependencyResolver` - Resolves cross-file links using the Relational DB

### Database Schema (v0.4 - Clean)

- **entities**: Stores hierarchy (Modules, Classes, Methods) via `parent_id`.
- **metadata**: Language-agnostic metadata linked to entities (docstrings, signatures, CMM types, type hints).
- **relations**: Captures "calls", "inherits", or "depends_on" with LSP verification tracking.
- **files**: Change detection and schema version tracking.

## Development

### Project Structure

```
py-cmm-parser/
├── src/      # Core logic, adapters, and CLI
├── tests/    # Unit and integration test suites
├── scripts/  # LSP troubleshooting and diagnostic tools
├── docs/     # Planning, architecture, and sprint solutions
└── vendor/   # Third-party dependencies and grammars
```

### Sprint Progress

- ✅ **Sprint 1**: Tree-sitter integration and CLI foundation
- ✅ **Sprint 2**: SQLite storage and directory scanning
- ✅ **Sprint 3**: Normalization and Lazy Resolution
- ✅ **Sprint 4**: Schema Migration & Deep Method Analysis
- ⚙️ **Sprint 5**: LSP Integration & Schema Polish
  - ✅ v0.4 clean schema (removed `_v3` suffixes)
  - ✅ Unified migration command (v0.2→v0.3, v0.3→v0.4)
  - ✅ LSP client with Pyright integration
  - ✅ Type enrichment via hover information

## Latest Updates

### v0.4 Clean Schema

Sprint 5 completed with a transition to a clean schema (v0.4), removing all version suffixes (`_v3`) for improved codebase health.

**Highlights**:
- `entities.symbol_hash` - Unique identifier for LSP correlation
- `metadata.type_hint` - Parameter and return type information
- `relations.is_verified` - Boolean flag for LSP-validated links

**Migrate to Clean Schema**:
```bash
cd src
uv run python -m cli parser migrate --from v0.3 --to v0.4 --scan-path .
```

This upgrade enables deterministic dependency linking via Pyright (95%+ accuracy vs 60-80% with Lazy Linker).


## Future Enhancements (Next Steps)

- **Import Tracking**: Implement explicit tracking of module imports to enable full dependency graph visualization.
- **Enhanced Call Extraction**: Improve the parser to capture chained calls (e.g., `self.storage.save()`) and qualified attribute accesses.
- **Function Signatures**: Parse and store parameters, return types, and type hints for richer metadata.
- **Edge Case Coverage**: Expand support for lambda functions, list comprehensions, and asynchronous constructs.
- **Graph Visualization**: Export dependency data to Graphviz or Mermaid format for visual architectural mapping.
- **Multi-language Support**: Extend the `ParserPort` to support other languages like Go or JavaScript using their respective Tree-sitter grammars.
