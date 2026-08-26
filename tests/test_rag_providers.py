from typing import Any

import httpx

from app.config import Settings
from app.rag.providers import DashScopeRagProvider


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


def test_dashscope_provider_uses_expected_embedding_and_rerank_contract(monkeypatch) -> None:
    requests: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        requests.append({"url": url, **kwargs})
        if url.endswith("/embeddings"):
            return FakeResponse(
                {
                    "data": [
                        {"index": 1, "embedding": [0.0, 1.0]},
                        {"index": 0, "embedding": [1.0, 0.0]},
                    ]
                }
            )
        return FakeResponse(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ]
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = DashScopeRagProvider(
        Settings(
            dashscope_api_key="test-key",
            dashscope_embedding_url="https://example.test/embeddings",
            dashscope_rerank_url="https://example.test/reranks",
            rag_embedding_dimensions=2,
        )
    )

    assert provider.embed(["甲", "乙"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert provider.rerank("查询", ["文档一", "文档二"]) == [0.2, 0.9]
    assert requests[0]["json"]["dimensions"] == 2
    assert requests[1]["json"]["model"] == "qwen3-rerank"
