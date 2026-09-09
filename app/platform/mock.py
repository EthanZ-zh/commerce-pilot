"""Mock 平台网关：数据来自本地合成业务表，用于无真实平台凭证时的完整运行与 CI。"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import InventorySnapshot, Product, SalesDaily
from app.platform.contracts import (
    CampaignDraft,
    CampaignDraftResult,
    PlatformOrder,
    PlatformProduct,
    ShopCredentials,
)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


class MockShopGateway:
    platform = "mock"

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_products(
        self,
        credentials: ShopCredentials,
        *,
        category: str | None = None,
        region: str | None = None,
    ) -> list[PlatformProduct]:
        statement = select(Product).where(Product.status == "ACTIVE")
        if category:
            statement = statement.where(Product.category == category)
        if region:
            statement = statement.where(Product.region == region)
        products = self._db.scalars(statement.order_by(Product.id)).all()
        return [self._to_product(product) for product in products]

    def list_orders(
        self,
        credentials: ShopCredentials,
        *,
        date_from: str,
        date_to: str,
        page_size: int = 50,
    ) -> list[PlatformOrder]:
        rows = self._db.execute(
            select(Product, SalesDaily)
            .join(SalesDaily, SalesDaily.product_id == Product.id)
            .where(
                SalesDaily.date >= _parse_date(date_from),
                SalesDaily.date <= _parse_date(date_to),
                SalesDaily.orders > 0,
            )
            .order_by(SalesDaily.date.desc(), Product.id)
        ).all()
        orders: list[PlatformOrder] = []
        for product, daily in rows:
            orders.append(
                PlatformOrder(
                    order_id=f"MOCK-{product.sku}-{daily.date}",
                    product_sku=product.sku,
                    title=product.title,
                    quantity=int(daily.orders),
                    paid_amount=Decimal(daily.revenue or 0),
                    status="FINISHED",
                    created_at=datetime.combine(daily.date, time.min),
                )
            )
        return orders

    def update_stock(self, credentials: ShopCredentials, sku: str, quantity: int) -> None:
        product = self._db.scalar(select(Product).where(Product.sku == sku))
        if product is None:
            raise ValueError(f"商品不存在：{sku}")

    def _to_product(self, product: Product) -> PlatformProduct:
        snapshot = self._db.scalar(
            select(InventorySnapshot)
            .where(InventorySnapshot.product_id == product.id)
            .order_by(InventorySnapshot.date.desc())
            .limit(1)
        )
        return PlatformProduct(
            sku=product.sku,
            title=product.title,
            category=product.category,
            region=product.region,
            sale_price=Decimal(product.sale_price or 0),
            available_stock=int(snapshot.available_stock if snapshot else 0),
            status=product.status,
        )


class MockCampaignPublisher:
    platform = "mock"

    def submit_draft(
        self, credentials: ShopCredentials, draft: CampaignDraft
    ) -> CampaignDraftResult:
        return CampaignDraftResult(
            platform_ref=f"MOCK-{draft.idempotency_key}",
            status="DRAFT",
            detail="mock 网关：草稿已登记，未对接真实发布通道",
        )
