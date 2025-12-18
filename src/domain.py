from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class CMMEntity:
    """A flexible container for Canonical Metadata Model (CMM) entities."""
    schema_version: str = "v0.1"
    entities: List[Dict[str, Any]] = field(default_factory=list)
