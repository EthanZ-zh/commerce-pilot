from app.config import get_settings
from app.rag.providers import DashScopeRagProvider


def main() -> None:
    settings = get_settings()
    provider = DashScopeRagProvider(settings)
    documents = [
        "营销活动发布前必须由授权运营人员审批。",
        "折扣价格不得突破最低毛利约束。",
    ]
    embeddings = provider.embed(["活动发布审批", *documents])
    rerank_scores = provider.rerank("活动发布需要人工审批吗？", documents)
    print(
        {
            "embedding_model": provider.model_name,
            "vectors": len(embeddings),
            "dimensions": len(embeddings[0]),
            "rerank_model": settings.dashscope_rerank_model,
            "rerank_scores": rerank_scores,
        }
    )


if __name__ == "__main__":
    main()
