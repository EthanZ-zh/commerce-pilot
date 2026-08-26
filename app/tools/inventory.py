from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.domain.models import InventorySnapshot, Product
from app.schemas.tools import InventoryItem, InventoryQuery


def query_inventory(db: Session, request: InventoryQuery) -> list[InventoryItem]:
    latest = (
        select(
            InventorySnapshot.product_id,
            func.max(InventorySnapshot.date).label("latest_date"),
        )
        .group_by(InventorySnapshot.product_id)
        .subquery()
    )
    statement = (
        select(Product, InventorySnapshot)
        .join(InventorySnapshot, InventorySnapshot.product_id == Product.id)
        .join(
            latest,
            and_(
                latest.c.product_id == InventorySnapshot.product_id,
                latest.c.latest_date == InventorySnapshot.date,
            ),
        )
        .where(
            Product.category == request.category,
            Product.region == request.region,
            Product.status == "ACTIVE",
            InventorySnapshot.turnover_days >= request.turnover_days_threshold,
        )
        .order_by(
            InventorySnapshot.turnover_days.desc(),
            InventorySnapshot.available_stock.desc(),
        )
        .limit(request.limit)
    )
    return [
        InventoryItem(
            product_id=product.id,
            sku=product.sku,
            title=product.title,
            cost_price=product.cost_price,
            sale_price=product.sale_price,
            available_stock=inventory.available_stock,
            inbound_stock=inventory.inbound_stock,
            turnover_days=inventory.turnover_days,
            snapshot_date=inventory.date,
        )
        for product, inventory in db.execute(statement).all()
    ]
