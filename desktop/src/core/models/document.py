from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
