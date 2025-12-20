import sqlite3
import hashlib
import uuid
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

    def get_hierarchical_intent(self) -> List[Dict[str, Any]]:
        """
        Retrieves the hierarchical intent structure.
        Returns a list of root (module) entities, each containing their children.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # 1. Fetch all entities with metadata
            query = """
                SELECT 
                    e.id, e.name, e.type, e.visibility, e.parent_id,
                    m.raw_docstring, m.type_hint, m.file_path
                FROM entities e
                LEFT JOIN metadata m ON e.id = m.entity_id
                ORDER BY e.parent_id NULLS FIRST, m.file_path
            """
            cursor.execute(query)
            all_rows = cursor.fetchall()

            # 2. Fetch all verified relations
            rel_query = """
                SELECT from_id, to_name, rel_type, is_verified
                FROM relations
                WHERE is_verified = 1
            """
            cursor.execute(rel_query)
            all_relations = cursor.fetchall()
            
            # Map relations to from_id
            relations_map = {}
            for r in all_relations:
                fid = r["from_id"]
                if fid not in relations_map:
                    relations_map[fid] = []
                relations_map[fid].append(dict(r))

            # 3. Build Tree
            # First pass: Create dict of all entities
            entities_map = {}
            roots = []

            for row in all_rows:
                entity = dict(row)
                entity["docstring"] = entity.pop("raw_docstring") # Rename for convenience
                entity["children"] = []
                entity["relations"] = relations_map.get(entity["id"], [])
                entities_map[entity["id"]] = entity

            # Second pass: Link parents and children
            for eid, entity in entities_map.items():
                pid = entity["parent_id"]
                if pid and pid in entities_map:
                    entities_map[pid]["children"].append(entity)
                else:
                    # Treat as root if parent is null (Modules) usually
                    # Note: In CMM, modules are roots.
                    if entity["type"] == "module":
                        roots.append(entity)
                    elif pid is None: 
                        # Fallback for parsing artifacts or orphan nodes
                        roots.append(entity)
            
            return roots

        finally:
            conn.close()

    def _init_db(self):
        """Initialize the database schema using v0.4 migration script."""
        migration_path = Path(__file__).parent / "migration_v0.4.sql"

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
            cursor.execute("SELECT name FROM entities WHERE id = ?", (to_id,))
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

    def save_type_hint(self, entity_id: str, type_hint: str):
        """
        Save or update type hint for an entity.

        Args:
            entity_id: Entity UUID
            type_hint: Type signature (e.g., "(x: int, y: int) -> int")
        """
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE metadata
                SET type_hint = ?
                WHERE entity_id = ?
            """,
                (type_hint, entity_id),
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
            # 1. Insert into files
            cursor.execute(
                """
                INSERT INTO files (file_path, file_hash, schema_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (file_path, file_hash, cmm_entity.schema_version, now, now),
            )

            # 2. Save Entity Hierarchy
            # We don't have a 'file_id' FK in entities directly, we track file via METADATA table
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
        depth: int = 0,
    ):
        """Recursively save an entity and its children.
        
        Args:
            depth: Current recursion depth (safety limit: 100)
        """
        # Safety check to prevent infinite recursion
        if depth > 100:
            import sys
            print(
                f"[ERROR] Maximum recursion depth exceeded for entity: {entity.get('name')} "
                f"(Type: {entity.get('type')})",
                file=sys.stderr
            )
            return

        # Generate new UUID for this entity
        entity_id = str(uuid.uuid4())

        # Extract fields
        name = entity.get("name", "unknown")
        entity_type = entity.get("type", "unknown")
        visibility = entity.get("visibility", "public")
        line_start = entity.get("line_start", 0)
        line_end = entity.get("line_end", 0)

        # 1. Insert into entities
        cursor.execute(
            """
            INSERT INTO entities (id, name, type, visibility, parent_id, line_start, line_end)
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
        # Deduplicate dependencies to avoid UNIQUE constraint violations
        dependencies = entity.get("dependencies", [])
        seen_relations = set()
        
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
            # Skip if we've already seen this (dep_name, rel_type) pair
            if dep_name:
                relation_key = (dep_name, rel_type)
                if relation_key not in seen_relations:
                    seen_relations.add(relation_key)
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
                cursor, method, file_path, now, parent_id=entity_id, depth=depth + 1
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
            "SELECT id, file_hash FROM files WHERE file_path = ?", (file_path,)
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
                UPDATE files 
                SET file_hash = ?, schema_version = ?, updated_at = ?
                WHERE id = ?
            """,
                (file_hash, cmm_entity.schema_version, now, file_db_id),
            )

            # Delete old entities for this file
            # Since we have ON DELETE CASCADE on metadata(entity_id) -> entities(id),
            # we need to find all entities belonging to this file and delete them from entities.
            # But entities doesn't have file_id. metadata has file_path.

            # Find definitions in this file
            cursor.execute(
                "SELECT entity_id FROM metadata WHERE file_path = ?", (file_path,)
            )
            entity_ids = [r[0] for r in cursor.fetchall()]

            if entity_ids:
                # Delete from entities. This triggers CASCADE delete on metadata and relations(from_id)
                # We need to be careful about parent/child. Deleting parent deletes child (ON DELETE CASCADE in entities).
                # So we just need to delete the entities found.
                # Ideally, deleting top-level entities cascades down.
                # Just deleting all IDs found in metadata should work, as long as we don't double-delete.
                # Alternatively: delete from entities where id in (...)

                placeholders = ",".join("?" for _ in entity_ids)
                cursor.execute(
                    f"DELETE FROM entities WHERE id IN ({placeholders})", entity_ids
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
            "SELECT schema_version FROM files WHERE file_path = ?", (file_path,)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        schema_version = row[0]

        # Get all entities for this file via metadata
        # We also need their hierarchy (parent_id) from entities
        query = """
            SELECT e.id, e.name, e.type, e.visibility, e.parent_id, 
                   m.raw_docstring, m.cmm_type, m.method_kind
            FROM entities e
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
