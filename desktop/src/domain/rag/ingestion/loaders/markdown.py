from domain.rag.ingestion.loaders.loader import Document


class MarkdownLoader:
    def load(self, source: str) -> Document:
        ...
