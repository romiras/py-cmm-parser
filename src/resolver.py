import sqlite3
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ResolvedDependency:
    """Represents a resolved dependency."""

    entity_name: str
    entity_type: str
    file_path: str
    visibility: str
    cmm_type: str
    rel_type: str = "unknown"  # Added in v0.3


class DependencyResolver:
    """Resolves cross-file dependencies by querying the SQLite database (v0.3 Schema)."""

    def __init__(self, db_path: str = "./cmm.db"):
        self.db_path = db_path

    def resolve_dependencies(
        self, file_path: str
    ) -> Dict[str, List[ResolvedDependency]]:
        """
        Resolve all dependencies for entities in a given file.

        Args:
            file_path: Path to the file to resolve dependencies for

        Returns:
            Dictionary mapping entity names to their resolved dependencies
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 1. identifying all entities in this file from metadata
        cursor.execute(
            """
            SELECT entity_id, raw_docstring 
            FROM metadata 
            WHERE file_path = ?
        """,
            (file_path,),
        )

        file_entities = cursor.fetchall()
        if not file_entities:
            conn.close()
            return {}

        entity_ids = [r[0] for r in file_entities]

        # 2. For each entity, find its outgoing relations
        # We want to map: Entity Name -> [Resolved Dependencies]

        result = {}

        for eid in entity_ids:
            # Get entity name
            cursor.execute("SELECT name FROM entities_v3 WHERE id = ?", (eid,))
            row = cursor.fetchone()
            if not row:
                continue
            entity_name = row[0]

            # Get relations
            cursor.execute(
                """
                SELECT r.to_name, r.rel_type, r.to_id
                FROM relations r
                WHERE r.from_id = ?
            """,
                (eid,),
            )

            relations = cursor.fetchall()
            resolved_deps = []

            for to_name, rel_type, to_id in relations:
                # Resolve target
                target_info = []

                if to_id:
                    # Direct link exists (resolved)
                    target_info = self._get_entity_info(cursor, to_id)
                else:
                    # Lazy link: search by name
                    # Exclude current file to avoid self-reference?
                    # Actually standard resolution allows intra-module loops, but usually we look for other files.
                    # Implementation Plan v0.3: "Search Entities table for matching to_name"
                    targets = self._find_entity(
                        cursor, to_name, excluding_file=file_path
                    )
                    target_info.extend(targets)

                # Convert to ResolvedDependency objects
                for t in target_info:
                    resolved_deps.append(
                        ResolvedDependency(
                            entity_name=t["name"],
                            entity_type=t["type"],
                            file_path=t["file_path"],
                            visibility=t["visibility"],
                            cmm_type=t["cmm_type"],
                            rel_type=rel_type,
                        )
                    )

            if resolved_deps:
                result[entity_name] = resolved_deps

        conn.close()
        return result

    def _get_entity_info(
        self, cursor: sqlite3.Cursor, entity_id: str
    ) -> List[Dict[str, Any]]:
        """Get info for a specific entity ID."""
        cursor.execute(
            """
            SELECT e.name, e.type, e.visibility, m.file_path, m.cmm_type
            FROM entities_v3 e
            JOIN metadata m ON e.id = m.entity_id
            WHERE e.id = ?
        """,
            (entity_id,),
        )
        row = cursor.fetchone()
        if row:
            return [
                {
                    "name": row[0],
                    "type": row[1],
                    "visibility": row[2],
                    "file_path": row[3],
                    "cmm_type": row[4],
                }
            ]
        return []

    def _find_entity(
        self,
        cursor: sqlite3.Cursor,
        entity_name: str,
        excluding_file: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find an entity by name in the database.
        """
        query = """
            SELECT e.name, e.type, e.visibility, m.file_path, m.cmm_type
            FROM entities_v3 e
            JOIN metadata m ON e.id = m.entity_id
            WHERE e.name = ?
        """
        params = [entity_name]

        if excluding_file:
            query += " AND m.file_path != ?"
            params.append(excluding_file)

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append(
                {
                    "name": r[0],
                    "type": r[1],
                    "visibility": r[2],
                    "file_path": r[3],
                    "cmm_type": r[4],
                }
            )

        return results

    def get_dependency_graph(self, file_path: str) -> Dict[str, Any]:
        """
        Build a dependency graph for a file.
        """
        dependencies = self.resolve_dependencies(file_path)

        graph = {"file": file_path, "entities": []}

        for entity_name, resolved_deps in dependencies.items():
            entity_node = {
                "name": entity_name,
                "dependencies": [
                    {
                        "name": dep.entity_name,
                        "type": dep.entity_type,
                        "file": dep.file_path,
                        "visibility": dep.visibility,
                        "cmm_type": dep.cmm_type,
                        "rel_type": dep.rel_type,
                    }
                    for dep in resolved_deps
                ],
            }
            graph["entities"].append(entity_node)

        return graph
