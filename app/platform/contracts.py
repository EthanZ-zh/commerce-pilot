from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ShopCredentials:
    """一个平台店铺的接入字段。

    - mock：app_key/app_secret/session_key 均可为空；
    - taobao：仅供离线 TOP 签名与请求映射测试，不触发真实 OAuth 或店铺访问。
    """

    tenant_id: str
    platform: str = "mock"
    app_key: str = ""
    app_secret: str = ""
    session_key: str = ""


@dataclass(frozen=True, slots=True)
class PlatformProduct:
    sku: str
    title: str
    category: str
    region: str
    sale_price: Decimal
    available_stock: int
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class PlatformOrder:
    order_id: str
    product_sku: str
    title: str
    quantity: int
    paid_amount: Decimal
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CampaignDraft:
    """待发布活动草稿：折扣与预算由确定性工具计算，不允许模型直接填数。"""

    task_id: str
    name: str
    product_skus: tuple[str, ...]
    discount_rate: Decimal
    budget: Decimal
    strategy: dict[str, Any]
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class CampaignDraftResult:
    platform_ref: str
    status: str = "DRAFT"
    detail: str = ""


class ShopGateway(Protocol):
    """店铺数据网关：向业务层隐藏"数据来自哪个平台/本地库"的差异。"""

    def list_products(
        self,
        credentials: ShopCredentials,
        *,
        category: str | None = None,
        region: str | None = None,
    ) -> list[PlatformProduct]: ...

    def list_orders(
        self,
        credentials: ShopCredentials,
        *,
        date_from: str,
        date_to: str,
        page_size: int = 50,
    ) -> list[PlatformOrder]: ...

    def update_stock(self, credentials: ShopCredentials, sku: str, quantity: int) -> None: ...


class CampaignPublisher(Protocol):
    """活动草稿发布网关：业务层只提交 DRAFT，不承诺平台侧已生效发布。"""

    def submit_draft(
        self, credentials: ShopCredentials, draft: CampaignDraft
    ) -> CampaignDraftResult: ...


class TenantSessionStore(Protocol):
    """多店铺凭证存储：按 tenant_id 返回该店铺的授权凭证。"""

    def get(self, tenant_id: str) -> ShopCredentials | None: ...
