import sqlite3
import hashlib
import json
from typing import Protocol, Optional
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
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_hash TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Create entities table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_data TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
            )
        """)

        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_file_path ON files(file_path)
        """)

        conn.commit()
        conn.close()

    def _compute_file_hash(self, file_path: str) -> str:
        """Compute MD5 hash of a file's contents."""
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            hasher.update(f.read())
        return hasher.hexdigest()

    def save_file(self, file_path: str, cmm_entity: CMMEntity) -> None:
        """Saves a file's CMM entities to storage."""
        file_hash = self._compute_file_hash(file_path)
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Insert file record
            cursor.execute("""
                INSERT INTO files (file_path, file_hash, schema_version, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (file_path, file_hash, cmm_entity.schema_version, now, now))

            file_id = cursor.lastrowid

            # Insert entity records
            for entity in cmm_entity.entities:
                entity_type = entity.get("type", "unknown")
                entity_data = json.dumps(entity)
                cursor.execute("""
                    INSERT INTO entities (file_id, entity_type, entity_data)
                    VALUES (?, ?, ?)
                """, (file_id, entity_type, entity_data))

            conn.commit()
        except sqlite3.IntegrityError:
            # File already exists, use upsert instead
            conn.rollback()
            conn.close()
            self.upsert_file(file_path, cmm_entity)
            return
        finally:
            conn.close()

    def get_file(self, file_path: str) -> Optional[CMMEntity]:
        """Retrieves a file's CMM entities from storage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get file record
        cursor.execute("""
            SELECT id, schema_version FROM files WHERE file_path = ?
        """, (file_path,))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        file_id, schema_version = row

        # Get entity records
        cursor.execute("""
            SELECT entity_data FROM entities WHERE file_id = ?
        """, (file_id,))

        entities = [json.loads(row[0]) for row in cursor.fetchall()]
        conn.close()

        return CMMEntity(schema_version=schema_version, entities=entities)

    def upsert_file(self, file_path: str, cmm_entity: CMMEntity) -> None:
        """Updates or inserts a file's CMM entities based on file hash."""
        file_hash = self._compute_file_hash(file_path)
        now = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Check if file exists and if hash has changed
        cursor.execute("""
            SELECT id, file_hash FROM files WHERE file_path = ?
        """, (file_path,))

        row = cursor.fetchone()

        if row:
            file_id, existing_hash = row
            if existing_hash == file_hash:
                # No changes, skip update
                conn.close()
                return

            # Update file record
            cursor.execute("""
                UPDATE files
                SET file_hash = ?, schema_version = ?, updated_at = ?
                WHERE id = ?
            """, (file_hash, cmm_entity.schema_version, now, file_id))

            # Delete old entities
            cursor.execute("""
                DELETE FROM entities WHERE file_id = ?
            """, (file_id,))

            # Insert new entities
            for entity in cmm_entity.entities:
                entity_type = entity.get("type", "unknown")
                entity_data = json.dumps(entity)
                cursor.execute("""
                    INSERT INTO entities (file_id, entity_type, entity_data)
                    VALUES (?, ?, ?)
                """, (file_id, entity_type, entity_data))

            conn.commit()
        else:
            # File doesn't exist, insert new record
            conn.close()
            self.save_file(file_path, cmm_entity)
            return

        conn.close()
