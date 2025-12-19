from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class CMMEntity:
    """A flexible container for Canonical Metadata Model (CMM) entities."""
    schema_version: str = "v0.3"
    entities: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert CMMEntity to a dictionary for serialization."""
        return {
            "schema_version": self.schema_version,
            "entities": self.entities
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CMMEntity':
        """Create CMMEntity from a dictionary."""
        return cls(
            schema_version=data.get("schema_version", "v0.3"),
            entities=data.get("entities", [])
        )

