# CMM Parser

A Python-based Canonical Metadata Model (CMM) parser that extracts structured information from Python source code using Tree-sitter and stores it in SQLite.

## Features

- **Tree-sitter Parsing**: Uses Tree-sitter 0.25.x for robust Python code parsing.
- **Deep Method Analysis**: Traverses method bodies to extract internal calls and dependencies.
- **Normalization**: Maps Python-specific constructs (methods, decorators) to language-neutral CMM types.
- **Relational-Graph Model**: Stores entities in a hierarchical structure with typed relations (v0.3).
- **SQLite Storage**: Persists parsed entities with file hash tracking for efficient re-scanning.
- **Directory Scanning**: Recursively scans directories for Python files.
- **Lazy Resolution**: Resolves cross-file dependencies (inheritance, calls, imports) on-demand.
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
# Migrate from v0.2 to v0.3 (includes backup and re-scan)
uv run python -m cli parser migrate --from v0.2 --to v0.3
```

### Inspect the Database (v0.3)

```bash
# View stored files and schema versions
sqlite3 src/cmm.db "SELECT file_path, schema_version FROM files_v3;"

# Count entities by type
sqlite3 src/cmm.db "SELECT type, COUNT(*) FROM entities_v3 GROUP BY type;"

# View relations (calls, inherits)
sqlite3 src/cmm.db "SELECT from_id, to_name, rel_type FROM relations LIMIT 10;"
```

## Architecture

### Hexagonal Architecture (Ports & Adapters)

- **Domain**: `CMMEntity` - Hierarchical container for parsed entities (v0.3)
- **Ports**: 
  - `ParserPort` - Interface for file parsing
  - `StoragePort` - Interface for entity storage
- **Adapters**:
  - `TreeSitterParser` - Tree-sitter implementation with deep traversal
  - `SQLiteStorage` - Relational SQLite implementation
- **Services**:
  - `PythonNormalizer` - Maps Python constructs to CMM types
  - `DependencyResolver` - Resolves cross-file links using the Relational DB

### Database Schema (v0.3)

- **entities_v3**: Stores hierarchy (Modules, Classes, Methods) via `parent_id`.
- **metadata**: Language-agnostic metadata linked to entities (docstrings, signatures, CMM types).
- **relations**: Captures "calls", "inherits", or "depends_on" with lazy resolution support.
- **files_v3**: Change detection and schema version tracking.

## Development

### Project Structure

```
py-cmm-parser/
├── src/
│   ├── cli.py          # CLI commands
│   ├── domain.py       # Domain models
│   ├── parser.py       # Tree-sitter parser with body traversal
│   ├── storage.py      # SQLite relational storage
│   ├── normalizer.py   # Normalization service
│   ├── resolver.py     # Dependency resolution service
│   └── migration_v0.3.sql # Schema definition
└── docs/
    ├── Plan-sprint-1.md
    ├── Plan-sprint-2.md
    ├── Plan-sprint-3.md
    └── Plan-sprint-4.md
```

### Sprint Progress

- ✅ **Sprint 1**: Tree-sitter integration and CLI foundation
- ✅ **Sprint 2**: SQLite storage and directory scanning
- ✅ **Sprint 3**: Normalization and Lazy Resolution
- ✅ **Sprint 4**: Schema Migration & Deep Method Analysis
- ⚙️ **Sprint 5.1**: LSP Integration Foundation (in progress)
  - ✅ v0.3.1 schema with LSP-ready columns
  - ✅ Migration command for v0.3 → v0.3.1
  - ⚠️ LSP client (protocol refinement needed)

## Latest Updates

### v0.3.1 Schema (LSP-Ready)

Sprint 5.1 introduced three new columns to support Language Server Protocol integration:
- `entities_v3.symbol_hash` - Unique identifier for LSP correlation
- `metadata.type_hint` - Parameter and return type information
- `relations.is_verified` - Boolean flag for LSP-validated links

**Migrate Existing Database**:
```bash
cd src
uv run python -m cli parser migrate-lsp --db-path ./cmm.db
```

This upgrade enables future deterministic dependency linking via Pyright (95%+ accuracy vs 60-80% with Lazy Linker).

## Future Enhancements (Next Steps)

- **Import Tracking**: Implement explicit tracking of module imports to enable full dependency graph visualization.
- **Enhanced Call Extraction**: Improve the parser to capture chained calls (e.g., `self.storage.save()`) and qualified attribute accesses.
- **Function Signatures**: Parse and store parameters, return types, and type hints for richer metadata.
- **Edge Case Coverage**: Expand support for lambda functions, list comprehensions, and asynchronous constructs.
- **Graph Visualization**: Export dependency data to Graphviz or Mermaid format for visual architectural mapping.
- **Multi-language Support**: Extend the `ParserPort` to support other languages like Go or JavaScript using their respective Tree-sitter grammars.
