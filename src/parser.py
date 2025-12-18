from typing import Protocol, List, Dict, Any
from tree_sitter import Parser, Language, Query, QueryCursor
from tree_sitter_python import language
from domain import CMMEntity


class ParserPort(Protocol):
    """A port for a file parser that extracts CMM entities."""

    def scan_file(self, file_path: str) -> CMMEntity:
        """Scans a file and returns a CMMEntity."""
        ...

# The S-expression query to find classes, functions, and their docstrings
CMM_QUERY = """
(class_definition
  name: (identifier) @class.name
  body: (block (expression_statement (string) @class.docstring)?) @class.body)

(function_definition
  name: (identifier) @function.name
  body: (block (expression_statement (string) @function.docstring)?) @function.body)
"""

class TreeSitterParser(ParserPort):
    """A parser that uses Tree-sitter to extract CMM entities."""

    def __init__(self):
        self.parser = Parser()
        self.language = Language(language())
        self.parser.language = self.language

    def scan_file(self, file_path: str) -> CMMEntity:
        """Scans a file and returns a CMMEntity."""
        with open(file_path, "r") as f:
            content = f.read()
        
        tree = self.parser.parse(bytes(content, "utf8"))
        query = Query(self.language, CMM_QUERY)
        cursor = QueryCursor(query)
        captures_dict = cursor.captures(tree.root_node)

        entities: List[Dict[str, Any]] = []
        node_to_entity: Dict[int, Dict[str, Any]] = {}

        # Flatten captures from dict format to list of (node, capture_name) tuples
        captures = []
        for capture_name, nodes in captures_dict.items():
            for node in nodes:
                captures.append((node, capture_name))

        # First pass: create entities for all classes and functions
        for node, capture_name in captures:
            if capture_name == "class.name":
                class_name = node.text.decode()
                entity = {"type": "class", "name": class_name, "methods": [], "docstring": ""}
                node_to_entity[node.parent.id] = entity
            elif capture_name == "function.name":
                function_name = node.text.decode()
                entity = {"type": "function", "name": function_name, "docstring": ""}
                node_to_entity[node.parent.id] = entity
        
        # Second pass: associate docstrings
        for node, capture_name in captures:
            if capture_name == "class.docstring":
                docstring = node.text.decode()
                # The docstring's parent is the expression_statement, its grandparent is the block, 
                # and its great-grandparent is the class_definition
                entity = node_to_entity.get(node.parent.parent.parent.id)
                if entity:
                    entity["docstring"] = docstring
            elif capture_name == "function.docstring":
                docstring = node.text.decode()
                # The docstring's parent is the expression_statement, its grandparent is the block, 
                # and its great-grandparent is the function_definition
                entity = node_to_entity.get(node.parent.parent.parent.id)
                if entity:
                    entity["docstring"] = docstring

        # Third pass: build the hierarchy
        for node, _ in captures:
            if node.id in node_to_entity:
                entity = node_to_entity[node.id]
                parent = node.parent
                while parent:
                    if parent.id in node_to_entity:
                        parent_entity = node_to_entity[parent.id]
                        if parent_entity["type"] == "class" and entity["type"] == "function":
                            parent_entity["methods"].append(entity)
                            # Mark the entity as moved
                            entity["moved"] = True
                        break
                    parent = parent.parent
        
        # Collect the root entities
        for entity in node_to_entity.values():
            if not entity.get("moved"):
                # clean up moved flag
                if "moved" in entity:
                    del entity["moved"]
                entities.append(entity)
        
        return CMMEntity(entities=entities)