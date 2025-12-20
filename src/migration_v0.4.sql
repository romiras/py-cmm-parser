-- Migration to v0.4: Clean Schema (removes _v3 suffix)
-- Purpose: Consolidate v0.3 + v0.3.1 into a clean schema without version suffixes
-- Note: This is a fresh start migration. Old data will be dropped.

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- Drop old tables (if they exist)
DROP TABLE IF EXISTS relations;
DROP TABLE IF EXISTS metadata;
DROP TABLE IF EXISTS entities_v3;
DROP TABLE IF EXISTS files_v3;

-- 1. Create FILES table (clean name)
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v0.4',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Create ENTITIES table (Hierarchy + LSP enhancements)
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,          -- UUID
    name TEXT NOT NULL,
    type TEXT NOT NULL,           -- module, class, function
    visibility TEXT NOT NULL,     -- public, private
    parent_id TEXT,               -- NULL for top-level, foreign key for nested
    symbol_hash TEXT DEFAULT NULL,  -- LSP correlation (v0.3.1)
    line_start INTEGER DEFAULT 0,   -- LSP line tracking (v0.3.1)
    line_end INTEGER DEFAULT 0,     -- LSP line tracking (v0.3.1)
    FOREIGN KEY (parent_id) REFERENCES entities(id) ON DELETE CASCADE
);

-- 3. Create METADATA table (Language-agnostic details + type hints)
CREATE TABLE IF NOT EXISTS metadata (
    entity_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    raw_docstring TEXT,
    signature TEXT,               -- Function/method signature
    cmm_type TEXT,                -- Constructor, Method, Display, etc.
    method_kind TEXT,             -- static, class, instance
    type_hint TEXT DEFAULT NULL,  -- LSP type enrichment (v0.3.1)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

-- 4. Create RELATIONS table (Dependencies + verification tracking)
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,
    to_id TEXT,                   -- NULL if unresolved (Lazy Linking)
    to_name TEXT NOT NULL,        -- String name for lazy resolution
    rel_type TEXT NOT NULL,       -- calls, inherits, imports, depends_on
    is_verified INTEGER DEFAULT 0, -- LSP verification flag (v0.3.1)
    FOREIGN KEY (from_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (to_id) REFERENCES entities(id) ON DELETE SET NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_files_path ON files(file_path);
CREATE INDEX IF NOT EXISTS idx_entities_parent ON entities(parent_id);
CREATE INDEX IF NOT EXISTS idx_entities_symbol_hash ON entities(symbol_hash);
CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_id);
CREATE INDEX IF NOT EXISTS idx_relations_to_name ON relations(to_name);
CREATE INDEX IF NOT EXISTS idx_relations_verified ON relations(is_verified);

-- Unique constraint for UPSERT support (Sprint 5.3)
CREATE UNIQUE INDEX IF NOT EXISTS idx_relations_unique ON relations(from_id, to_name, rel_type);

-- Migration completed: v0.4
-- Schema now includes all v0.3 + v0.3.1 features with clean table names
