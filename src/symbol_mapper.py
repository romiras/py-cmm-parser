"""
Symbol Mapper: Correlates LSP locations to CMM entity UUIDs.

Provides mapping between LSP file locations and database entity IDs,
with caching to minimize database queries.
"""

import hashlib
import sqlite3
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass
from lsp_client import Location


@dataclass
class Entity:
    """Simplified entity representation for mapper."""

    id: str
    name: str
    file_path: str
    line_start: int
    line_end: int


class SymbolMapper:
    """Maps LSP locations to CMM entity UUIDs."""

    def __init__(self, storage):
        """
        Initialize symbol mapper.

        Args:
            storage: SQLiteStorage instance for database queries
        """
        self.storage = storage
        self.conn = sqlite3.connect(storage.db_path)
        self._location_cache: Dict[Tuple[str, int], str] = {}
        self._symbol_hash_cache: Dict[str, str] = {}
        self._file_entity_cache: Dict[str, List[Entity]] = {}  # NEW

    def __del__(self):
        """Close database connection."""
        if hasattr(self, "conn"):
            self.conn.close()

    def find_by_location(self, location: Location) -> Optional[str]:
        """
        Find entity UUID by LSP location.

        Args:
            location: LSP Location with file URI and line number

        Returns:
            Entity UUID or None if not found
        """
        # Convert file URI to path
        file_path = self._uri_to_path(location.uri)

        # Check cache first
        cache_key = (file_path, location.line)
        if cache_key in self._location_cache:
            return self._location_cache[cache_key]

        # Query database for entity at this location
        entity_id = self._query_entity_at_location(file_path, location.line)

        # Cache result
        if entity_id:
            self._location_cache[cache_key] = entity_id

        return entity_id

    def generate_symbol_hash(self, file_uri: str, qualified_name: str) -> str:
        """
        Generate unique symbol hash for deduplication.

        Args:
            file_uri: File URI (e.g., "file:///path/to/file.py")
            qualified_name: Fully qualified name (e.g., "MyClass.my_method")

        Returns:
            SHA256 hash as hex string
        """
        cache_key = f"{file_uri}#{qualified_name}"

        if cache_key in self._symbol_hash_cache:
            return self._symbol_hash_cache[cache_key]

        # Create hash from URI + qualified name
        hash_input = f"{file_uri}#{qualified_name}".encode("utf-8")
        symbol_hash = hashlib.sha256(hash_input).hexdigest()

        # Cache result
        self._symbol_hash_cache[cache_key] = symbol_hash

        return symbol_hash

    def cache_location_to_uuid(self, location: Location, entity_id: str):
        """
        Cache a location-to-UUID mapping.

        Args:
            location: LSP Location
            entity_id: Entity UUID
        """
        file_path = self._uri_to_path(location.uri)
        cache_key = (file_path, location.line)
        self._location_cache[cache_key] = entity_id

    def clear_cache(self):
        """Clear all cached mappings."""
        self._location_cache.clear()
        self._symbol_hash_cache.clear()

    def _uri_to_path(self, uri: str) -> str:
        """
        Convert file URI to file system path.

        Args:
            uri: File URI (e.g., "file:///path/to/file.py")

        Returns:
            File system path
        """
        if uri.startswith("file://"):
            return uri[7:]  # Remove 'file://' prefix
        return uri

    def _query_entity_at_location(self, file_path: str, line: int) -> Optional[str]:
        """
        Query database for entity at given file location.

        Args:
            file_path: Absolute file path
            line: Line number (0-based from LSP, need to handle conversion)

        Returns:
            Entity UUID or None
        """
        # Note: LSP uses 0-based line numbers, but we might store 1-based
        # This implementation assumes 0-based storage; adjust if needed

        cursor = self.conn.cursor()

        # Query for entity that contains this line
        # Join entities_v3 with metadata to get file_path
        cursor.execute(
            """
            SELECT e.id 
            FROM entities_v3 e
            JOIN metadata m ON e.id = m.entity_id
            WHERE m.file_path = ?
              AND e.line_start <= ?
              AND e.line_end >= ?
            ORDER BY (e.line_end - e.line_start) ASC
            LIMIT 1
        """,
            (file_path, line, line),
        )

        result = cursor.fetchone()
        return result[0] if result else None

    def update_symbol_hash(self, entity_id: str, symbol_hash: str):
        """
        Update symbol_hash for an entity in the database.

        Args:
            entity_id: Entity UUID
            symbol_hash: Generated symbol hash
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE entities_v3
            SET symbol_hash = ?
            WHERE id = ?
        """,
            (symbol_hash, entity_id),
        )
        self.conn.commit()

    def find_enclosing_entity(self, file_path: str, line: int) -> Optional[str]:
        """
        Find the entity UUID that contains the given line.

        Used to determine the "from_id" for a call relation.

        Args:
            file_path: Absolute file path
            line: Line number (0-based, LSP convention)

        Returns:
            Entity UUID or None if line is outside any entity
        """
        # Load all entities for this file (cached)
        if file_path not in self._file_entity_cache:
            self._file_entity_cache[file_path] = self._load_file_entities(file_path)

        entities = self._file_entity_cache[file_path]

        # Find smallest entity containing this line
        # (handles nested methods inside classes)
        best_match = None
        best_span = float("inf")

        for entity in entities:
            if entity.line_start <= line <= entity.line_end:
                span = entity.line_end - entity.line_start
                if span < best_span:
                    best_match = entity
                    best_span = span

        return best_match.id if best_match else None

    def _load_file_entities(self, file_path: str) -> List[Entity]:
        """Load all entities for a file from database."""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT e.id, e.name, e.line_start, e.line_end
            FROM entities_v3 e
            JOIN metadata m ON e.id = m.entity_id
            WHERE m.file_path = ?
            ORDER BY e.line_start ASC
        """,
            (file_path,),
        )

        entities = []
        for row in cursor.fetchall():
            entities.append(
                Entity(
                    id=row[0],
                    name=row[1],
                    file_path=file_path,
                    line_start=row[2],
                    line_end=row[3],
                )
            )

        return entities

    def clear_file_cache(self, file_path: str):
        """Clear cache for a specific file (useful after re-scan)."""
        self._file_entity_cache.pop(file_path, None)
