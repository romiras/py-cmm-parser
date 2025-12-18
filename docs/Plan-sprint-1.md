## 1.1 The "Skeleton" Implementation Plan (Sprint 1)

This plan focuses on a type-safe, single-file parser that respects the **Canonical Metadata Model (CMM)**.
Using `uv` will give you a significant speed advantage in dependency management, and type annotations will ensure the "Hexagonal Architecture" remains robust as we scale from a single file to a full repository scan.


## Git

Initialize `git` while using `master` as a default branch. Commit frequently, but not too much.

### Phase A: Environment & Schema (The Foundation)

A target source code will reside within `src` in root of a project.

* **Dependency Management**: Initialize the project using `uv`.
* *Core*: `typer`, `rich`, `tree-sitter`, `tree-sitter-python`.

* **Domain Entities**: Define a `CMMEntity` class using `TypedDict` or `dataclasses` to represent the JSON blob.
* Include `schema_version: str` (set to "v0.1").
* Include `entities: List[Dict]` to store the flexible metadata.

### Phase B: The Parser Adapter (Tree-sitter Wrapper)

* **Interface**: Define `ParserPort(Protocol)` to enforce type-safe implementation of the `scan_file` method.
* **Tree-sitter Logic**:
* Implement the S-expression query to capture `class_definition` and `function_definition`.
* **Visibility**: Ensure the query captures all methods, including private ones (prefixed with `_`).
* **Docstring Extraction**: Capture the first expression in each block as the `raw_docstring`.


#### The Core Query

We will define a query that identifies the structural "intent" of the file. Reference query just for a sake of illustration:

```scheme
;; Query to find classes, functions, and their docstrings
(class_definition 
  name: (identifier) @class.name
  body: (block (expression_statement (string) @class.docstring)?) @class.body)

(function_definition
  name: (identifier) @function.name
  body: (block (expression_statement (string) @function.docstring)?) @function.body)
```



### Phase C: The CLI Interface (Typer)

* **Command Structure**:
* `cmm parser scan-file <path>`


* **Outputs**:
* **Default**: Use `rich.tree.Tree` to render a nested visualization of the classes and methods.
* **`--json` Flag**: Output the raw `CMMEntity` structure to `stdout` using `json.dumps(entity, indent=2)`.


---

## 1.2 Efficiency & Constraint Summary

* **Time Complexity**: O(n) for a single file scan using Tree-sitter's incremental parsing capabilities.
* **Space Complexity**: O(m) where m is the number of symbols (classes/methods) identified, stored in memory before outputting.
* **Design Choice**: By including private methods now but keeping them in a "flexible" JSON blob, we satisfy the requirement to store deep metadata while allowing for future filtering during the PRD generation phase.

---

## 1.3 Strategic Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| **Parsing Overhead** | Tree-sitter is highly efficient; we are only scanning signatures and docstrings at this stage. |
| **Complex Nesting** | Use recursive functions to map the Tree-sitter CST nodes into the hierarchical CMM format. |
| **Type Safety** | Use `mypy` to verify that the `ParserPort` and `CMMEntity` types are strictly followed across the project. |
