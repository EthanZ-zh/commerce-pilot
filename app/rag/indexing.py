from __future__ import annotations

import hashlib
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.models import Policy, PolicyChunk
from app.rag.providers import EmbeddingProvider


def split_text(text: str, *, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap 必须小于 chunk_size")
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = end - overlap
    return chunks


def index_policies(
    db: Session,
    provider: EmbeddingProvider,
    policies: Iterable[Policy] | None = None,
) -> int:
    selected = list(policies) if policies is not None else list(db.scalars(select(Policy)).all())
    policy_chunks = [
        (policy, index, chunk)
        for policy in selected
        for index, chunk in enumerate(split_text(f"{policy.title}\n{policy.content}"))
    ]
    if not policy_chunks:
        return 0
    policy_ids = [policy.id for policy in selected]
    existing_chunks = list(
        db.scalars(select(PolicyChunk).where(PolicyChunk.policy_id.in_(policy_ids))).all()
    )
    for chunk in existing_chunks:
        if chunk in db:
            db.expunge(chunk)
    db.execute(
        delete(PolicyChunk)
        .where(PolicyChunk.policy_id.in_(policy_ids))
        .execution_options(synchronize_session=False)
    )
    db.flush()
    embeddings = provider.embed([chunk for _, _, chunk in policy_chunks])
    if len(embeddings) != len(policy_chunks):
        raise ValueError("Embedding 返回数量与政策分块数量不一致")
    db.add_all(
        [
            PolicyChunk(
                policy_id=policy.id,
                chunk_index=index,
                content=chunk,
                content_hash=hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                embedding=embedding,
                embedding_model=provider.model_name,
            )
            for (policy, index, chunk), embedding in zip(
                policy_chunks, embeddings, strict=True
            )
        ]
    )
    db.flush()
    return len(policy_chunks)
