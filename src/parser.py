from typing import Protocol, List, Dict, Any
from tree_sitter import Parser, Language, Query, QueryCursor
from tree_sitter_python import language
from domain import CMMEntity
from normalizer import PythonNormalizer


class ParserPort(Protocol):
    """A port for a file parser that extracts CMM entities."""

    def scan_file(self, file_path: str) -> CMMEntity:
        """Scans a file and returns a CMMEntity."""
        ...

# Extended S-expression query to capture decorators, base classes, and imports
CMM_QUERY = """
(class_definition
  name: (identifier) @class.name
  superclasses: (argument_list)? @class.bases
  body: (block (expression_statement (string) @class.docstring)?) @class.body)

(decorated_definition
  (decorator (identifier) @decorator.name)
  definition: (function_definition
    name: (identifier) @decorated_function.name
    body: (block (expression_statement (string) @decorated_function.docstring)?) @decorated_function.body))

(function_definition
  name: (identifier) @function.name
  body: (block (expression_statement (string) @function.docstring)?) @function.body)

(import_statement
  name: (dotted_name) @import.module)

(import_from_statement
  module_name: (dotted_name) @import_from.module
  name: (dotted_name) @import_from.name)
"""

class TreeSitterParser(ParserPort):
    """A parser that uses Tree-sitter to extract CMM entities."""

    def __init__(self):
        self.parser = Parser()
        self.language = Language(language())
        self.parser.language = self.language
        self.normalizer = PythonNormalizer()

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
        decorator_map: Dict[int, List[str]] = {}  # Maps function node ID to decorators
        imports: List[str] = []  # Track imports for dependency resolution

        # Flatten captures from dict format to list of (node, capture_name) tuples
        captures = []
        for capture_name, nodes in captures_dict.items():
            for node in nodes:
                captures.append((node, capture_name))

        # First pass: collect imports and decorators
        for node, capture_name in captures:
            if capture_name == "import.module":
                module_name = node.text.decode()
                imports.append(module_name)
            elif capture_name == "import_from.module":
                module_name = node.text.decode()
                imports.append(module_name)
            elif capture_name == "decorator.name":
                decorator_name = node.text.decode()
                # Find the decorated function
                parent = node.parent
                while parent:
                    if parent.type == "decorated_definition":
                        # Find the function_definition child
                        for child in parent.children:
                            if child.type == "function_definition":
                                if child.id not in decorator_map:
                                    decorator_map[child.id] = []
                                decorator_map[child.id].append(decorator_name)
                        break
                    parent = parent.parent

        # Second pass: create entities for classes and functions
        for node, capture_name in captures:
            if capture_name == "class.name":
                class_name = node.text.decode()
                entity = {
                    "type": "class",
                    "name": class_name,
                    "methods": [],
                    "docstring": "",
                    "dependencies": []
                }
                node_to_entity[node.parent.id] = entity
                
            elif capture_name == "function.name" or capture_name == "decorated_function.name":
                function_name = node.text.decode()
                entity = {
                    "type": "function",
                    "name": function_name,
                    "docstring": "",
                    "method_kind": "instance",  # Default, will be updated
                    "dependencies": []
                }
                
                # Determine the actual function node
                if capture_name == "decorated_function.name":
                    func_node = node.parent  # function_definition
                else:
                    func_node = node.parent
                
                # Check for decorators
                if func_node.id in decorator_map:
                    decorators = decorator_map[func_node.id]
                    if "staticmethod" in decorators:
                        entity["method_kind"] = "static"
                    elif "classmethod" in decorators:
                        entity["method_kind"] = "class"
                
                node_to_entity[func_node.id] = entity

        # Third pass: associate docstrings and base classes
        for node, capture_name in captures:
            if capture_name == "class.docstring":
                docstring = node.text.decode()
                entity = node_to_entity.get(node.parent.parent.parent.id)
                if entity:
                    entity["docstring"] = docstring
                    
            elif capture_name == "function.docstring" or capture_name == "decorated_function.docstring":
                docstring = node.text.decode()
                entity = node_to_entity.get(node.parent.parent.parent.id)
                if entity:
                    entity["docstring"] = docstring
                    
            elif capture_name == "class.bases":
                # Extract base class names for dependency tracking
                base_classes = node.text.decode()
                # Remove parentheses and split by comma
                base_classes = base_classes.strip("()").split(",")
                base_classes = [bc.strip() for bc in base_classes if bc.strip()]
                
                # Find the class entity
                class_node = node.parent
                entity = node_to_entity.get(class_node.id)
                if entity and base_classes:
                    entity["dependencies"].extend(base_classes)

        # Fourth pass: build the hierarchy
        for node, _ in captures:
            if node.id in node_to_entity:
                entity = node_to_entity[node.id]
                parent = node.parent
                while parent:
                    if parent.id in node_to_entity:
                        parent_entity = node_to_entity[parent.id]
                        if parent_entity["type"] == "class" and entity["type"] == "function":
                            parent_entity["methods"].append(entity)
                            entity["moved"] = True
                        break
                    parent = parent.parent

        # Collect the root entities
        for entity in node_to_entity.values():
            if not entity.get("moved"):
                if "moved" in entity:
                    del entity["moved"]
                entities.append(entity)

        # Normalize all entities
        normalized_entities = self.normalizer.normalize_entities(entities)

        return CMMEntity(schema_version="v0.2", entities=normalized_entities)
