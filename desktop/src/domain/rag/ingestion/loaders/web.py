from domain.rag.ingestion.loaders.loader import Document


class WebLoader:
    def load(self, source: str) -> Document:
        ...
