from core.models.document import Document


class PdfLoader:
    def load(self, source: str) -> Document:
        ...
