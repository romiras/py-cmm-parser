-- Migration script from v0.2 (2 tables) to v0.3 (Relational-Graph)

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- 1. Create new FILES table (v3)
CREATE TABLE IF NOT EXISTS files_v3 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v0.3',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Create ENTITIES table (Hierarchy)
CREATE TABLE IF NOT EXISTS entities_v3 (
    id TEXT PRIMARY KEY,          -- UUID
    name TEXT NOT NULL,
    type TEXT NOT NULL,           -- module, class, function
    visibility TEXT NOT NULL,     -- public, private
    parent_id TEXT,               -- NULL for top-level, foreign key for nested
    FOREIGN KEY (parent_id) REFERENCES entities_v3(id) ON DELETE CASCADE
);

-- 3. Create METADATA table (Language-agnostic details)
CREATE TABLE IF NOT EXISTS metadata (
    entity_id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    raw_docstring TEXT,
    signature TEXT,               -- Function/method signature
    cmm_type TEXT,                -- Constructor, Method, Display, etc.
    method_kind TEXT,             -- static, class, instance
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES entities_v3(id) ON DELETE CASCADE
);

-- 4. Create RELATIONS table (Dependencies)
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,
    to_id TEXT,                   -- NULL if unresolved (Lazy Linking)
    to_name TEXT NOT NULL,        -- String name for lazy resolution
    rel_type TEXT NOT NULL,       -- calls, inherits, imports, depends_on
    FOREIGN KEY (from_id) REFERENCES entities_v3(id) ON DELETE CASCADE,
    FOREIGN KEY (to_id) REFERENCES entities_v3(id) ON DELETE SET NULL
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_files_v3_path ON files_v3(file_path);
CREATE INDEX IF NOT EXISTS idx_entities_v3_parent ON entities_v3(parent_id);
CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_id);
CREATE INDEX IF NOT EXISTS idx_relations_to_name ON relations(to_name);
