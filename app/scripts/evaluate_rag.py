import argparse

from app.evaluation.datasets import POLICY_RETRIEVAL_CASES
from app.evaluation.retrieval import evaluate_policy_retrieval
from app.infrastructure.database import SessionLocal
from app.rag.providers import get_rag_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="执行政策混合 RAG 检索评测")
    parser.add_argument(
        "--limit",
        type=int,
        default=len(POLICY_RETRIEVAL_CASES),
        help="只运行前 N 条 query，适合控制真实 Provider 评测成本",
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit 必须大于 0")
    cases = POLICY_RETRIEVAL_CASES[: args.limit]
    provider = get_rag_provider()
    with SessionLocal() as db:
        report = evaluate_policy_retrieval(
            db, provider, cases, k=3
        )
    print(
        f"provider={provider.model_name} cases={report.case_count} k={report.k} "
        f"Recall@K={report.recall_at_k:.4f} MRR={report.mrr:.4f} "
        f"nDCG@K={report.ndcg_at_k:.4f}"
    )
    for case in report.cases:
        print(
            f"{case.case_id}: expected={list(case.expected)} "
            f"retrieved={list(case.retrieved)} rr={case.reciprocal_rank:.4f}"
        )


if __name__ == "__main__":
    main()
