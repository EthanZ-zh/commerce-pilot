from app.infrastructure.database import SessionLocal
from app.rag.indexing import index_policies
from app.rag.providers import get_rag_provider


def main() -> None:
    provider = get_rag_provider()
    with SessionLocal() as db:
        count = index_policies(db, provider)
        db.commit()
    print(f"Indexed {count} policy chunks with {provider.model_name}")


if __name__ == "__main__":
    main()
