from app.infrastructure.database import SessionLocal
from app.policies.catalog import sync_policy_catalog


def main() -> None:
    with SessionLocal() as db:
        stats = sync_policy_catalog(db)
        db.commit()
    print(f"Policy sync complete: {stats}")


if __name__ == "__main__":
    main()
