from src.domain.ports import CharacterCatalogUnavailable, CharacterStoreFailed


def test_store_failed_keeps_sentence() -> None:
    assert str(CharacterStoreFailed("fix it")) == "fix it"


def test_catalog_unavailable_keeps_sentence() -> None:
    assert str(CharacterCatalogUnavailable("fix it")) == "fix it"
