from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from opentelemetry.trace import Status, StatusCode
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.models import Policy, PolicyChunk
from app.rag.indexing import index_policies
from app.rag.providers import RagProvider, tokenize
from app.schemas.tools import PolicyEvidence, PolicyQuery
from app.telemetry import get_tracer


@dataclass
class Candidate:
    chunk: PolicyChunk
    policy: Policy
    lexical_score: float = 0.0
    vector_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float = 0.0


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _bm25(query: str, documents: list[str]) -> list[float]:
    tokenized = [tokenize(document) for document in documents]
    query_tokens = tokenize(query)
    if not documents or not query_tokens:
        return [0.0] * len(documents)
    avg_length = sum(map(len, tokenized)) / len(tokenized) or 1.0
    document_frequency = Counter(
        token for tokens in tokenized for token in set(tokens)
    )
    scores: list[float] = []
    for tokens in tokenized:
        frequencies = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if not frequency:
                continue
            idf = math.log(
                1
                + (len(documents) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / avg_length)
            score += idf * frequency * 2.5 / denominator
        scores.append(score)
    return scores


def _rrf(candidates: list[Candidate], attribute: str, k: int = 60) -> dict[int, float]:
    ranked = sorted(candidates, key=lambda item: getattr(item, attribute), reverse=True)
    return {item.chunk.id: 1 / (k + rank) for rank, item in enumerate(ranked, start=1)}


def hybrid_retrieve_policy(
    db: Session,
    request: PolicyQuery,
    provider: RagProvider,
) -> list[PolicyEvidence]:
    with get_tracer().start_as_current_span(
        "commerce_pilot.rag.retrieve",
        attributes={
            "commerce_pilot.rag.provider_model": provider.model_name,
            "commerce_pilot.rag.category": request.category,
            "commerce_pilot.rag.limit": request.limit,
        },
    ) as span:
        try:
            evidence = _hybrid_retrieve_policy(db, request, provider)
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            raise
        span.set_attribute("commerce_pilot.rag.result_count", len(evidence))
        span.set_attribute(
            "commerce_pilot.rag.policy_codes", [item.code for item in evidence]
        )
        return evidence


def _hybrid_retrieve_policy(
    db: Session,
    request: PolicyQuery,
    provider: RagProvider,
) -> list[PolicyEvidence]:
    policies = list(
        db.scalars(
            select(Policy).where(
                Policy.is_active.is_(True),
                Policy.effective_from <= request.as_of,
                or_(Policy.expires_at.is_(None), Policy.expires_at >= request.as_of),
                or_(Policy.category == request.category, Policy.category == "审批"),
            )
        ).all()
    )
    if not policies:
        return []
    policy_ids = [policy.id for policy in policies]
    chunks = list(
        db.scalars(select(PolicyChunk).where(PolicyChunk.policy_id.in_(policy_ids))).all()
    )
    if not chunks or any(chunk.embedding_model != provider.model_name for chunk in chunks):
        index_policies(db, provider, policies)
        db.commit()
        chunks = list(
            db.scalars(select(PolicyChunk).where(PolicyChunk.policy_id.in_(policy_ids))).all()
        )
    policy_by_id = {policy.id: policy for policy in policies}
    query_vector = provider.embed([request.query_text])[0]
    lexical_scores = _bm25(request.query_text, [chunk.content for chunk in chunks])
    recall_limit = min(max(request.limit * 5, 20), len(chunks))
    lexical_by_id = {
        chunk.id: score for chunk, score in zip(chunks, lexical_scores, strict=True)
    }
    lexical_chunks = sorted(
        chunks, key=lambda chunk: lexical_by_id[chunk.id], reverse=True
    )[:recall_limit]
    if db.get_bind().dialect.name == "postgresql":
        vector_chunks = list(
            db.scalars(
                select(PolicyChunk)
                .where(PolicyChunk.policy_id.in_(policy_ids))
                .order_by(PolicyChunk.embedding.cosine_distance(query_vector))
                .limit(recall_limit)
            ).all()
        )
    else:
        vector_chunks = sorted(
            chunks,
            key=lambda chunk: _cosine(query_vector, list(chunk.embedding)),
            reverse=True,
        )[:recall_limit]
    recalled = {chunk.id: chunk for chunk in [*lexical_chunks, *vector_chunks]}
    candidates = [
        Candidate(chunk=chunk, policy=policy_by_id[chunk.policy_id])
        for chunk in recalled.values()
    ]
    for item in candidates:
        lexical_score = lexical_by_id[item.chunk.id]
        item.lexical_score = lexical_score
        item.vector_score = _cosine(query_vector, list(item.chunk.embedding))
    lexical_rrf = _rrf(candidates, "lexical_score")
    vector_rrf = _rrf(candidates, "vector_score")
    for item in candidates:
        item.fused_score = lexical_rrf[item.chunk.id] + vector_rrf[item.chunk.id]
    candidates.sort(key=lambda item: item.fused_score, reverse=True)
    rerank_scores = provider.rerank(
        request.query_text, [item.chunk.content for item in candidates]
    )
    for item, score in zip(candidates, rerank_scores, strict=True):
        item.rerank_score = score
    candidates.sort(key=lambda item: (item.rerank_score, item.fused_score), reverse=True)

    grouped: dict[int, list[Candidate]] = defaultdict(list)
    for item in candidates:
        grouped[item.policy.id].append(item)
    ranked_policies = sorted(
        grouped.values(),
        key=lambda items: (items[0].rerank_score, items[0].fused_score),
        reverse=True,
    )[: request.limit]
    return [
        PolicyEvidence(
            policy_id=items[0].policy.id,
            code=items[0].policy.code,
            title=items[0].policy.title,
            content="\n".join(item.chunk.content for item in items[:3]),
            source=items[0].policy.source,
            version=items[0].policy.version,
            forbidden_terms=items[0].policy.forbidden_terms or [],
            chunk_ids=[item.chunk.id for item in items[:3]],
            lexical_score=items[0].lexical_score,
            vector_score=items[0].vector_score,
            fused_score=items[0].fused_score,
            rerank_score=items[0].rerank_score,
        )
        for items in ranked_policies
    ]
