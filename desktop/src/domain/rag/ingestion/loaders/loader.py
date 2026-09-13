from dataclasses import dataclass, field
from typing import Protocol, Any


@dataclass
class Document:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Loader(Protocol):
    def load(self, source: str) -> Document:
        ...
