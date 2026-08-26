from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.domain.models import Policy, PolicyChunk
from app.rag.indexing import index_policies, split_text
from app.rag.providers import DeterministicRagProvider
from app.schemas.tools import PolicyQuery
from app.tools.policy import retrieve_policy


def test_split_text_has_overlap_and_no_empty_chunks() -> None:
    chunks = split_text("甲" * 900, chunk_size=500, overlap=80)

    assert [len(chunk) for chunk in chunks] == [500, 480]
    assert chunks[0][-80:] == chunks[1][:80]


def test_hybrid_policy_rag_indexes_ranks_and_returns_scores(db: Session) -> None:
    today = date.today()
    db.add_all(
        [
            Policy(
                code="PRICE",
                title="价格规则",
                category="营销",
                content="折扣不得突破最低毛利率。",
                source="test",
                version="1",
                forbidden_terms=[],
                effective_from=today - timedelta(days=1),
                is_active=True,
            ),
            Policy(
                code="APPROVAL",
                title="发布审批规则",
                category="审批",
                content="活动发布前必须由授权运营人员人工审批，自动系统只能创建草稿。",
                source="test",
                version="1",
                forbidden_terms=[],
                effective_from=today - timedelta(days=1),
                is_active=True,
            ),
        ]
    )
    db.commit()
    provider = DeterministicRagProvider()

    indexed = index_policies(db, provider)
    results = retrieve_policy(
        db,
        PolicyQuery(category="营销", query_text="活动发布需要谁授权审批？"),
        provider,
    )

    assert indexed == 2
    assert db.query(PolicyChunk).count() == 2
    assert results[0].code == "APPROVAL"
    assert results[0].chunk_ids
    assert results[0].fused_score > 0
    assert results[0].rerank_score > 0


def test_retrieval_reindexes_when_embedding_model_changes(db: Session) -> None:
    policy = Policy(
        code="POLICY",
        title="政策",
        category="营销",
        content="营销活动需要合规检查。",
        source="test",
        version="1",
        forbidden_terms=[],
        effective_from=date.today(),
        is_active=True,
    )
    db.add(policy)
    db.commit()
    first = DeterministicRagProvider(256)
    index_policies(db, first)
    db.query(PolicyChunk).update({PolicyChunk.embedding_model: "old-model"})
    db.commit()

    retrieve_policy(db, PolicyQuery(query_text="营销合规"), first)

    assert {chunk.embedding_model for chunk in db.query(PolicyChunk)} == {first.model_name}
