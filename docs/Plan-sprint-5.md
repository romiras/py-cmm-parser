# Sprint 5: LSP Integration for Deterministic Dependency Linking

## Executive Summary

Sprint 5 introduces **Language Server Protocol (LSP)** integration via Pyright to upgrade from "Lazy Linking" (name-based guessing) to "Deterministic Linking" (compiler-grade resolution). This enhancement maintains backward compatibility with Sprint 4's foundation while adding semantic analysis capabilities.

**Key Decision Drivers**:
- ✅ **Accuracy over Speed**: Reverse-engineering complex dependencies requires 95%+ resolution accuracy
- ✅ **Polyglot Readiness**: LSP abstraction prepares for Go/Java support in upcoming sprints
- ✅ **Hybrid Approach**: Keep Lazy Linker as fallback for environments without Pyright

---

## Comparative Analysis: Lazy vs Deterministic Linking

| Aspect | Sprint 4 (Lazy) | Sprint 5 (LSP-Enhanced) |
|--------|-----------------|-------------------------|
| **Resolution Accuracy** | 60-80% (name-based guessing) | 95-99% (compiler-grade) |
| **Cross-File Linking** | Manual resolution needed | Automatic via Pyright |
| **Implementation Complexity** | Low (Tree-sitter only) | High (LSP client + protocol) |
| **Performance** | Fast (single-pass scan) | Slower (LSP roundtrips per call) |
| **External Dependencies** | None | Requires Pyright installed |
| **Type Information** | ❌ Not captured | ✅ Full type hints available |
| **Ambiguity Handling** | ⚠️ Stores multiple matches | ✅ Resolves to exact definition |
| **Polyglot Extensibility** | Same Tree-sitter per language | Higher (LSP abstraction layer) |

---

## Architecture Evolution

### Current Architecture (Sprint 4)
```
┌─────┐
│ CLI │
└──┬──┘
   │
   ▼
┌──────────────┐
│ Tree-sitter  │ (Syntax + Structure)
│   Parser     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   SQLite     │
│  (v0.3 DB)   │
└──────────────┘
```

### Enhanced Architecture (Sprint 5)
```
┌─────┐
│ CLI │
└──┬──┘
   │
   ▼
┌────────────────────┐
│   Orchestrator     │ (Coordinates syntax + semantics)
└─────────┬──────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
┌──────────┐ ┌──────────────┐
│Tree-     │ │ LSP Client   │
│sitter    │ │ (Pyright)    │
│(Syntax)  │ │ (Semantics)  │
└────┬─────┘ └──────┬───────┘
     │              │
     └──────┬───────┘
            ▼
    ┌───────────────┐
    │ Symbol Mapper │ (Correlates Tree-sitter → LSP → UUIDs)
    └───────┬───────┘
            ▼
    ┌───────────────┐
    │    SQLite     │
    │ (Enhanced DB) │
    └───────────────┘
```

---

## Phase 1: Schema Enhancement (v0.3 → v0.3.1)

### New Columns

#### `entities_v3` Table
```sql
ALTER TABLE entities_v3 ADD COLUMN symbol_hash TEXT;
-- Purpose: Unique identifier (SHA256 of file_uri + qualified_name)
-- Example: sha256("file:///src/parser.py#TreeSitterParser.scan_file")
```

#### `metadata` Table
```sql
ALTER TABLE metadata ADD COLUMN type_hint TEXT DEFAULT NULL;
-- Purpose: Store parameter and return type information
-- Example: "Dict[str, Any]" or "(file_path: str) -> CMMEntity"
```

#### `relations` Table
```sql
ALTER TABLE relations ADD COLUMN is_verified BOOLEAN DEFAULT 0;
-- Purpose: Track whether link was resolved by LSP (1) or Lazy Linker (0)
-- Enables querying: "Show only LSP-verified dependencies"
```

### Migration Strategy
1. Create migration script `migration_v0.3.1.sql`
2. Backfill `is_verified=0` for all existing relations
3. Generate `symbol_hash` for existing entities based on file path + name
4. No data loss - purely additive changes

---

## Phase 2: LSP Client Implementation & Protocol Fix

### Component: `src/lsp_client.py`

**Responsibilities**:
1. **Launch Pyright sidecar process**: Use `python -m pyright.langserver --stdio` (Critical: `pyright` CLI wrapper does not support persistent stdio mode).
2. **Binary Communication**: Use binary mode for I/O pipes to handle raw JSON-RPC bytes.
3. **JSON-RPC Protocol Handling**:
   - Calculate `Content-Length` in **bytes** (UTF-8 encoding) to avoid protocol desync.
   - Implement notification skipping: Ignore server noise (logging, diagnostics) to focus on request responses with matching IDs.
4. **Lifecycle Management**: Implement `initialize` -> `initialized` handshake.

**Automated Troubleshooting Suite (`scripts/lsp-troubleshoot/`)**:
- `01_check_prerequisites.sh`: Verify Node.js/Pyright.
- `02_test_langserver_invocation.sh`: Test server startup.
- `03_test_json_rpc_protocol.sh`: Validate header/body formatting.
- `04_test_definition_lookup.sh`: End-to-end lookup test.

**Protocol Example (Fixed)**:
```json
// Header (Bytes)
Content-Length: 142\r\n\r\n

// Body (Request)
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "textDocument/definition",
  "params": {
    "textDocument": {"uri": "file:///path/to/parser.py"},
    "position": {"line": 42, "character": 15}
  }
}
```

### Error Handling
- **Pyright not installed**: Gracefully fall back to Lazy Linker.
- **Protocol Desync**: Detect malformed headers and reconnect/fallback.
- **Ambiguous symbols**: Trust LSP result (it uses type inference).

---

## Phase 3: Parser Integration (Hybrid Mode)

### Updated Flow in `parser.py`

**Step 1: Tree-sitter Scan** (Existing)
```python
# Extract call at line 42, column 15: "self._internal_logic()"
call_info = {
    "name": "_internal_logic",
    "line": 42,
    "character": 15,
    "file_uri": "file:///path/to/main.py"
}
```

**Step 2: LSP Resolution** (New)
```python
if lsp_client.is_available():
    definition = lsp_client.get_definition(
        call_info["file_uri"], 
        call_info["line"], 
        call_info["character"]
    )
    
    if definition:
        # Deterministic linking
        target_entity = storage.find_by_location(
            definition["uri"], 
            definition["range"]["start"]["line"]
        )
        
        relation = {
            "from_id": current_entity_id,
            "to_id": target_entity.id,
            "to_name": call_info["name"],
            "rel_type": "calls",
            "is_verified": True  # LSP-validated
        }
    else:
        # Fallback to Lazy Linker
        relation = {
            "from_id": current_entity_id,
            "to_id": None,
            "to_name": call_info["name"],
            "rel_type": "calls",
            "is_verified": False  # Unverified
        }
else:
    # No LSP available - use Lazy Linker
    relation = lazy_linker.resolve(call_info["name"])
```

---

## Phase 4: Symbol Mapper Service

### Component: `src/symbol_mapper.py`

**Purpose**: Correlate LSP locations to CMM entity UUIDs

**Key Methods**:
1. `find_by_location(file_uri: str, line: int) -> Entity`
   - Query: `SELECT id FROM entities_v3 WHERE file_path = ? AND line_start <= ? AND line_end >= ?`
2. `generate_symbol_hash(file_uri: str, qualified_name: str) -> str`
   - SHA256 hash for deduplication
3. `cache_location_to_uuid(location: Location, entity_id: UUID)`
   - In-memory cache to avoid repeated DB lookups

---

## Phase 5: Type-Enriched Metadata

### Capturing Type Hints

When scanning a method definition:
```python
def process_data(self, items: List[Dict[str, Any]]) -> bool:
    """Process data items."""
    pass
```

**Without LSP** (Sprint 4):
```json
{
  "name": "process_data",
  "cmm_type": "Method",
  "signature": "process_data(self, items)"
}
```

**With LSP** (Sprint 5):
```json
{
  "name": "process_data",
  "cmm_type": "Method",
  "signature": "process_data(self, items)",
  "type_hint": "(items: List[Dict[str, Any]]) -> bool"
}
```

**Implementation**:
```python
# After parsing method signature
if lsp_client.is_available():
    hover_info = lsp_client.get_hover(file_uri, line, char)
    if hover_info and "signature" in hover_info:
        entity["type_hint"] = hover_info["signature"]
```

---

## Phased Rollout
 
### Sprint 5.1: Foundation (Complete)
- ✅ Implement schema changes (v0.3.1 migration).
- ✅ Create LSP client skeleton and data structures.
- ✅ Add migration logic to CLI (`migrate-lsp`).

### Sprint 5.2: Protocol & Troubleshooting (Complete)
- ✅ Resolve Pyright invocation issue (`pyright.langserver --stdio`).
- ✅ Implement binary-mode JSON-RPC handling.
- ✅ Create automated troubleshooting suite (`scripts/lsp-troubleshoot/`).
- ✅ Establish documentation for protocol fixes.
- ✅ Implement `SymbolMapper` service.

### Sprint 5.3: Integration (Timebox: 3 Days)
**Goal**: Wire `LSPClient` into the scanning workflow to produce verified relations.

**Challenge**: "Forward Reference" problem. During a fresh scan, referenced files may not be in the DB yet, so `SymbolMapper` can't link to UUIDs.
**Solution**: Implement a **Two-Pass Strategy** in the `scan` command.
1. **Pass 1 (Syntax)**: Standard Tree-sitter scan. storage.upsert() all entities.
2. **Pass 2 (Semantics)**: If `--enable-lsp` is active, re-iterate files, resolving calls via LSP and linking to the now-populated DB.

**Tasks**:
- [ ] **LSP Lifecycle Management**: Update `CLI` to manage LSP process (start on generic scan, shutdown on exit).
- [ ] **Parser Updates**: Add `resolve_dependencies(file_path, lsp_client)` method to `TreeSitterParser` (or separate service) that:
    - Re-parses calls.
    - Queries LSP `textDocument/definition`.
    - Uses `SymbolMapper` to find target `to_id`.
- [ ] **Storage Updates**: Add `update_relation_verification(from_id, to_id, is_verified)` method.
- [ ] **CLI Wiring**: Update `scan` command to orchestrate the Two-Pass approach.

### Sprint 5.4: Type Enrichment & Validation (Timebox: 3 Days)
**Goal**: Capture type signatures and validate the end-to-end value.

**Tasks**:
- [ ] **Type Capture**: Use `lsp_client.get_hover()` in the "Pass 2" loop to extract signatures/docstrings and update `metadata.type_hint`.
- [ ] **Benchmarks**: Run head-to-head comparison (LSP vs Lazy) on:
    - Resolution Accuracy (Manual spot check of 20 complex cases).
    - Performance (Time overhead of Pass 2).
- [ ] **Documentation**: Write `sprint-5-SOLUTION.md` with "Lesson Learned: The Two-Pass Necessity".
- [ ] **Final Polish**: Ensure robust error handling (e.g., if LSP crashes mid-scan).

---

## Success Criteria Status

- **Functional**: 
  - ✅ LSP client successfully handshakes with Pyright (16 capabilities detected).
  - ✅ `SymbolMapper` service implemented and ready.
  - ⏳ 95% resolution accuracy (Dependent on Sprint 5.3).
  - ⏳ Type hint capture (Dependent on Sprint 5.4).
- **Protocol**:
  - ✅ Robust JSON-RPC over stdio (binary-safe).
  - ✅ Server notification filtering.
  - ✅ Automatic troubleshooting scripts pass.

---

## Risk Mitigation

| Risk | Mitigation Strategy |
|------|---------------------|
| **Pyright installation complexity** | Provide auto-detection + clear error messages with install instructions |
| **LSP protocol breaking changes** | Pin Pyright version in requirements, test with specific version |
| **Performance degradation** | Implement aggressive caching, make LSP opt-in via flag initially |
| **Cross-platform issues** | Test on Linux, macOS, Windows (WSL) |
| **Memory leaks from sidecar** | Implement process lifecycle management with timeouts |

---

## CLI Enhancements

### New Commands

```bash
# Enable LSP for scanning (opt-in initially)
uv run python -m cli parser scan ./src --enable-lsp

# Check LSP status
uv run python -m cli parser lsp-status
# Output: 
#   LSP Client: Active
#   Pyright Version: 1.1.350
#   Indexed Files: 42
#   Resolution Rate: 97.3%

# Compare Lazy vs LSP results
uv run python -m cli parser resolve main.py --compare-modes
# Output: Shows side-by-side comparison of dependency resolution
```

### Updated Commands

```bash
# Show only LSP-verified dependencies
uv run python -m cli parser resolve main.py --verified-only

# Show unresolved (Lazy Linker fallback) dependencies
uv run python -m cli parser resolve main.py --unverified-only

# Display type hints in output
uv run python -m cli parser resolve main.py --show-types
```

---

## Polyglot Preparation

The LSP abstraction layer sets the foundation for future language support:

| Language | LSP Server | Sprint Timeline |
|----------|-----------|-----------------|
| Python | Pyright (Sprint 5) | ✅ Current |
| Go | `gopls` | Sprint 6-7 |
| Java | Eclipse JDT LS | Sprint 8-9 |
| TypeScript | `tsserver` | Sprint 10+ |

**Abstraction Pattern**:
```python
# src/lsp_adapter.py (Sprint 5)
class LSPAdapter(Protocol):
    def get_definition(self, uri, line, char) -> Location: ...
    def get_hover(self, uri, line, char) -> TypeInfo: ...

# src/lsp_pyright.py (Sprint 5)
class PyrightAdapter(LSPAdapter):
    # Python-specific implementation
    pass

# src/lsp_gopls.py (Sprint 6 - Future)
class GoplsAdapter(LSPAdapter):
    # Go-specific implementation
    pass
```

---

## Git Strategy

Continue frequent commits with descriptive messages:
- `feat(schema): add LSP-ready columns to v0.3.1 schema`
- `feat(lsp): implement Pyright client wrapper`
- `feat(parser): add hybrid LSP + Lazy resolution mode`
- `feat(types): capture type hints via LSP hover`
- `test: add LSP integration test suite`
- `docs: create Sprint 5 solution walkthrough`

---

## Dependencies

### Python Packages
```toml
# pyproject.toml additions
[tool.uv.dependencies]
pyright = "^1.1.407"  # Pin to latest stable version
```

### System Requirements
- Node.js 16+ (Pyright dependency)
- 2GB+ RAM (Pyright workspace indexing)

### Development Tools
- `pytest-asyncio` for LSP client tests
- Mock LSP server for unit testing

---

## Next Steps After Sprint 5

### Sprint 6: Advanced Graph Queries
- Export CMM to graph format (NetworkX, GraphML)
- Implement dependency impact analysis
- Visualize call graphs with type annotations

### Sprint 7: Go Language Support
- Implement `gopls` LSP adapter
- Extend schema for Go-specific constructs (interfaces, goroutines)
- Unified CMM for Python + Go codebases

---

## Conclusion

Sprint 5 represents a **significant architectural upgrade** while maintaining full backward compatibility. The hybrid LSP + Lazy approach ensures the tool works in all environments while maximizing accuracy where possible.

**Key Advantages**:
- 🎯 95%+ dependency resolution accuracy (vs 60-80% in Sprint 4)
- 🔧 Type-enriched metadata for better program analysis
- 🌐 Polyglot-ready architecture for upcoming languages
- 🔄 Zero breaking changes - opt-in enhancement

**User Impact**:
- More accurate reverse engineering of complex codebases
- Ability to distinguish between ambiguous symbols
- Foundation for advanced features (impact analysis, refactoring suggestions)
