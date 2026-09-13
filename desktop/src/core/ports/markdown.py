from core.models.document import Document


class MarkdownLoader:
    def load(self, source: str) -> Document:
        ...
