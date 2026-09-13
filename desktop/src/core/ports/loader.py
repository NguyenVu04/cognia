from typing import Protocol

from core.models.document import Document


class Loader(Protocol):
    def load(self, source: str) -> Document:
        ...
