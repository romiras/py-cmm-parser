## Sprint 3: Normalization & Lazy Resolution (Weeks 5-6)

Now that the data is in the database, we must turn "raw code signatures" into "Architectural Intent".

### Phase 1: The Normalizer

* **Language-Neutral Mapping**: Convert Python-specific identifiers (like `__init__`) into generic CMM terms (like `Constructor`).
* **Visibility Logic**: Add a flag to your extraction logic to distinguish between public and private methods, preparing for future filtering.

### Phase 2: The Lazy Resolver

* **Symbol Capture**: When scanning a file, store "unresolved" dependencies (e.g., a class inherited from another module) as raw strings.
* **Assembly**: Create a service that queries the SQLite DB to link these strings to actual entities in other files, forming the basis for a dependency graph.

---

## Efficiency & Risk Check

* **Complexity**: Sprint 2 moves from O(1) file to O(N) files. SQLite lookups will keep this performant by avoiding re-scanning unchanged files.
* **Risk (The "Semantic Gap")**: Raw signatures might not tell the whole story. We must ensure the `docstring` field is captured reliably to give the LLM context later.
* **Trade-off**: Storing everything as JSON blobs in SQLite allows for "Schema-on-read" flexibility but requires careful versioning ("v1", "v2") as you suggested.

---

### Implementation Plan Snapshot (Sprints 2-3)

| Task | Outcome | Constraint Check |
| --- | --- | --- |
| **SQLite Adapter** | Persistent storage of code structure. | O(1) write per entity. |
| **Bulk Scanner** | Full repository metadata in one DB file. | O(N) file traversal. |
| **Normalizer** | Python constructs → Language-neutral CMM. | Standardizes metadata. |
| **Lazy Resolver** | Cross-file dependency strings captured. | Minimizes initial scan time. |

## Git

Initialize `git` while using `master` as a default branch. Commit frequently, but not too much.
