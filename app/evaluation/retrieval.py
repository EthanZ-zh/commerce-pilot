from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.evaluation.datasets import RetrievalCase
from app.rag.providers import RagProvider
from app.schemas.tools import PolicyQuery
from app.tools.policy import retrieve_policy


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    expected: tuple[str, ...]
    retrieved: tuple[str, ...]
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float


@dataclass(frozen=True)
class RetrievalEvaluation:
    k: int
    case_count: int
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    cases: tuple[RetrievalCaseResult, ...]


def score_ranking(
    retrieved: list[str], relevant: frozenset[str], *, k: int
) -> tuple[float, float, float]:
    if k < 1:
        raise ValueError("k 必须大于 0")
    ranked = retrieved[:k]
    hits = sum(code in relevant for code in ranked)
    recall = hits / len(relevant) if relevant else 0.0
    reciprocal_rank = next(
        (1.0 / rank for rank, code in enumerate(ranked, start=1) if code in relevant),
        0.0,
    )
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, code in enumerate(ranked, start=1)
        if code in relevant
    )
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return recall, reciprocal_rank, ndcg


def evaluate_policy_retrieval(
    db: Session,
    provider: RagProvider,
    cases: tuple[RetrievalCase, ...],
    *,
    k: int = 3,
    as_of: date | None = None,
) -> RetrievalEvaluation:
    if not cases:
        raise ValueError("评测集不能为空")
    results: list[RetrievalCaseResult] = []
    for case in cases:
        evidence = retrieve_policy(
            db,
            PolicyQuery(
                category=case.category,
                query_text=case.query,
                as_of=as_of or date.today(),
                limit=k,
            ),
            provider,
        )
        retrieved = [item.code for item in evidence]
        recall, reciprocal_rank, ndcg = score_ranking(
            retrieved, case.relevant_codes, k=k
        )
        results.append(
            RetrievalCaseResult(
                case_id=case.case_id,
                expected=tuple(sorted(case.relevant_codes)),
                retrieved=tuple(retrieved),
                recall_at_k=recall,
                reciprocal_rank=reciprocal_rank,
                ndcg_at_k=ndcg,
            )
        )
    count = len(results)
    return RetrievalEvaluation(
        k=k,
        case_count=count,
        recall_at_k=sum(item.recall_at_k for item in results) / count,
        mrr=sum(item.reciprocal_rank for item in results) / count,
        ndcg_at_k=sum(item.ndcg_at_k for item in results) / count,
        cases=tuple(results),
    )
