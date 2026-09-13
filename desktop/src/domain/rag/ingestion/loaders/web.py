from core.models.document import Document


class WebLoader:
    def load(self, source: str) -> Document:
        ...
