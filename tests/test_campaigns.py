from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.models import Campaign, Product
from app.schemas.tools import CampaignDraftRequest
from app.tools.campaigns import create_campaign_draft


def test_campaign_draft_is_idempotent_and_never_published(db: Session) -> None:
    product = Product(
        sku="TEST-1",
        category="耳机",
        title="测试商品",
        region="华南",
        cost_price=Decimal("60"),
        sale_price=Decimal("100"),
    )
    db.add(product)
    db.flush()
    request = CampaignDraftRequest(
        task_id="task-1",
        product_id=product.id,
        name="库存优化活动",
        discount_rate=Decimal("0.10"),
        budget=Decimal("1000"),
        strategy={"approval_required": True},
        idempotency_key="idempotency-test-1",
    )

    first = create_campaign_draft(db, request)
    second = create_campaign_draft(db, request)

    assert first.created is True
    assert second.created is False
    assert first.campaign_id == second.campaign_id
    assert db.query(Campaign).count() == 1
    assert first.status == "DRAFT"
