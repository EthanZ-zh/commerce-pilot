import math

import pytest

from app.evaluation.datasets import POLICY_RETRIEVAL_CASES
from app.evaluation.retrieval import evaluate_policy_retrieval, score_ranking
from app.rag.indexing import index_policies
from app.rag.providers import DeterministicRagProvider


def test_score_ranking_calculates_recall_mrr_and_ndcg() -> None:
    recall, mrr, ndcg = score_ranking(
        ["OTHER", "EXPECTED", "SECOND"],
        frozenset({"EXPECTED", "SECOND"}),
        k=3,
    )

    assert recall == 1.0
    assert mrr == 0.5
    assert ndcg == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    )


def test_policy_retrieval_evaluation_runs_offline(seeded_db) -> None:
    provider = DeterministicRagProvider()
    index_policies(seeded_db, provider)
    seeded_db.commit()

    report = evaluate_policy_retrieval(
        seeded_db, provider, POLICY_RETRIEVAL_CASES, k=3
    )

    assert report.case_count == len(POLICY_RETRIEVAL_CASES)
    assert report.recall_at_k >= 0.75
    assert report.mrr >= 0.70
    assert report.ndcg_at_k >= 0.70
    assert all(case.retrieved for case in report.cases)
