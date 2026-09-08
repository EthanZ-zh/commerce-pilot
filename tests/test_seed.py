from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import InventorySnapshot, Policy, Product, SalesDaily
from app.scripts.seed import seed_database


def test_seed_is_reproducible_and_has_expected_scale(db: Session) -> None:
    stats = seed_database(db, product_count=12, days=7, seed=42, reset=True)

    assert stats == {
        "products": 12,
        "sales_daily": 84,
        "inventory_snapshots": 12,
        "product_reviews": 12,
        "policies": 10,
    }
    assert db.scalar(select(func.count()).select_from(Product)) == 12
    assert db.scalar(select(func.count()).select_from(SalesDaily)) == 84
    assert db.scalar(select(func.count()).select_from(InventorySnapshot)) == 12
    assert db.scalar(select(func.count()).select_from(Policy)) == 10
