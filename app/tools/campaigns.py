from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Campaign, Product
from app.schemas.tools import CampaignDraftRequest, CampaignDraftResult


def create_campaign_draft(db: Session, request: CampaignDraftRequest) -> CampaignDraftResult:
    existing = db.scalar(
        select(Campaign).where(Campaign.idempotency_key == request.idempotency_key)
    )
    if existing:
        return CampaignDraftResult(
            campaign_id=existing.id,
            task_id=existing.task_id,
            product_id=existing.product_id,
            status=existing.status,
            created=False,
            idempotency_key=existing.idempotency_key,
        )

    if db.get(Product, request.product_id) is None:
        raise ValueError(f"商品不存在：{request.product_id}")

    campaign = Campaign(
        idempotency_key=request.idempotency_key,
        task_id=request.task_id,
        product_id=request.product_id,
        name=request.name,
        discount_rate=request.discount_rate,
        budget=request.budget,
        status="DRAFT",
        strategy_json=request.strategy,
    )
    db.add(campaign)
    db.flush()
    return CampaignDraftResult(
        campaign_id=campaign.id,
        task_id=campaign.task_id,
        product_id=campaign.product_id,
        status=campaign.status,
        created=True,
        idempotency_key=campaign.idempotency_key,
    )
