"""淘宝开放平台（TOP）适配器。

实现内容：
- top_sign：官方文档 md5 签名（key 升序、拼接 key+value、首尾加 AppSecret、MD5 大写）；
- build_request_params：组装公共参数与业务参数并签名；
- TaobaoShopGateway：构造 router/rest 请求并把注入 transport 返回的平台 JSON 映射为领域 DTO；
- TaobaoCampaignPublisher：只提交平台侧草稿（DRAFT 语义），不自动发布。

本模块不提供真实网络 transport，默认调用会明确失败。注入的 transport 只用于
签名、请求参数和响应映射测试；真实 OAuth、店铺调用和活动发布不在本项目范围内。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from decimal import Decimal

from app.config import Settings
from app.platform.contracts import (
    CampaignDraft,
    CampaignDraftResult,
    PlatformOrder,
    PlatformProduct,
    ShopCredentials,
)

TOP_GATEWAY_URL = "https://eco.taobao.com/router/rest"

ORDER_FIELDS = "tid,sku_id,title,num,payment,status,created"
PRODUCT_FIELDS = "num_iid,title,price,num,category_name"
MAX_ORDER_PAGES = 100
TopTransport = Callable[[str, dict[str, str]], dict[str, object]]


def top_sign(params: dict[str, str], app_secret: str) -> str:
    """淘宝 TOP 签名：key 按 ASCII 升序，拼接 key+value，首尾加 AppSecret 后 MD5 大写。"""
    ordered = "".join(f"{key}{params[key]}" for key in sorted(params))
    raw = f"{app_secret}{ordered}{app_secret}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def build_request_params(
    method: str,
    *,
    app_key: str,
    app_secret: str,
    session_key: str,
    biz_params: dict[str, str] | None = None,
    gateway_version: str = "2.0",
    timestamp: str | None = None,
) -> dict[str, str]:
    """组装公共参数 + 业务参数并签名（不含空值参数，空值不参与签名）。"""
    from datetime import UTC, datetime

    params: dict[str, str] = {
        "method": method,
        "app_key": app_key,
        "timestamp": timestamp or datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "format": "json",
        "v": gateway_version,
        "sign_method": "md5",
    }
    if session_key:
        params["session"] = session_key
    for key, value in (biz_params or {}).items():
        if value:
            params[key] = value
    params["sign"] = top_sign(params, app_secret)
    return params


def _require_credentials(credentials: ShopCredentials) -> None:
    if not credentials.app_key or not credentials.app_secret:
        raise ValueError("未配置淘宝开放平台 AppKey/AppSecret，无法调用 TOP API")
    if not credentials.session_key:
        raise ValueError("缺少商家授权 session key，请先完成 OAuth 授权")


def _parse_error(payload: dict[str, object]) -> str:
    error = payload.get("error_response")
    if isinstance(error, dict):
        return str(error.get("sub_msg") or error.get("msg") or "TOP API 调用失败")
    return "TOP API 调用失败"


class TaobaoShopGateway:
    platform = "taobao"

    def __init__(
        self,
        settings: Settings,
        gateway_url: str | None = None,
        *,
        transport: TopTransport | None = None,
    ) -> None:
        self._settings = settings
        self._gateway_url = gateway_url or settings.taobao_gateway_url or TOP_GATEWAY_URL
        self._transport = transport

    def _call(
        self, method: str, credentials: ShopCredentials, biz_params: dict[str, str]
    ) -> dict[str, object]:
        _require_credentials(credentials)
        params = build_request_params(
            method,
            app_key=credentials.app_key,
            app_secret=credentials.app_secret,
            session_key=credentials.session_key,
            biz_params=biz_params,
        )
        if self._transport is None:
            raise RuntimeError("TOP live transport is disabled in this project")
        payload = self._transport(self._gateway_url, params)
        if "error_response" in payload:
            raise ValueError(_parse_error(payload))
        return payload

    def list_products(
        self,
        credentials: ShopCredentials,
        *,
        category: str | None = None,
        region: str | None = None,
    ) -> list[PlatformProduct]:
        biz: dict[str, str] = {"fields": PRODUCT_FIELDS}
        if category:
            biz["category"] = category
        payload = self._call("taobao.items.onsale.get", credentials, biz)
        items = _dig(payload, "items_onsale_get_response", "items", "item")
        return [_to_platform_product(item) for item in (items if isinstance(items, list) else [])]

    def list_orders(
        self,
        credentials: ShopCredentials,
        *,
        date_from: str,
        date_to: str,
        page_size: int = 50,
    ) -> list[PlatformOrder]:
        orders: list[PlatformOrder] = []
        for page_no in range(1, MAX_ORDER_PAGES + 1):
            payload = self._call(
                "taobao.trades.sold.get",
                credentials,
                {
                    "fields": ORDER_FIELDS,
                    "start_created": date_from,
                    "end_created": date_to,
                    "status": "TRADE_FINISHED",
                    "page_size": str(page_size),
                    "page_no": str(page_no),
                    "use_has_next": "true",
                },
            )
            response = _dig(payload, "trades_sold_get_response")
            if not isinstance(response, dict):
                raise ValueError("TOP order response is missing trades_sold_get_response")
            trades = _dig(response, "trades", "trade")
            if isinstance(trades, list):
                orders.extend(_to_platform_order(trade) for trade in trades)
            if not _has_next(response):
                return orders
        raise ValueError(f"TOP order response exceeds {MAX_ORDER_PAGES} pages")

    def update_stock(self, credentials: ShopCredentials, sku: str, quantity: int) -> None:
        self._call(
            "taobao.item.quantity.update",
            credentials,
            {"num_iid": sku, "quantity": str(quantity)},
        )


class TaobaoCampaignPublisher:
    platform = "taobao"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def submit_draft(
        self, credentials: ShopCredentials, draft: CampaignDraft
    ) -> CampaignDraftResult:
        # 平台营销活动创建通常需要额外权限且随促销类型变化；当前只登记草稿语义，
        # 不执行自动发布。接入具体营销接口时在此处扩展。
        return CampaignDraftResult(
            platform_ref=f"TOP-DRAFT-{draft.idempotency_key}",
            status="DRAFT",
            detail="TOP 协议骨架：未创建平台草稿，发布动作保持人工审批（DRAFT only）",
        )


def _dig(payload: object, *path: str) -> object:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _has_next(response: dict[str, object]) -> bool:
    value = response.get("has_next")
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    raise ValueError("TOP order response is missing has_next pagination state")


def _to_platform_product(item: object) -> PlatformProduct:
    mapping = item if isinstance(item, dict) else {}
    price = Decimal(str(mapping.get("price") or "0"))
    stock = int(mapping.get("num") or 0)
    return PlatformProduct(
        sku=str(mapping.get("num_iid") or ""),
        title=str(mapping.get("title") or ""),
        category=str(mapping.get("category_name") or ""),
        region="",
        sale_price=price,
        available_stock=stock,
    )
def _to_platform_order(trade: object) -> PlatformOrder:
    from datetime import datetime

    mapping = trade if isinstance(trade, dict) else {}
    created = mapping.get("created")
    if not created:
        raise ValueError("TOP order is missing created timestamp")
    try:
        created_at = datetime.fromisoformat(str(created))
    except ValueError:
        raise ValueError("TOP order has invalid created timestamp") from None
    status = str(mapping.get("status") or "")
    if status == "TRADE_FINISHED":
        status = "FINISHED"
    return PlatformOrder(
        order_id=str(mapping.get("tid") or ""),
        product_sku=str(mapping.get("sku_id") or ""),
        title=str(mapping.get("title") or ""),
        quantity=int(mapping.get("num") or 0),
        paid_amount=Decimal(str(mapping.get("payment") or "0")),
        status=status,
        created_at=created_at,
    )
