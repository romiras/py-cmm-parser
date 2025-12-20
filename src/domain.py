from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class CallSite:
    """Represents a function/method call with precise location for LSP queries."""

    name: str  # Function/method name (e.g., "scan_file")
    line: int  # 0-based line number (LSP convention)
    character: int  # 0-based column offset
    file_uri: str  # Absolute URI: "file:///path/to/file.py"

    @staticmethod
    def from_node(node, file_path: str) -> "CallSite":
        """Create CallSite from Tree-sitter node."""
        return CallSite(
            name=node.text.decode("utf-8"),
            line=node.start_point[0],
            character=node.start_point[1],
            file_uri=f"file://{file_path}",
        )


@dataclass
class CMMEntity:
    """A flexible container for Canonical Metadata Model (CMM) entities."""

    schema_version: str = "v0.3"
    entities: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert CMMEntity to a dictionary for serialization."""
        return {"schema_version": self.schema_version, "entities": self.entities}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CMMEntity":
        """Create CMMEntity from a dictionary."""
        return cls(
            schema_version=data.get("schema_version", "v0.3"),
            entities=data.get("entities", []),
        )
