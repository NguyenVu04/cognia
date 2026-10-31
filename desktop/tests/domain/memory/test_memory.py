from src.domain.memory.memory_service import MemoryService


def test_service_constructs() -> None:
    assert MemoryService()
