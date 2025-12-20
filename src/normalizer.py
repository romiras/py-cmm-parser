from typing import Dict, Any, List


class PythonNormalizer:
    """Normalizes Python-specific constructs to language-neutral CMM terms."""

    # Mapping of Python dunder methods to CMM types
    DUNDER_TO_CMM = {
        "__init__": "Constructor",
        "__new__": "Constructor",
        "__str__": "Display",
        "__repr__": "Display",
        "__eq__": "Equality",
        "__ne__": "Equality",
        "__hash__": "Equality",
        "__lt__": "Comparison",
        "__le__": "Comparison",
        "__gt__": "Comparison",
        "__ge__": "Comparison",
        "__len__": "Collection",
        "__getitem__": "Collection",
        "__setitem__": "Collection",
        "__delitem__": "Collection",
        "__iter__": "Collection",
        "__contains__": "Collection",
        "__enter__": "Context",
        "__exit__": "Context",
        "__call__": "Callable",
        "__del__": "Destructor",
    }

    def normalize_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a single entity by adding CMM metadata.

        Args:
            entity: Raw entity dictionary from parser

        Returns:
            Enhanced entity with normalized metadata
        """
        entity_type = entity.get("type")
        name = entity.get("name", "")

        # Add visibility
        entity["visibility"] = self._detect_visibility(name, entity_type)

        # Add CMM type for methods
        if entity_type == "function":
            entity["cmm_type"] = self._get_cmm_type(name)
            # Method kind will be determined later when we have decorator info
            # For now, default to instance method (will be refined in parser)
            entity["method_kind"] = entity.get("method_kind", "instance")
        elif entity_type == "class":
            entity["cmm_type"] = "Class"

        # Normalize nested methods in classes
        if "methods" in entity:
            entity["methods"] = [
                self.normalize_entity(method) for method in entity["methods"]
            ]

        return entity

    def _detect_visibility(self, name: str, entity_type: str) -> str:
        """
        Detect visibility based on Python naming conventions.

        Args:
            name: Name of the entity
            entity_type: Type of entity (class, function)

        Returns:
            "public" or "private"
        """
        # Dunder methods are public (language-level interface)
        if name.startswith("__") and name.endswith("__"):
            return "public"

        # Single underscore prefix indicates private
        if name.startswith("_"):
            return "private"

        # Everything else is public
        return "public"

    def _get_cmm_type(self, name: str) -> str:
        """
        Map Python method name to CMM type.

        Args:
            name: Method name

        Returns:
            CMM type string
        """
        # Check if it's a dunder method
        if name in self.DUNDER_TO_CMM:
            return self.DUNDER_TO_CMM[name]

        # Regular method
        return "Method"

    def normalize_entities(
        self, entities: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Normalize a list of entities.

        Args:
            entities: List of raw entity dictionaries

        Returns:
            List of normalized entities
        """
        return [self.normalize_entity(entity) for entity in entities]
