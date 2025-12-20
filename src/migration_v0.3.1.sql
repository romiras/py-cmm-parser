-- Migration from v0.3 to v0.3.1: LSP Integration Schema Enhancements
-- Purpose: Add columns for LSP-based deterministic linking and type enrichment

-- 1. Add symbol_hash to entities_v3 for unique LSP correlation
ALTER TABLE entities_v3 ADD COLUMN symbol_hash TEXT DEFAULT NULL;

-- 1b. Add line tracking to entities_v3 for CallSite mapping
ALTER TABLE entities_v3 ADD COLUMN line_start INTEGER DEFAULT 0;
ALTER TABLE entities_v3 ADD COLUMN line_end INTEGER DEFAULT 0;

-- 2. Add type_hint to metadata for parameter and return type information
ALTER TABLE metadata ADD COLUMN type_hint TEXT DEFAULT NULL;

-- 3. Add is_verified to relations to track LSP vs Lazy resolution
ALTER TABLE relations ADD COLUMN is_verified INTEGER DEFAULT 0;

-- 4. Create index on symbol_hash for fast lookups
CREATE INDEX IF NOT EXISTS idx_symbol_hash ON entities_v3(symbol_hash);

-- 5. Create index on is_verified for filtering queries
CREATE INDEX IF NOT EXISTS idx_is_verified ON relations(is_verified);

-- 6. Backfill is_verified=0 for existing relations (all are Lazy-resolved)
UPDATE relations SET is_verified = 0 WHERE is_verified IS NULL;

-- Migration completed: v0.3.1
-- Note: symbol_hash will be populated during next scan with LSP enabled
