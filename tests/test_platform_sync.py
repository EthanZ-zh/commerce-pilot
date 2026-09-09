from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import InventorySnapshot, Product, SalesDaily
from app.platform.contracts import PlatformOrder, PlatformProduct, ShopCredentials
from app.schemas.tools import BaselineWorkflowRequest
from app.workflows.multi_agent import run_multi_agent_workflow


@dataclass
class FakeGateway:
    products: list[PlatformProduct]
    orders: list[PlatformOrder]
    fail_orders: bool = False
    product_calls: int = 0
    order_calls: int = 0

    def list_products(
        self,
        credentials: ShopCredentials,
        *,
        category: str | None = None,
        region: str | None = None,
    ) -> list[PlatformProduct]:
        self.product_calls += 1
        return self.products

    def list_orders(
        self,
        credentials: ShopCredentials,
        *,
        date_from: str,
        date_to: str,
        page_size: int = 50,
    ) -> list[PlatformOrder]:
        self.order_calls += 1
        if self.fail_orders:
            raise RuntimeError("gateway unavailable")
        return self.orders

    def update_stock(self, credentials: ShopCredentials, sku: str, quantity: int) -> None:
        return None


def make_product() -> Product:
    return Product(
        sku="SKU-1",
        title="Internal title",
        category="Internal category",
        region="CN",
        cost_price=Decimal("40.00"),
        sale_price=Decimal("50.00"),
        status="ACTIVE",
    )


def synced_gateway(*, fail_orders: bool = False) -> FakeGateway:
    return FakeGateway(
        products=[
            PlatformProduct(
                sku="SKU-1",
                title="Platform title",
                category="Platform category",
                region="US",
                sale_price=Decimal("60.00"),
                available_stock=7,
                status="INACTIVE",
            )
        ],
        orders=[
            PlatformOrder(
                order_id="order-1",
                product_sku="SKU-1",
                title="Platform title",
                quantity=2,
                paid_amount=Decimal("120.00"),
                status="FINISHED",
                created_at=datetime(2026, 9, 1, 10),
            ),
            PlatformOrder(
                order_id="order-2",
                product_sku="SKU-1",
                title="Platform title",
                quantity=3,
                paid_amount=Decimal("180.00"),
                status="FINISHED",
                created_at=datetime(2026, 9, 1, 11),
            ),
            PlatformOrder(
                order_id="order-3",
                product_sku="SKU-1",
                title="Platform title",
                quantity=8,
                paid_amount=Decimal("480.00"),
                status="PENDING",
                created_at=datetime(2026, 9, 1, 12),
            ),
        ],
        fail_orders=fail_orders,
    )


def agent_evidence_gateway() -> FakeGateway:
    gateway = synced_gateway()
    gateway.products[0] = replace(gateway.products[0], status="ACTIVE")
    gateway.orders = [
        PlatformOrder(
            order_id="agent-order-1",
            product_sku="SKU-1",
            title="Platform title",
            quantity=1,
            paid_amount=Decimal("80.00"),
            status="FINISHED",
            created_at=datetime(2026, 9, 1, 10),
        ),
        PlatformOrder(
            order_id="agent-order-2",
            product_sku="SKU-1",
            title="Platform title",
            quantity=2,
            paid_amount=Decimal("160.00"),
            status="FINISHED",
            created_at=datetime(2026, 9, 1, 11),
        ),
    ]
    return gateway


def test_sync_maps_platform_data_and_preserves_internal_metrics(db: Session) -> None:
    from app.platform.sync import sync_shop_data

    product = make_product()
    db.add(product)
    db.flush()
    db.add_all(
        [
            SalesDaily(
                date=date(2026, 9, 1),
                product_id=product.id,
                views=100,
                clicks=10,
                orders=1,
                revenue=Decimal("50.00"),
            ),
            InventorySnapshot(
                date=date(2026, 8, 31),
                product_id=product.id,
                available_stock=3,
                inbound_stock=11,
                turnover_days=9,
            ),
        ]
    )
    db.commit()
    gateway = synced_gateway()

    report = sync_shop_data(
        db,
        gateway,
        ShopCredentials(tenant_id="shop-1"),
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 1),
        snapshot_date=date(2026, 9, 1),
    )

    db.refresh(product)
    daily = db.scalar(select(SalesDaily).where(SalesDaily.product_id == product.id))
    inventory = db.scalar(
        select(InventorySnapshot).where(
            InventorySnapshot.product_id == product.id,
            InventorySnapshot.date == date(2026, 9, 1),
        )
    )
    assert report.products_updated == 1
    assert report.sales_rows_updated == 1
    assert report.inventory_rows_updated == 1
    assert gateway.product_calls == 1
    assert gateway.order_calls == 1
    assert (
        product.title,
        product.category,
        product.region,
        product.sale_price,
        product.status,
    ) == (
        "Platform title",
        "Platform category",
        "US",
        Decimal("60.00"),
        "INACTIVE",
    )
    assert product.cost_price == Decimal("40.00")
    assert daily is not None
    assert (daily.orders, daily.revenue, daily.views, daily.clicks) == (
        5,
        Decimal("300.00"),
        100,
        10,
    )
    assert inventory is not None
    assert (
        inventory.available_stock,
        inventory.inbound_stock,
        inventory.turnover_days,
    ) == (7, 11, 9)


def test_taobao_finished_order_updates_sales_through_sync_service(db: Session) -> None:
    from app.config import Settings
    from app.platform.sync import sync_shop_data
    from app.platform.taobao import TaobaoShopGateway

    product = make_product()
    db.add(product)
    db.flush()
    db.add(
        InventorySnapshot(
            date=date(2026, 8, 31),
            product_id=product.id,
            available_stock=3,
            inbound_stock=11,
            turnover_days=9,
        )
    )
    db.commit()

    def transport(_gateway_url: str, _params: dict[str, str]) -> dict[str, object]:
        return {
            "trades_sold_get_response": {
                "has_next": False,
                "trades": {
                    "trade": [
                        {
                            "tid": "top-order-1",
                            "sku_id": "SKU-1",
                            "title": "Platform title",
                            "num": "3",
                            "payment": "45.00",
                            "status": "TRADE_FINISHED",
                            "created": "2026-09-01T10:00:00",
                        }
                    ]
                },
            }
        }

    gateway = TaobaoShopGateway(Settings(platform_provider="taobao"), transport=transport)
    credentials = ShopCredentials(
        tenant_id="shop-1",
        platform="taobao",
        app_key="app-key",
        app_secret="app-secret",
        session_key="session-key",
    )

    report = sync_shop_data(
        db,
        gateway,
        credentials,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 1),
        snapshot_date=date(2026, 9, 1),
    )

    daily = db.scalar(select(SalesDaily).where(SalesDaily.product_id == product.id))
    assert report.sales_rows_updated == 1
    assert daily is not None
    assert (daily.orders, daily.revenue) == (3, Decimal("45.00"))


def test_multi_agent_reads_synchronized_shop_evidence(db: Session) -> None:
    from app.platform.sync import sync_shop_data

    product = make_product()
    db.add(product)
    db.flush()
    db.add(
        InventorySnapshot(
            date=date(2026, 8, 31),
            product_id=product.id,
            available_stock=3,
            inbound_stock=11,
            turnover_days=9,
        )
    )
    db.commit()

    sync_shop_data(
        db,
        agent_evidence_gateway(),
        ShopCredentials(tenant_id="shop-1"),
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 1),
        snapshot_date=date(2026, 9, 1),
    )

    result = run_multi_agent_workflow(
        db,
        BaselineWorkflowRequest(
            category="Platform category",
            region="US",
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 1),
            turnover_days_threshold=9,
        ),
        write_enabled=False,
        persist_audit=False,
    )

    sales = next(item for item in result.sales_evidence if item.product_id == product.id)
    inventory = next(
        item for item in result.inventory_evidence if item.product_id == product.id
    )
    assert sales.orders == 3
    assert sales.revenue == Decimal("240.00")
    assert inventory.available_stock == 7


def test_sync_is_idempotent_and_reports_unknown_skus(db: Session) -> None:
    from app.platform.sync import sync_shop_data

    product = make_product()
    db.add(product)
    db.flush()
    db.add(
        InventorySnapshot(
            date=date(2026, 8, 31),
            product_id=product.id,
            available_stock=3,
            inbound_stock=11,
            turnover_days=9,
        )
    )
    db.commit()
    gateway = synced_gateway()
    gateway.products.append(
        PlatformProduct(
            sku="UNKNOWN",
            title="Unknown",
            category="Other",
            region="CN",
            sale_price=Decimal("1.00"),
            available_stock=1,
        )
    )
    gateway.orders.append(
        PlatformOrder(
            order_id="unknown-order",
            product_sku="UNKNOWN",
            title="Unknown",
            quantity=1,
            paid_amount=Decimal("1.00"),
            status="FINISHED",
            created_at=datetime(2026, 9, 1),
        )
    )

    first = sync_shop_data(
        db, gateway, ShopCredentials(tenant_id="shop-1"),
        date_from=date(2026, 9, 1), date_to=date(2026, 9, 1), snapshot_date=date(2026, 9, 1)
    )
    sync_shop_data(
        db, gateway, ShopCredentials(tenant_id="shop-1"),
        date_from=date(2026, 9, 1), date_to=date(2026, 9, 1), snapshot_date=date(2026, 9, 1)
    )

    assert first.unknown_skus == ("UNKNOWN",)
    assert db.scalar(select(func.count()).select_from(Product)) == 1
    assert db.scalar(select(func.count()).select_from(SalesDaily)) == 1
    assert db.scalar(select(func.count()).select_from(InventorySnapshot)) == 2


def test_sync_rejects_invalid_dates_before_calling_gateway(db: Session) -> None:
    from app.platform.sync import sync_shop_data

    gateway = synced_gateway()
    with pytest.raises(ValueError, match="date_from"):
        sync_shop_data(
            db, gateway, ShopCredentials(tenant_id="shop-1"),
            date_from=date(2026, 9, 2), date_to=date(2026, 9, 1), snapshot_date=date(2026, 9, 1)
        )
    assert gateway.product_calls == 0
    assert gateway.order_calls == 0


def test_sync_rejects_out_of_window_order_and_rolls_back_all_writes(db: Session) -> None:
    from app.platform.sync import sync_shop_data

    product = make_product()
    db.add(product)
    db.flush()
    db.add(
        InventorySnapshot(
            date=date(2026, 8, 31),
            product_id=product.id,
            available_stock=3,
            inbound_stock=11,
            turnover_days=9,
        )
    )
    db.commit()
    gateway = synced_gateway()
    gateway.orders[0] = replace(
        gateway.orders[0], created_at=datetime(2026, 9, 2, 10)
    )

    with pytest.raises(ValueError, match="outside"):
        sync_shop_data(
            db,
            gateway,
            ShopCredentials(tenant_id="shop-1"),
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 1),
            snapshot_date=date(2026, 9, 1),
        )

    db.refresh(product)
    assert product.title == "Internal title"
    assert product.sale_price == Decimal("50.00")
    assert db.scalar(select(func.count()).select_from(SalesDaily)) == 0
    assert db.scalar(select(func.count()).select_from(InventorySnapshot)) == 1


def test_sync_rolls_back_product_changes_when_gateway_fails(db: Session) -> None:
    from app.platform.sync import sync_shop_data

    product = make_product()
    db.add(product)
    db.commit()

    with pytest.raises(RuntimeError, match="gateway unavailable"):
        sync_shop_data(
            db, synced_gateway(fail_orders=True), ShopCredentials(tenant_id="shop-1"),
            date_from=date(2026, 9, 1), date_to=date(2026, 9, 1), snapshot_date=date(2026, 9, 1)
        )

    db.refresh(product)
    assert product.title == "Internal title"
    assert product.sale_price == Decimal("50.00")
