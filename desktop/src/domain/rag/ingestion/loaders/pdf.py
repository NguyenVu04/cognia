from domain.rag.ingestion.loaders.loader import Document


class PdfLoader:
    def load(self, source: str) -> Document:
        ...
