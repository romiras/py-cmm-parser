# CMM Parser

A Python-based Canonical Metadata Model (CMM) parser that extracts structured information from Python source code using Tree-sitter and stores it in SQLite.

## Features

- **Tree-sitter Parsing**: Uses Tree-sitter 0.25.x for robust Python code parsing
- **Normalization**: Maps Python-specific constructs (methods, decorators) to language-neutral CMM types
- **Flexible Entity Model**: Stores classes, functions, methods, and docstrings in a flexible JSON structure
- **SQLite Storage**: Persists parsed entities with file hash tracking for efficient re-scanning
- **Directory Scanning**: Recursively scans directories for Python files
- **Lazy Resolution**: Resolves cross-file dependencies (inheritance, imports) on-demand
- **Rich CLI**: Beautiful terminal output with progress indicators and dependency tables

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
```

### Resolve Dependencies

```bash
cd src
# Show all dependencies for a file
uv run python -m cli parser resolve <file-path>

# Filter by specific entity name
uv run python -m cli parser resolve <file-path> --entity <name>

# Output as JSON graph
uv run python -m cli parser resolve <file-path> --json
```

### Inspect the Database

```bash
# View stored files and schema versions
sqlite3 src/cmm.db "SELECT file_path, schema_version FROM files;"

# Count entities by type
sqlite3 src/cmm.db "SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type;"

# View normalized entity data (v0.2)
sqlite3 src/cmm.db "SELECT entity_data FROM entities WHERE entity_type = 'function' LIMIT 1;" | python -m json.tool
```

## Architecture

### Hexagonal Architecture (Ports & Adapters)

- **Domain**: `CMMEntity` - Flexible container for parsed entities (v0.2)
- **Ports**: 
  - `ParserPort` - Interface for file parsing
  - `StoragePort` - Interface for entity storage
- **Adapters**:
  - `TreeSitterParser` - Tree-sitter implementation of ParserPort
  - `SQLiteStorage` - SQLite implementation of StoragePort
- **Services**:
  - `PythonNormalizer` - Maps Python constructs to CMM types
  - `DependencyResolver` - Resolves cross-file links using the DB

### Database Schema

**files table:**
- `id`: Primary key
- `file_path`: Absolute path to the file
- `file_hash`: MD5 hash for change detection
- `schema_version`: CMM schema version (v0.2)
- `created_at`, `updated_at`: Timestamps

**entities table:**
- `id`: Primary key
- `file_id`: Foreign key to files table
- `entity_type`: Type of entity (class, function)
- `entity_data`: JSON blob with entity details (visibility, cmm_type, dependencies, etc.)

## Development

### Project Structure

```
py-cmm-parser/
├── src/
│   ├── cli.py          # CLI commands
│   ├── domain.py       # Domain models
│   ├── parser.py       # Tree-sitter parser
│   ├── storage.py      # SQLite storage
│   ├── normalizer.py   # Normalization service
│   └── resolver.py     # Dependency resolution
└── docs/
    ├── Plan-sprint-1.md
    ├── Plan-sprint-2.md
    └── Plan-sprint-3.md
```

### Sprint Progress

- ✅ **Sprint 1**: Tree-sitter integration and CLI foundation
- ✅ **Sprint 2**: SQLite storage and directory scanning
- ✅ **Sprint 3**: Normalization and Lazy Resolution
- 🔜 **Sprint 4**: (Coming Soon)
