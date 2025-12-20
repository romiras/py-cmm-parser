from typing import Protocol, List, Dict, Any
from tree_sitter import Parser, Language, Query, QueryCursor, Node
from tree_sitter_python import language
from domain import CMMEntity
from normalizer import PythonNormalizer
import os


class ParserPort(Protocol):
    """A port for a file parser that extracts CMM entities."""

    def scan_file(self, file_path: str) -> CMMEntity:
        """Scans a file and returns a CMMEntity."""
        ...


# S-expression query to capture classes, functions, decorators, bases, and imports
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

# Query to extract function/method calls within bodies
CALL_QUERY = """
(call
  function: (identifier) @call.function)

(call
  function: (attribute
    object: (identifier) @call.object
    attribute: (identifier) @call.method))
"""

# Python built-in functions and keywords to exclude from call dependencies
PYTHON_BUILTINS = {
    "self",
    "cls",  # Common method parameters
    "print",
    "len",
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
    "range",
    "enumerate",
    "zip",
    "map",
    "filter",
    "sorted",
    "sum",
    "min",
    "max",
    "abs",
    "all",
    "any",
    "isinstance",
    "issubclass",
    "hasattr",
    "getattr",
    "setattr",
    "open",
    "type",
    "id",
    "hash",
    "repr",
    "format",
    "input",
    "next",
    "iter",
}


class TreeSitterParser(ParserPort):
    """A parser that uses Tree-sitter to extract CMM entities."""

    def __init__(self):
        self.parser = Parser()
        self.language = Language(language())
        self.parser.language = self.language
        self.normalizer = PythonNormalizer()

        self.cmm_query = Query(self.language, CMM_QUERY)
        self.call_query = Query(self.language, CALL_QUERY)

        self.debug_mode = os.environ.get("CMM_DEBUG") == "1"

    def extract_call_sites(self, file_path: str) -> List[Any]:
        """
        Extract all function/method call sites with precise LSP-compatible locations.

        This is a second parse specifically for LSP integration. Returns location
        data that scan_file() discards for performance.
        """
        from domain import CallSite

        with open(file_path, "r") as f:
            content = f.read()

        tree = self.parser.parse(bytes(content, "utf8"))
        cursor = QueryCursor(self.call_query)
        captures_dict = cursor.captures(tree.root_node)

        call_sites = []
        for capture_name, nodes in captures_dict.items():
            for node in nodes:
                call_name = node.text.decode("utf-8")
                if call_name in PYTHON_BUILTINS:
                    continue
                call_sites.append(CallSite.from_node(node, file_path))

        return call_sites

    def scan_file(self, file_path: str) -> CMMEntity:
        """Scans a file and returns a CMMEntity."""
        with open(file_path, "r") as f:
            content = f.read()

        tree = self.parser.parse(bytes(content, "utf8"))
        cursor = QueryCursor(self.cmm_query)
        captures_dict = cursor.captures(tree.root_node)

        # Flatten captures to list of (node, capture_name) tuples
        captures = []
        for capture_name, nodes in captures_dict.items():
            for node in nodes:
                captures.append((node, capture_name))

        # Data structures
        node_to_entity: Dict[int, Dict[str, Any]] = {}
        decorator_map: Dict[int, List[str]] = {}

        # Pass 1: Collect decorators and create entities
        for node, capture_name in captures:
            if capture_name == "decorator.name":
                self._process_decorator(node, decorator_map)
            elif capture_name == "class.name":
                self._create_class_entity(node, node_to_entity)
            elif capture_name in ["function.name", "decorated_function.name"]:
                self._create_function_entity(node, node_to_entity, decorator_map)

        # Pass 2: Populate entity metadata (docstrings, base classes, calls, imports)
        for node, capture_name in captures:
            if capture_name in [
                "class.docstring",
                "function.docstring",
                "decorated_function.docstring",
            ]:
                self._add_docstring(node, node_to_entity)
            elif capture_name == "class.bases":
                self._add_base_classes(node, node_to_entity)
            elif capture_name in ["function.body", "decorated_function.body"]:
                self._extract_calls_from_body(node, node_to_entity)
            elif capture_name in ["import.module", "import_from.module"]:
                self._add_import_dependency(node, node_to_entity, captures)

        # Pass 3: Build class hierarchy (nest methods inside classes)
        self._build_hierarchy(captures, node_to_entity)

        # Collect root-level entities (not nested)
        final_entities = [e for e in node_to_entity.values() if not e.get("_is_nested")]

        # Clean up internal flags
        for e in final_entities:
            e.pop("_is_nested", None)

        # Normalize and return
        normalized_entities = self.normalizer.normalize_entities(final_entities)
        return CMMEntity(schema_version="v0.3", entities=normalized_entities)

    def _process_decorator(self, node: Node, decorator_map: Dict[int, List[str]]):
        """Extract decorator name and map it to its function."""
        decorator_name = node.text.decode()
        parent = node.parent
        while parent:
            if parent.type == "decorated_definition":
                for child in parent.children:
                    if child.type == "function_definition":
                        if child.id not in decorator_map:
                            decorator_map[child.id] = []
                        decorator_map[child.id].append(decorator_name)
                break
            parent = parent.parent

    def _create_class_entity(
        self, node: Node, node_to_entity: Dict[int, Dict[str, Any]]
    ):
        """Create a class entity."""
        class_name = node.text.decode()
        class_node = node.parent  # identifier -> class_definition

        entity = {
            "type": "class",
            "name": class_name,
            "line_start": class_node.start_point[0],
            "line_end": class_node.end_point[0],
            "methods": [],
            "docstring": "",
            "dependencies": [],
        }
        node_to_entity[class_node.id] = entity

    def _create_function_entity(
        self,
        node: Node,
        node_to_entity: Dict[int, Dict[str, Any]],
        decorator_map: Dict[int, List[str]],
    ):
        """Create a function/method entity."""
        function_name = node.text.decode()
        func_node = node.parent  # identifier -> function_definition

        entity = {
            "type": "function",
            "name": function_name,
            "line_start": func_node.start_point[0],
            "line_end": func_node.end_point[0],
            "docstring": "",
            "method_kind": "instance",
            "dependencies": [],
        }

        # Check for decorators to determine method kind
        if func_node.id in decorator_map:
            decorators = decorator_map[func_node.id]
            if "staticmethod" in decorators:
                entity["method_kind"] = "static"
            elif "classmethod" in decorators:
                entity["method_kind"] = "class"

        node_to_entity[func_node.id] = entity

    def _add_docstring(self, node: Node, node_to_entity: Dict[int, Dict[str, Any]]):
        """Add docstring to entity."""
        docstring = node.text.decode()
        # Navigate: string -> expression_statement -> block -> definition
        body_block = node.parent.parent
        def_node = body_block.parent

        entity = node_to_entity.get(def_node.id)
        if entity:
            entity["docstring"] = docstring

    def _add_base_classes(self, node: Node, node_to_entity: Dict[int, Dict[str, Any]]):
        """Add base classes as 'inherits' dependencies."""
        class_node = node.parent
        entity = node_to_entity.get(class_node.id)
        if not entity:
            return

        # Extract base class names from argument_list node
        for child in node.children:
            if child.type == "identifier":
                base_class = child.text.decode()
                entity["dependencies"].append(
                    {"name": base_class, "rel_type": "inherits"}
                )
            elif child.type == "attribute":
                # Handle qualified names like module.ClassName
                base_class = child.text.decode()
                entity["dependencies"].append(
                    {"name": base_class, "rel_type": "inherits"}
                )

    def _extract_calls_from_body(
        self, body_node: Node, node_to_entity: Dict[int, Dict[str, Any]]
    ):
        """Extract function/method calls from body and add as dependencies."""
        func_node = body_node.parent
        entity = node_to_entity.get(func_node.id)
        if not entity:
            return

        cursor = QueryCursor(self.call_query)
        captures = cursor.captures(body_node)

        # Collect unique call names
        call_names = set()
        for capture_name, nodes in captures.items():
            for node in nodes:
                call_name = node.text.decode()
                # Filter out Python builtins
                if call_name not in PYTHON_BUILTINS:
                    call_names.add(call_name)

        # Add as dependencies
        for call_name in call_names:
            entity["dependencies"].append({"name": call_name, "rel_type": "calls"})

        if self.debug_mode:
            print(f"[TRACE] Body for {entity['name']}:\n{body_node.text.decode()}\n")

    def _add_import_dependency(
        self,
        node: Node,
        node_to_entity: Dict[int, Dict[str, Any]],
        captures: List[tuple],
    ):
        """Add import as a file-level dependency."""
        module_name = node.text.decode()

        # Find the top-level module entity (if we create one) or attach to first function/class
        # For simplicity, we'll create a synthetic "module" entity if none exists
        # Or we can skip this for now since imports are file-level, not entity-level
        #
        # Decision: Skip for now. Imports are file-level metadata, not entity-level.
        # We can add a "module" entity type in a future sprint if needed.
        pass

    def _build_hierarchy(
        self, captures: List[tuple], node_to_entity: Dict[int, Dict[str, Any]]
    ):
        """Build class-method hierarchy by nesting methods inside classes."""
        # Clear existing methods lists
        for entity in node_to_entity.values():
            if entity["type"] == "class":
                entity["methods"] = []

        # Iterate over function/class name captures to establish parent-child relationships
        for node, capture_name in captures:
            if capture_name not in [
                "class.name",
                "function.name",
                "decorated_function.name",
            ]:
                continue

            def_node = node.parent  # identifier -> definition
            if def_node.id not in node_to_entity:
                continue

            entity = node_to_entity[def_node.id]

            # Walk up the tree to find parent class
            current = def_node.parent
            while current:
                if current.id in node_to_entity:
                    parent_entity = node_to_entity[current.id]
                    # If parent is a class and child is a function, nest it
                    if (
                        parent_entity["type"] == "class"
                        and entity["type"] == "function"
                    ):
                        if entity not in parent_entity["methods"]:
                            parent_entity["methods"].append(entity)
                        entity["_is_nested"] = True
                    break
                current = current.parent
