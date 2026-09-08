from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import InventorySnapshot, Product, SalesDaily
from app.platform.contracts import ShopCredentials, ShopGateway


@dataclass(frozen=True, slots=True)
class PlatformSyncReport:
    products_updated: int
    sales_rows_updated: int
    inventory_rows_updated: int
    unknown_skus: tuple[str, ...]
    inventory_skipped_skus: tuple[str, ...]


def sync_shop_data(
    db: Session,
    gateway: ShopGateway,
    credentials: ShopCredentials,
    *,
    date_from: date,
    date_to: date,
    snapshot_date: date,
) -> PlatformSyncReport:
    if date_from > date_to:
        raise ValueError("date_from must not be after date_to")

    try:
        platform_products = gateway.list_products(credentials)
        platform_orders = gateway.list_orders(
            credentials, date_from=date_from.isoformat(), date_to=date_to.isoformat()
        )
        if any(
            order.created_at.date() < date_from or order.created_at.date() > date_to
            for order in platform_orders
        ):
            raise ValueError("gateway order is outside requested date range")
        products_by_sku = {
            product.sku: product for product in db.scalars(select(Product)).all()
        }
        platform_by_sku = {product.sku: product for product in platform_products}
        unknown_skus = {
            sku for sku in platform_by_sku if sku not in products_by_sku
        } | {
            order.product_sku
            for order in platform_orders
            if order.product_sku not in products_by_sku
        }

        products_updated = 0
        inventory_rows_updated = 0
        inventory_skipped_skus: set[str] = set()
        for sku, platform_product in platform_by_sku.items():
            product = products_by_sku.get(sku)
            if product is None:
                continue
            for field in ("title", "category", "region", "status"):
                value = getattr(platform_product, field)
                if value:
                    setattr(product, field, value)
            product.sale_price = platform_product.sale_price
            products_updated += 1

            baseline = db.scalar(
                select(InventorySnapshot)
                .where(InventorySnapshot.product_id == product.id)
                .order_by(InventorySnapshot.date.desc())
                .limit(1)
            )
            if baseline is None:
                inventory_skipped_skus.add(sku)
                continue
            snapshot = db.scalar(
                select(InventorySnapshot).where(
                    InventorySnapshot.product_id == product.id,
                    InventorySnapshot.date == snapshot_date,
                )
            )
            if snapshot is None:
                snapshot = InventorySnapshot(
                    date=snapshot_date,
                    product_id=product.id,
                    available_stock=platform_product.available_stock,
                    inbound_stock=baseline.inbound_stock,
                    turnover_days=baseline.turnover_days,
                )
                db.add(snapshot)
            else:
                snapshot.available_stock = platform_product.available_stock
            inventory_rows_updated += 1

        sales_totals: dict[tuple[str, date], list[Decimal | int]] = defaultdict(
            lambda: [0, Decimal("0")]
        )
        for order in platform_orders:
            if order.status != "FINISHED" or order.product_sku not in products_by_sku:
                continue
            total = sales_totals[(order.product_sku, order.created_at.date())]
            total[0] += order.quantity
            total[1] += order.paid_amount

        for (sku, sales_date), (orders, revenue) in sales_totals.items():
            product = products_by_sku[sku]
            daily = db.scalar(
                select(SalesDaily).where(
                    SalesDaily.product_id == product.id, SalesDaily.date == sales_date
                )
            )
            if daily is None:
                daily = SalesDaily(
                    date=sales_date,
                    product_id=product.id,
                    orders=int(orders),
                    revenue=Decimal(revenue),
                )
                db.add(daily)
            else:
                daily.orders = int(orders)
                daily.revenue = Decimal(revenue)

        db.commit()
        return PlatformSyncReport(
            products_updated=products_updated,
            sales_rows_updated=len(sales_totals),
            inventory_rows_updated=inventory_rows_updated,
            unknown_skus=tuple(sorted(unknown_skus)),
            inventory_skipped_skus=tuple(sorted(inventory_skipped_skus)),
        )
    except Exception:
        db.rollback()
        raise
