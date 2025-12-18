## Sprint 2: The Deep Scan & Persistence (Weeks 3-4)

The focus shifts from CLI output to building a local repository of knowledge using **SQLite**.

### Phase 1: Storage Adapter & SQLite Implementation

* **StoragePort**: Define the interface for saving and retrieving entities.
* **SQLite Adapter**: Implement the port.
* **Schema**: Create tables for `files` and `entities`. Each entity will store the flexible JSON blob you just designed, plus a `schema_version` column ("v0.1").
* **Upsert Logic**: Implement logic to update existing file data if the file is re-scanned (using file hashes or paths).



### Phase 2: Directory Crawling & Bulk Scanning

* **Project Crawler**: Extend the CLI to handle `cmm-scan <directory-path>`.
* **Orchestration**: Loop through the directory, filtering for `.py` files, and passing each to your `ParserPort`.
* **Batch Save**: Pipe the results into the `StoragePort`.

## Git

Initialize `git` while using `master` as a default branch. Commit frequently, but not too much.
