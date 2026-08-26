from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.domain.models import (
    AgentRun,
    ApprovalRecord,
    Base,
    Campaign,
    InventorySnapshot,
    Policy,
    PolicyChunk,
    Product,
    ProductReview,
    SalesDaily,
    WorkflowApproval,
    WorkflowTask,
)
from app.infrastructure.database import SessionLocal, engine
from app.policies.catalog import POLICY_CATALOG, sync_policy_catalog

CATEGORIES = ["耳机", "键盘", "鼠标", "显示器", "护肤", "运动鞋"]
REGIONS = ["华南", "华东", "华北", "西南"]


def money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reset_database(db: Session) -> None:
    for model in (
        WorkflowApproval,
        WorkflowTask,
        ApprovalRecord,
        AgentRun,
        Campaign,
        ProductReview,
        SalesDaily,
        InventorySnapshot,
        PolicyChunk,
        Policy,
        Product,
    ):
        db.execute(delete(model))
    db.commit()


def seed_database(
    db: Session,
    *,
    product_count: int = 500,
    days: int = 90,
    seed: int = 20260825,
    reset: bool = True,
) -> dict[str, int]:
    if product_count < 1 or days < 1:
        raise ValueError("product_count 和 days 必须大于 0")
    if reset:
        reset_database(db)

    rng = random.Random(seed)
    today = date.today()
    products: list[Product] = []
    for index in range(product_count):
        category = CATEGORIES[index % len(CATEGORIES)]
        region = REGIONS[(index // len(CATEGORIES)) % len(REGIONS)]
        cost = money(rng.uniform(35, 1800))
        sale = money(float(cost) * rng.uniform(1.28, 1.85))
        products.append(
            Product(
                sku=f"CP-{index + 1:05d}",
                category=category,
                title=f"{region}{category}示例商品 {index + 1}",
                region=region,
                cost_price=cost,
                sale_price=sale,
            )
        )
    db.add_all(products)
    db.flush()

    sales_rows: list[SalesDaily] = []
    inventory_rows: list[InventorySnapshot] = []
    review_rows: list[ProductReview] = []
    for product in products:
        demand_factor = rng.uniform(0.35, 1.8)
        for offset in range(days):
            day = today - timedelta(days=offset)
            views = max(20, int(rng.gauss(550 * demand_factor, 90)))
            clicks = max(1, int(views * rng.uniform(0.04, 0.16)))
            orders = max(0, int(clicks * rng.uniform(0.02, 0.18)))
            sales_rows.append(
                SalesDaily(
                    date=day,
                    product_id=product.id,
                    views=views,
                    clicks=clicks,
                    orders=orders,
                    revenue=money(orders * float(product.sale_price)),
                )
            )
        turnover_days = rng.randint(20, 120)
        inventory_rows.append(
            InventorySnapshot(
                date=today,
                product_id=product.id,
                available_stock=rng.randint(30, 900),
                inbound_stock=rng.randint(0, 120),
                turnover_days=turnover_days,
            )
        )
        review_rows.append(
            ProductReview(
                product_id=product.id,
                rating=rng.randint(2, 5),
                content=rng.choice(["性价比不错", "包装完整", "物流很快", "续航一般", "外观简洁"]),
            )
        )

    db.add_all(sales_rows)
    db.add_all(inventory_rows)
    db.add_all(review_rows)
    sync_policy_catalog(db)
    db.commit()
    return {
        "products": len(products),
        "sales_daily": len(sales_rows),
        "inventory_snapshots": len(inventory_rows),
        "product_reviews": len(review_rows),
        "policies": len(POLICY_CATALOG),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 CommercePilot 演示数据")
    parser.add_argument("--products", type=int, default=500)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--no-reset", action="store_true")
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        stats = seed_database(
            db,
            product_count=args.products,
            days=args.days,
            reset=not args.no_reset,
        )
    print(f"Seed complete: {stats}")


if __name__ == "__main__":
    main()
