import sqlite3
import hashlib
import json
import uuid
import os
from typing import Protocol, Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from domain import CMMEntity


class StoragePort(Protocol):
    """A port for storing and retrieving CMM entities."""

    def save_file(self, file_path: str, cmm_entity: CMMEntity) -> None:
        """Saves a file's CMM entities to storage."""
        ...

    def get_file(self, file_path: str) -> Optional[CMMEntity]:
        """Retrieves a file's CMM entities from storage."""
        ...

    def upsert_file(self, file_path: str, cmm_entity: CMMEntity) -> None:
        """Updates or inserts a file's CMM entities based on file hash."""
        ...


class SQLiteStorage(StoragePort):
    """A storage adapter that uses SQLite to persist CMM entities."""

    def __init__(self, db_path: str = "./cmm.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema using v0.3 migration script."""
        migration_path = Path(__file__).parent / "migration_v0.3.sql"

        # Fallback if file doesn't exist (e.g. running from different context)
        if not migration_path.exists():
            # In production, we might embed the SQL string here
            # For now, we expect the file to exist as per plan
            print(f"Warning: Migration script not found at {migration_path}")
            return

        with open(migration_path, "r") as f:
            schema_sql = f.read()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Enable foreign keys for this connection (and future ones)
        cursor.execute("PRAGMA foreign_keys = ON;")

        # Execute migration script (creates tables if not exist)
        cursor.executescript(schema_sql)

        # Apply v0.3.1 schema (LSP enhancements) if available
        # We execute statements individually to handle "column exists" errors gracefully
        migration_3_1_path = Path(__file__).parent / "migration_v0.3.1.sql"
        if migration_3_1_path.exists():
            with open(migration_3_1_path, "r") as f:
                schema_3_1_sql = f.read()

            # Split by semicolon to run statements one by one
            statements = [s.strip() for s in schema_3_1_sql.split(";") if s.strip()]

            for stmt in statements:
                try:
                    cursor.execute(stmt)
                except sqlite3.OperationalError as e:
                    # Ignore "duplicate column name" errors
                    if "duplicate column name" in str(e):
                        continue
                    # Ignore "index already exists" errors
                    if "already exists" in str(e):
                        continue
                    print(f"Warning: Migration statement failed: {stmt[:50]}... -> {e}")

        # Ensure UNIQUE constraint for UPSERT support (Sprint 5.3)
        # We drop the old non-unique index if it exists (optional, but clean)
        # And ensure the unique one exists
        try:
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_relations_unique ON relations(from_id, to_name, rel_type);"
            )
        except sqlite3.OperationalError as e:
            print(f"Warning: Could not create unique index: {e}")

        conn.commit()
        conn.close()

    def save_verified_relation(
        self, from_id: str, to_id: str, rel_type: str, is_verified: bool = True
    ):
        """
        Save or update a verified relation.

        Uses UPSERT logic:
        - If relation (from_id, to_name) exists: UPDATE to_id and is_verified
        - If new: INSERT with is_verified=True
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        try:
            # Get target entity name for to_name field
            cursor.execute("SELECT name FROM entities_v3 WHERE id = ?", (to_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return  # Target entity doesn't exist

            to_name = row[0]

            # UPSERT: Try to update first, insert if not exists
            # Note: explicit UPSERT syntax (ON CONFLICT) requires SQLite 3.24+
            # We use distinct INSERT ... ON CONFLICT ... DO UPDATE
            cursor.execute(
                """
                INSERT INTO relations (from_id, to_id, to_name, rel_type, is_verified)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (from_id, to_name, rel_type) 
                DO UPDATE SET 
                    to_id = excluded.to_id,
                    is_verified = excluded.is_verified
            """,
                (from_id, to_id, to_name, rel_type, is_verified),
            )

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _compute_file_hash(self, file_path: str) -> str:
        """Compute MD5 hash of a file's contents."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            hasher.update(f.read())
        return hasher.hexdigest()

    def save_file(self, file_path: str, cmm_entity: CMMEntity) -> None:
        """Saves a file's CMM entities to storage (v0.3 Schema)."""
        file_hash = self._compute_file_hash(file_path)
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        try:
            # 1. Insert into files_v3
            cursor.execute(
                """
                INSERT INTO files_v3 (file_path, file_hash, schema_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (file_path, file_hash, cmm_entity.schema_version, now, now),
            )

            # 2. Save Entity Hierarchy
            # We don't have a 'file_id' FK in entities_v3 directly, we track file via METADATA table
            # Top-level entities have parent_id = NULL

            for entity in cmm_entity.entities:
                self._save_entity_recursive(
                    cursor, entity, file_path, now, parent_id=None
                )

            conn.commit()
        except sqlite3.IntegrityError:
            # File already exists, rollback and use upsert logic
            conn.rollback()
            conn.close()
            self.upsert_file(file_path, cmm_entity)
            return
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _save_entity_recursive(
        self,
        cursor: sqlite3.Cursor,
        entity: Dict[str, Any],
        file_path: str,
        now: str,
        parent_id: Optional[str],
    ):
        """Recursively save an entity and its children."""

        # Generate new UUID for this entity
        entity_id = str(uuid.uuid4())

        # Extract fields
        name = entity.get("name", "unknown")
        entity_type = entity.get("type", "unknown")
        visibility = entity.get("visibility", "public")
        line_start = entity.get("line_start", 0)
        line_end = entity.get("line_end", 0)

        # 1. Insert into entities_v3
        cursor.execute(
            """
            INSERT INTO entities_v3 (id, name, type, visibility, parent_id, line_start, line_end)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (entity_id, name, entity_type, visibility, parent_id, line_start, line_end),
        )

        # 2. Insert into metadata
        raw_docstring = entity.get("docstring", "")
        cmm_type = entity.get("cmm_type", "")
        method_kind = entity.get("method_kind")  # Optional

        # Signature is not parsed yet, leaving blank or extracting if available (future)
        signature = ""

        cursor.execute(
            """
            INSERT INTO metadata (entity_id, file_path, raw_docstring, signature, cmm_type, method_kind, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                entity_id,
                file_path,
                raw_docstring,
                signature,
                cmm_type,
                method_kind,
                now,
                now,
            ),
        )

        # 3. Insert into relations (Dependencies)
        dependencies = entity.get("dependencies", [])
        for dep in dependencies:
            if isinstance(dep, str):
                # Old format (v0.2): just a name string (assumed to be inheritance or import)
                # Default to 'inherits' for classes if it's in dependencies list from parser v0.2
                # But wait, parser v0.2 put base classes in 'dependencies'.
                dep_name = dep
                rel_type = "dependencies"  # Generic fallback
            elif isinstance(dep, dict):
                # New format (v0.3): {"name": "...", "rel_type": "..."}
                dep_name = dep.get("name")
                rel_type = dep.get("rel_type", "dependencies")
            else:
                continue

            # Insert relation with to_id=NULL (Lazy Resolution)
            if dep_name:
                cursor.execute(
                    """
                    INSERT INTO relations (from_id, to_name, rel_type)
                    VALUES (?, ?, ?)
                """,
                    (entity_id, dep_name, rel_type),
                )

        # 4. Recursively save children (methods)
        methods = entity.get("methods", [])
        for method in methods:
            self._save_entity_recursive(
                cursor, method, file_path, now, parent_id=entity_id
            )

    def upsert_file(self, file_path: str, cmm_entity: CMMEntity) -> None:
        """Updates or inserts a file's CMM entities based on file hash."""
        file_hash = self._compute_file_hash(file_path)
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        # Check existing file
        cursor.execute(
            "SELECT id, file_hash FROM files_v3 WHERE file_path = ?", (file_path,)
        )
        row = cursor.fetchone()

        if row:
            file_db_id, existing_hash = row
            if existing_hash == file_hash:
                conn.close()
                return  # No changes

            # Update file record
            cursor.execute(
                """
                UPDATE files_v3 
                SET file_hash = ?, schema_version = ?, updated_at = ?
                WHERE id = ?
            """,
                (file_hash, cmm_entity.schema_version, now, file_db_id),
            )

            # Delete old entities for this file
            # Since we have ON DELETE CASCADE on metadata(entity_id) -> entities_v3(id),
            # we need to find all entities belonging to this file and delete them from entities_v3.
            # But entities_v3 doesn't have file_id. metadata has file_path.

            # Find definitions in this file
            cursor.execute(
                "SELECT entity_id FROM metadata WHERE file_path = ?", (file_path,)
            )
            entity_ids = [r[0] for r in cursor.fetchall()]

            if entity_ids:
                # Delete from entities_v3. This triggers CASCADE delete on metadata and relations(from_id)
                # We need to be careful about parent/child. Deleting parent deletes child (ON DELETE CASCADE in entities_v3).
                # So we just need to delete the entities found.
                # Ideally, deleting top-level entities cascades down.
                # Just deleting all IDs found in metadata should work, as long as we don't double-delete.
                # Alternatively: delete from entities_v3 where id in (...)

                placeholders = ",".join("?" for _ in entity_ids)
                cursor.execute(
                    f"DELETE FROM entities_v3 WHERE id IN ({placeholders})", entity_ids
                )

            # Insert new entities
            for entity in cmm_entity.entities:
                self._save_entity_recursive(
                    cursor, entity, file_path, now, parent_id=None
                )

            conn.commit()
        else:
            conn.close()
            # Delegating to save_file but careful about recursion if save_file calls upsert.
            # Save_file calls upsert only on IntegrityError (duplicate file_path).
            # Here we know file doesn't exist (if row is None), so calling save_file is safe.
            self.save_file(file_path, cmm_entity)

        conn.close()

    def get_file(self, file_path: str) -> Optional[CMMEntity]:
        """Retrieves a file's CMM entities from storage (reconstructed from v0.3 schema)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check file existence
        cursor.execute(
            "SELECT schema_version FROM files_v3 WHERE file_path = ?", (file_path,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        schema_version = row[0]

        # Get all entities for this file via metadata
        # We also need their hierarchy (parent_id) from entities_v3
        query = """
            SELECT e.id, e.name, e.type, e.visibility, e.parent_id, 
                   m.raw_docstring, m.cmm_type, m.method_kind
            FROM entities_v3 e
            JOIN metadata m ON e.id = m.entity_id
            WHERE m.file_path = ?
        """
        cursor.execute(query, (file_path,))
        rows = cursor.fetchall()

        # Build dictionary of all entities: id -> entity_dict
        entities_map = {}
        for r in rows:
            eid, name, etype, visibility, parent_id, doc, cmm_type, method_kind = r

            entity = {
                "id": eid,
                "name": name,
                "type": etype,
                "visibility": visibility,
                "docstring": doc,
                "cmm_type": cmm_type,
                "dependencies": [],  # Populated later
                "methods": [],  # Populated recursively
            }
            if method_kind:
                entity["method_kind"] = method_kind

            entities_map[eid] = {"data": entity, "parent_id": parent_id}

        # Fetch relations for these entities
        if entities_map:
            placeholders = ",".join("?" for _ in entities_map.keys())
            c_rel = conn.execute(
                f"SELECT from_id, to_name, rel_type FROM relations WHERE from_id IN ({placeholders})",
                list(entities_map.keys()),
            )
            for from_id, to_name, rel_type in c_rel:
                entities_map[from_id]["data"]["dependencies"].append(
                    {"name": to_name, "rel_type": rel_type}
                )

        conn.close()

        # Reconstruct Hierarchy
        top_level_entities = []

        for eid, info in entities_map.items():
            parent_id = info["parent_id"]
            entity_data = info["data"]

            if parent_id and parent_id in entities_map:
                # Add as child to parent
                parent = entities_map[parent_id]["data"]
                # Specifically for classes containing methods
                # Note: v0.3 schema supports generic nesting, but domain specific:
                # classes have 'methods'. Modules might have functions/classes.
                # Assuming standard structure:
                if "methods" in parent:
                    parent["methods"].append(entity_data)
                elif parent["type"] == "class":
                    # Keep as is, it has 'methods' list initialized
                    parent["methods"].append(entity_data)
                else:
                    # If parent is something else (e.g. nested function),
                    # we might attach it differently or just ignore for now in this CMM simplify?
                    # For now, append to methods if it looks like a function/method
                    parent.setdefault("methods", []).append(entity_data)
            else:
                # Top level (or parent not in this file/map)
                top_level_entities.append(entity_data)

        # Sort top level? Maybe not needed.

        return CMMEntity(schema_version=schema_version, entities=top_level_entities)
