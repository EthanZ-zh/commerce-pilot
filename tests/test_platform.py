from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.models import SalesDaily
from app.platform.contracts import CampaignDraft, ShopCredentials
from app.platform.factory import (
    demo_credentials,
    get_campaign_publisher,
    get_shop_gateway,
)
from app.platform.mock import MockCampaignPublisher, MockShopGateway
from app.platform.taobao import (
    TaobaoCampaignPublisher,
    TaobaoShopGateway,
    build_request_params,
    top_sign,
)

TOP_DOC_GOLDEN = {
    "app_key": "test",
    "fields": "nick",
    "format": "xml",
    "method": "taobao.user.seller.get",
    "session": "test",
    "sign_method": "md5",
    "timestamp": "2013-05-06 13:52:03",
    "v": "2.0",
}


def test_top_sign_matches_official_example() -> None:
    # 官方文档示例：secret=test，期望 32 位大写 MD5
    assert top_sign(TOP_DOC_GOLDEN, "test") == "72CB4D809B375A54502C09360D879C64"


def test_top_sign_is_deterministic_and_order_sensitive() -> None:
    first = top_sign({"a": "1", "b": "2"}, "secret")
    assert first == top_sign({"b": "2", "a": "1"}, "secret")
    assert first != top_sign({"a": "1", "b": "3"}, "secret")


def test_build_request_params_excludes_empty_and_signs() -> None:
    params = build_request_params(
        "taobao.item.get",
        app_key="k123",
        app_secret="s456",
        session_key="",
        biz_params={"num_iid": "11223344", "fields": ""},
        timestamp="2013-05-06 13:52:03",
    )
    assert params["method"] == "taobao.item.get"
    assert params["app_key"] == "k123"
    assert "session" not in params
    assert "fields" not in params  # 空业务参数不参与签名
    assert params["num_iid"] == "11223344"
    assert len(params["sign"]) == 32
    assert params["sign"] == params["sign"].upper()


def test_mock_shop_gateway_reads_seeded_products(seeded_db: Session) -> None:
    gateway = MockShopGateway(seeded_db)
    credentials = ShopCredentials(tenant_id="t1")
    products = gateway.list_products(credentials, category="耳机")
    assert products
    assert all(product.category == "耳机" for product in products)
    first = products[0]
    assert first.sku.startswith("CP-")
    assert first.sale_price > 0
    assert first.available_stock >= 0


def test_mock_shop_gateway_lists_orders_within_range(seeded_db: Session) -> None:
    gateway = MockShopGateway(seeded_db)
    today = date.today()
    orders = gateway.list_orders(
        ShopCredentials(tenant_id="t1"),
        date_from=(today - timedelta(days=31)).isoformat(),
        date_to=(today + timedelta(days=1)).isoformat(),
    )
    assert orders
    assert orders[0].order_id.startswith("MOCK-")
    assert orders[0].created_at.date() <= today


def test_mock_shop_gateway_update_stock_unknown_sku_raises(seeded_db: Session) -> None:
    gateway = MockShopGateway(seeded_db)
    with pytest.raises(ValueError, match="商品不存在"):
        gateway.update_stock(ShopCredentials(tenant_id="t1"), sku="CP-999999", quantity=10)


def test_mock_campaign_publisher_returns_draft_only() -> None:
    publisher = MockCampaignPublisher()
    draft = CampaignDraft(
        task_id="task-1",
        name="清库存活动",
        product_skus=("CP-00001",),
        discount_rate=Decimal("0.2"),
        budget=Decimal("10000"),
        strategy={"goal": "清库存"},
        idempotency_key="key-1",
    )
    result = publisher.submit_draft(ShopCredentials(tenant_id="t1"), draft)
    assert result.status == "DRAFT"
    assert result.platform_ref == "MOCK-key-1"


def test_taobao_gateway_requires_credentials() -> None:
    gateway = TaobaoShopGateway(Settings(platform_provider="taobao"))
    credentials = ShopCredentials(tenant_id="t1", platform="taobao")  # 无 app_key/session
    with pytest.raises(ValueError, match="AppKey/AppSecret"):
        gateway.list_products(credentials)


def test_taobao_gateway_only_uses_explicit_injected_transport() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def transport(gateway_url: str, params: dict[str, str]) -> dict[str, object]:
        calls.append((gateway_url, params))
        return {"items_onsale_get_response": {"items": {"item": []}}}

    settings = Settings(platform_provider="taobao")
    credentials = ShopCredentials(
        tenant_id="t1",
        platform="taobao",
        app_key="app-key",
        app_secret="app-secret",
        session_key="session-key",
    )
    gateway = TaobaoShopGateway(settings, transport=transport)

    assert gateway.list_products(credentials) == []
    assert calls[0][1]["method"] == "taobao.items.onsale.get"
    with pytest.raises(RuntimeError, match="disabled"):
        TaobaoShopGateway(settings).list_products(credentials)
    with pytest.raises(RuntimeError, match="disabled"):
        TaobaoShopGateway(settings).update_stock(credentials, "SKU-1", 1)


def test_taobao_orders_paginate_and_map_sku_id() -> None:
    calls: list[dict[str, str]] = []

    def transport(_gateway_url: str, params: dict[str, str]) -> dict[str, object]:
        calls.append(params)
        if params["page_no"] == "1":
            return {
                "trades_sold_get_response": {
                    "has_next": True,
                    "trades": {
                        "trade": [
                            {
                                "tid": "order-1",
                                "sku_id": "SKU-1",
                                "title": "first",
                                "num": "1",
                                "payment": "10.00",
                                "status": "TRADE_FINISHED",
                                "created": "2026-09-01T10:00:00",
                            }
                        ]
                    },
                }
            }
        return {
            "trades_sold_get_response": {
                "has_next": False,
                "trades": {
                    "trade": [
                        {
                            "tid": "order-2",
                            "sku_id": "SKU-2",
                            "title": "second",
                            "num": "2",
                            "payment": "20.00",
                            "status": "TRADE_FINISHED",
                            "created": "2026-09-02T10:00:00",
                        }
                    ]
                },
            }
        }

    gateway = TaobaoShopGateway(Settings(platform_provider="taobao"), transport=transport)
    credentials = ShopCredentials(
        tenant_id="t1",
        platform="taobao",
        app_key="app-key",
        app_secret="app-secret",
        session_key="session-key",
    )

    orders = gateway.list_orders(
        credentials,
        date_from="2026-09-01",
        date_to="2026-09-02",
        page_size=1,
    )

    assert [order.product_sku for order in orders] == ["SKU-1", "SKU-2"]
    assert [params["page_no"] for params in calls] == ["1", "2"]
    assert all("sku_id" in params["fields"] for params in calls)
    assert all(params["use_has_next"] == "true" for params in calls)


def test_taobao_orders_reject_missing_pagination_state() -> None:
    def transport(_gateway_url: str, _params: dict[str, str]) -> dict[str, object]:
        return {"trades_sold_get_response": {"trades": {"trade": []}}}

    gateway = TaobaoShopGateway(Settings(platform_provider="taobao"), transport=transport)
    credentials = ShopCredentials(
        tenant_id="t1",
        platform="taobao",
        app_key="app-key",
        app_secret="app-secret",
        session_key="session-key",
    )

    with pytest.raises(ValueError, match="has_next"):
        gateway.list_orders(credentials, date_from="2026-09-01", date_to="2026-09-02")


def test_taobao_publisher_keeps_draft_semantics() -> None:
    publisher = TaobaoCampaignPublisher(Settings(platform_provider="taobao"))
    draft = CampaignDraft(
        task_id="task-1",
        name="清库存活动",
        product_skus=("12345",),
        discount_rate=Decimal("0.2"),
        budget=Decimal("10000"),
        strategy={},
        idempotency_key="key-1",
    )
    result = publisher.submit_draft(ShopCredentials(tenant_id="t1", platform="taobao"), draft)
    assert result.status == "DRAFT"
    assert result.platform_ref.startswith("TOP-DRAFT-")


def test_factory_returns_mock_by_default(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        assert isinstance(get_shop_gateway(db), MockShopGateway)
        assert isinstance(get_campaign_publisher(), MockCampaignPublisher)
    finally:
        get_settings.cache_clear()


def test_factory_returns_taobao_when_configured(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATFORM_PROVIDER", "taobao")
    get_settings.cache_clear()
    try:
        assert isinstance(get_shop_gateway(db), TaobaoShopGateway)
        assert isinstance(get_campaign_publisher(), TaobaoCampaignPublisher)
    finally:
        get_settings.cache_clear()


def test_factory_rejects_unknown_provider(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_PROVIDER", "pinduoduo")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="PLATFORM_PROVIDER"):
            get_shop_gateway(db)
        with pytest.raises(ValueError, match="PLATFORM_PROVIDER"):
            get_campaign_publisher()
    finally:
        get_settings.cache_clear()


def test_demo_credentials_carries_platform_and_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_PROVIDER", "taobao")
    monkeypatch.setenv("TAOBAO_APP_KEY", "k")
    monkeypatch.setenv("TAOBAO_APP_SECRET", "s")
    monkeypatch.setenv("TAOBAO_SESSION_KEY", "token")
    get_settings.cache_clear()
    try:
        credentials = demo_credentials()
    finally:
        get_settings.cache_clear()
    assert credentials.platform == "taobao"
    assert credentials.app_key == "k"
    assert credentials.app_secret == "s"
    assert credentials.session_key == "token"


def test_sync_cli_uses_empty_credentials_for_mock(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.scripts import sync_platform_data

    captured: dict[str, object] = {}

    class SessionScope:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(sync_platform_data, "SessionLocal", SessionScope)
    monkeypatch.setattr(
        sync_platform_data,
        "get_settings",
        lambda: Settings(platform_provider="mock"),
    )
    monkeypatch.setattr(sync_platform_data, "get_shop_gateway", lambda *_args: object())

    def fake_sync(*_args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        captured["credentials"] = _args[2]
        return sync_platform_data.PlatformSyncReport(1, 2, 3, (), ())

    monkeypatch.setattr(sync_platform_data, "sync_shop_data", fake_sync)

    assert sync_platform_data.main(["--date-from", "2026-09-01", "--date-to", "2026-09-02"]) == 0
    assert captured["credentials"] == ShopCredentials(tenant_id="demo-tenant")
    assert "products_updated=1" in capsys.readouterr().out


def test_sync_cli_passes_taobao_credentials_without_printing_them(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.scripts import sync_platform_data

    captured: dict[str, object] = {}

    class SessionScope:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    settings = Settings(
        platform_provider="taobao",
        taobao_app_key="app-key",
        taobao_app_secret="app-secret",
        taobao_session_key="session-key",
    )
    monkeypatch.setattr(sync_platform_data, "SessionLocal", SessionScope)
    monkeypatch.setattr(sync_platform_data, "get_settings", lambda: settings)
    monkeypatch.setattr(sync_platform_data, "get_shop_gateway", lambda *_args: object())

    def fake_sync(*_args: object, **_kwargs: object) -> object:
        captured["credentials"] = _args[2]
        return sync_platform_data.PlatformSyncReport(0, 0, 0, (), ())

    monkeypatch.setattr(sync_platform_data, "sync_shop_data", fake_sync)

    assert sync_platform_data.main(["--date-from", "2026-09-01", "--date-to", "2026-09-02"]) == 0
    assert captured["credentials"] == ShopCredentials(
        tenant_id="demo-tenant",
        platform="taobao",
        app_key="app-key",
        app_secret="app-secret",
        session_key="session-key",
    )
    output = capsys.readouterr().out
    assert "app-secret" not in output
    assert "session-key" not in output


def test_sync_cli_rejects_inverted_date_range(capsys: pytest.CaptureFixture[str]) -> None:
    from app.scripts import sync_platform_data

    with pytest.raises(SystemExit) as error:
        sync_platform_data.main(["--date-from", "2026-09-02", "--date-to", "2026-09-01"])

    assert error.value.code == 2
    assert "--date-from must not be after --date-to" in capsys.readouterr().err


def test_sync_cli_runs_real_mock_gateway_and_sync_service(
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.scripts import sync_platform_data

    class SessionScope:
        def __enter__(self) -> Session:
            return seeded_db

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(sync_platform_data, "SessionLocal", SessionScope)
    monkeypatch.setattr(
        sync_platform_data,
        "get_settings",
        lambda: Settings(platform_provider="mock"),
    )
    today = date.today()

    assert (
        sync_platform_data.main(
            [
                "--date-from",
                (today - timedelta(days=7)).isoformat(),
                "--date-to",
                today.isoformat(),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "products_updated=120" in output
    sales_rows = output.split("sales_rows_updated=", maxsplit=1)[1].split(maxsplit=1)[0]
    assert int(sales_rows) > 0


def test_sync_cli_mock_syncs_every_qualifying_order_beyond_default_page_size(
    seeded_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.scripts import sync_platform_data

    class SessionScope:
        def __enter__(self) -> Session:
            return seeded_db

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(sync_platform_data, "SessionLocal", SessionScope)
    monkeypatch.setattr(
        sync_platform_data,
        "get_settings",
        lambda: Settings(platform_provider="mock"),
    )
    today = date.today()
    expected = seeded_db.scalar(
        select(func.count())
        .select_from(SalesDaily)
        .where(SalesDaily.date == today, SalesDaily.orders > 0)
    )
    assert expected is not None and expected > 50

    assert (
        sync_platform_data.main(
            ["--date-from", today.isoformat(), "--date-to", today.isoformat()]
        )
        == 0
    )
    output = capsys.readouterr().out
    sales_rows = output.split("sales_rows_updated=", maxsplit=1)[1].split(maxsplit=1)[0]
    assert int(sales_rows) == expected
