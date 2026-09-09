"""平台网关工厂：按 PLATFORM_PROVIDER 配置返回实现，业务代码不感知具体平台。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.platform.contracts import CampaignPublisher, ShopCredentials, ShopGateway
from app.platform.mock import MockCampaignPublisher, MockShopGateway
from app.platform.taobao import TaobaoCampaignPublisher, TaobaoShopGateway

SUPPORTED_PROVIDERS = ("mock", "taobao")


def get_shop_gateway(db: Session, settings: Settings | None = None) -> ShopGateway:
    resolved = settings or get_settings()
    if resolved.platform_provider == "mock":
        return MockShopGateway(db)
    if resolved.platform_provider == "taobao":
        return TaobaoShopGateway(resolved)
    raise ValueError(f"PLATFORM_PROVIDER 必须为 {' 或 '.join(SUPPORTED_PROVIDERS)}")


def get_campaign_publisher(settings: Settings | None = None) -> CampaignPublisher:
    resolved = settings or get_settings()
    if resolved.platform_provider == "mock":
        return MockCampaignPublisher()
    if resolved.platform_provider == "taobao":
        return TaobaoCampaignPublisher(resolved)
    raise ValueError(f"PLATFORM_PROVIDER 必须为 {' 或 '.join(SUPPORTED_PROVIDERS)}")


def demo_credentials(settings: Settings | None = None) -> ShopCredentials:
    """开发环境接入字段：Mock 无需密钥；TOP 值仅供离线协议映射测试。"""
    resolved = settings or get_settings()
    return ShopCredentials(
        tenant_id="demo-tenant",
        platform=resolved.platform_provider,
        app_key=resolved.taobao_app_key,
        app_secret=resolved.taobao_app_secret,
        session_key=resolved.taobao_session_key,
    )
