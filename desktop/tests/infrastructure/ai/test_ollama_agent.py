from src.infrastructure.ai.ollama_agent import OllamaAgent


def test_refused_connection_names_ollama() -> None:
    url = "http://localhost:1"
    agent = OllamaAgent("model", url)

    assert url in agent._explain(Exception("connection refused"))
