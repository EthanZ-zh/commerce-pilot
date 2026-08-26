from sqlalchemy.orm import Session

from app.rag.providers import RagProvider, get_rag_provider
from app.rag.retrieval import hybrid_retrieve_policy
from app.schemas.tools import PolicyEvidence, PolicyQuery


def retrieve_policy(
    db: Session,
    request: PolicyQuery,
    provider: RagProvider | None = None,
) -> list[PolicyEvidence]:
    return hybrid_retrieve_policy(db, request, provider or get_rag_provider())
