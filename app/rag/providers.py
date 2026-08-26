from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

import httpx

from app.config import Settings, get_settings

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class RerankProvider(Protocol):
    def rerank(self, query: str, documents: Sequence[str]) -> list[float]: ...


class RagProvider(EmbeddingProvider, RerankProvider, Protocol):
    pass


def tokenize(text: str) -> list[str]:
    base = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    chinese = [token for token in base if "\u4e00" <= token <= "\u9fff"]
    return base + ["".join(chinese[index : index + 2]) for index in range(len(chinese) - 1)]


class DeterministicRagProvider:
    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    @property
    def model_name(self) -> str:
        return f"deterministic-hash-{self.dimensions}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        query_tokens = set(tokenize(query))
        denominator = max(len(query_tokens), 1)
        return [
            len(query_tokens.intersection(tokenize(document))) / denominator
            for document in documents
        ]


class DashScopeRagProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        self.settings = settings
        self.headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

    @property
    def model_name(self) -> str:
        return self.settings.dashscope_embedding_model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), 10):
            response = httpx.post(
                self.settings.dashscope_embedding_url,
                headers=self.headers,
                json={
                    "model": self.settings.dashscope_embedding_model,
                    "input": list(texts[start : start + 10]),
                    "dimensions": self.settings.rag_embedding_dimensions,
                    "encoding_format": "float",
                },
                timeout=self.settings.rag_request_timeout_seconds,
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            embeddings.extend(item["embedding"] for item in data)
        return embeddings

    def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        response = httpx.post(
            self.settings.dashscope_rerank_url,
            headers=self.headers,
            json={
                "model": self.settings.dashscope_rerank_model,
                "query": query,
                "documents": list(documents),
                "top_n": len(documents),
                "return_documents": False,
            },
            timeout=self.settings.rag_request_timeout_seconds,
        )
        response.raise_for_status()
        scores = [0.0] * len(documents)
        for item in response.json()["results"]:
            scores[item["index"]] = float(item["relevance_score"])
        return scores


def get_rag_provider(settings: Settings | None = None) -> RagProvider:
    resolved = settings or get_settings()
    if resolved.rag_provider == "dashscope":
        return DashScopeRagProvider(resolved)
    if resolved.rag_provider != "deterministic":
        raise ValueError("RAG_PROVIDER 必须为 deterministic 或 dashscope")
    return DeterministicRagProvider(resolved.rag_embedding_dimensions)
