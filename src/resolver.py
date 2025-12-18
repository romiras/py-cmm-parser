import sqlite3
import json
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


class DependencyResolver:
    """Resolves cross-file dependencies by querying the SQLite database."""
    
    def __init__(self, db_path: str = "./cmm.db"):
        self.db_path = db_path
    
    def resolve_dependencies(self, file_path: str) -> Dict[str, List[ResolvedDependency]]:
        """
        Resolve all dependencies for entities in a given file.
        
        Args:
            file_path: Path to the file to resolve dependencies for
            
        Returns:
            Dictionary mapping entity names to their resolved dependencies
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all entities from the file
        cursor.execute("""
            SELECT e.entity_data 
            FROM entities e
            JOIN files f ON e.file_id = f.id
            WHERE f.file_path = ?
        """, (file_path,))
        
        rows = cursor.fetchall()
        if not rows:
            conn.close()
            return {}
        
        result = {}
        
        for row in rows:
            entity_data = json.loads(row[0])
            entity_name = entity_data.get("name", "")
            dependencies = entity_data.get("dependencies", [])
            
            if not dependencies:
                continue
            
            resolved_deps = []
            for dep_name in dependencies:
                # Search for the dependency in the database
                resolved = self._find_entity(cursor, dep_name, file_path)
                if resolved:
                    resolved_deps.extend(resolved)
            
            if resolved_deps:
                result[entity_name] = resolved_deps
        
        conn.close()
        return result
    
    def _find_entity(
        self, 
        cursor: sqlite3.Cursor, 
        entity_name: str, 
        excluding_file: Optional[str] = None
    ) -> List[ResolvedDependency]:
        """
        Find an entity by name in the database.
        
        Args:
            cursor: Database cursor
            entity_name: Name of the entity to find
            excluding_file: Optional file path to exclude from search
            
        Returns:
            List of resolved dependencies
        """
        # Query for entities with matching name
        if excluding_file:
            cursor.execute("""
                SELECT e.entity_data, f.file_path
                FROM entities e
                JOIN files f ON e.file_id = f.id
                WHERE f.file_path != ?
            """, (excluding_file,))
        else:
            cursor.execute("""
                SELECT e.entity_data, f.file_path
                FROM files f
                JOIN entities e ON e.file_id = f.id
            """)
        
        rows = cursor.fetchall()
        results = []
        
        for entity_json, file_path in rows:
            entity = json.loads(entity_json)
            
            # Check if name matches
            if entity.get("name") == entity_name:
                results.append(ResolvedDependency(
                    entity_name=entity.get("name", ""),
                    entity_type=entity.get("type", ""),
                    file_path=file_path,
                    visibility=entity.get("visibility", "unknown"),
                    cmm_type=entity.get("cmm_type", "unknown")
                ))
            
            # Also check methods within classes
            if entity.get("type") == "class":
                for method in entity.get("methods", []):
                    if method.get("name") == entity_name:
                        results.append(ResolvedDependency(
                            entity_name=method.get("name", ""),
                            entity_type=method.get("type", ""),
                            file_path=file_path,
                            visibility=method.get("visibility", "unknown"),
                            cmm_type=method.get("cmm_type", "unknown")
                        ))
        
        return results
    
    def get_dependency_graph(self, file_path: str) -> Dict[str, Any]:
        """
        Build a dependency graph for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary representing the dependency graph
        """
        dependencies = self.resolve_dependencies(file_path)
        
        graph = {
            "file": file_path,
            "entities": []
        }
        
        for entity_name, resolved_deps in dependencies.items():
            entity_node = {
                "name": entity_name,
                "dependencies": [
                    {
                        "name": dep.entity_name,
                        "type": dep.entity_type,
                        "file": dep.file_path,
                        "visibility": dep.visibility,
                        "cmm_type": dep.cmm_type
                    }
                    for dep in resolved_deps
                ]
            }
            graph["entities"].append(entity_node)
        
        return graph
