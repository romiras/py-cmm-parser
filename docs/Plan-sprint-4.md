## Sprint 4: Schema Migration & Deep Method Analysis (Weeks 7-8)

Implementing the Rosetta vision with a normalized relational-graph schema, deep method body traversal, and polyglot-ready architecture.

### Phase 1: Database Schema Evolution (v0.2 → v0.3)

**The "Big Bang" Migration Strategy**

We are moving from a 2-table JSON-blob design to a 3-table relational-graph structure for better scalability and polyglot readiness.

**Old Schema (v0.2)**:
- `files`: File metadata + schema version
- `entities`: JSON blobs containing entity data

**New Schema (v0.3)**:
- `entities_v3`: Hierarchical structure (id, name, type, visibility, parent_id)
- `metadata`: Language-agnostic metadata (file_path, docstring, signature, cmm_type)
- `relations`: Typed dependencies (from_id, to_id, to_name, rel_type)
- `files_v3`: File tracking with hash-based change detection

**Why This Matters**:
- **Polyglot Proficiency**: The new schema separates language-specific concerns (in Metadata) from universal structure (in Entities)
- **Explicit Relations**: The Relations table enables lazy resolution with typed links (inherits, calls, imports)
- **Query Efficiency**: Normalized data reduces redundancy and enables faster joins

### Phase 2: Deep Method Body Traversal

**The "Method Body" Strategy (Revisited)**

While we **do not store** method bodies, we **must traverse** them to extract internal calls. This is critical for building accurate dependency graphs.

**Implementation**:
1. Extend Tree-sitter queries to capture `call` expressions within method bodies
2. Walk the AST to identify function/method invocations
3. Store extracted calls in Relations table with `rel_type = 'calls'`
4. Add debug logging (via `CMM_DEBUG=1` env var) to troubleshoot parser logic without bloating the database

**Example**:
```python
def process_order(self):
    user = self.get_user()      # Internal call → Relations entry
    self.validate(user)         # Internal call → Relations entry
    return user
```

**Relations Table Entries**:
```
from_id: process_order, to_name: get_user, rel_type: calls
from_id: process_order, to_name: validate, rel_type: calls
```

### Phase 3: Enhanced Dependency Resolution

**The "Lazy Linker" Evolution**

The new Relations table enables more precise dependency tracking:

- **Unresolved Dependencies**: Initially stored with `to_id = NULL`, `to_name = "SomeClass"`
- **Resolution**: A background service queries Entities table to find matching `to_name` and updates `to_id`
- **Typed Relations**: Each dependency has a `rel_type` (inherits, calls, imports, depends_on)

**CLI Enhancement**:
```bash
# Show all dependencies with relation types
uv run python -m cli parser resolve myfile.py

# Batch resolve all unresolved links
uv run python -m cli parser resolve-all
```

---

## Implementation Plan Snapshot (Sprint 4)

| Task | Outcome | Constraint Check |
| --- | --- | --- |
| **Schema Migration** | 3-table relational-graph structure | O(N) one-time migration cost |
| **Migration Command** | Auto-backup + safe migration path | Zero data loss |
| **Body Traversal** | Extract internal calls from methods | O(M) for M methods per file |
| **Typed Relations** | Explicit dependency semantics | Enables advanced graph queries |
| **UUID Entity IDs** | Unique, portable identifiers | Python `uuid.uuid4()` |

---

## Efficiency & Risk Check

* **Complexity**: Schema migration is a one-time O(N) operation. New queries benefit from indexes on foreign keys.
* **Risk (Data Loss)**: Mitigated by auto-backup strategy. Old database saved as `cmm.db.v0.2.backup` before migration.
* **Risk (Parsing Errors)**: Body traversal failures degrade gracefully—if call extraction fails, entity is still saved without call relations.
* **Trade-off**: Normalized schema improves query performance but increases write complexity (3 tables vs. 1).

---

## Phased Rollout

### Sprint 4.1: Foundation (Days 1-2)
- Implement new schema in `storage.py`
- Add UUID generation
- Create migration SQL script

### Sprint 4.2: Parser Enhancement (Days 3-4)
- Implement method body traversal logic
- Add Tree-sitter call extraction queries
- Test call detection in isolation

### Sprint 4.3: Integration (Days 5-6)
- Wire parser → Relations table
- Implement migration command
- Update resolver to use Relations table

### Sprint 4.4: Validation (Days 7-8)
- Comprehensive test suite
- Migrate real codebase for testing
- Performance benchmarking
- Documentation updates

---

## Success Criteria

- ✅ Migration command successfully converts v0.2 → v0.3 with zero data loss
- ✅ Parser extracts internal calls from method bodies
- ✅ Relations table populated with typed dependencies (inherits, calls)
- ✅ `resolve` command displays relation types
- ✅ All tests pass (unit, integration, migration)
- ✅ Documentation reflects v0.3 schema

---

## Git

Continue committing frequently. Use descriptive commit messages for each phase:
- `feat: implement v0.3 schema migration`
- `feat: add method body traversal for call extraction`
- `feat: add migration command with auto-backup`
- `test: add comprehensive migration test suite`
