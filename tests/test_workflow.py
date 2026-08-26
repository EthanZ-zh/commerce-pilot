from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.models import AgentRun, Campaign
from app.schemas.tools import BaselineWorkflowRequest
from app.workflows.baseline import run_baseline_workflow


def test_baseline_workflow_creates_audited_drafts(seeded_db: Session) -> None:
    request = BaselineWorkflowRequest(
        category="耳机",
        region="华南",
        turnover_days_threshold=1,
        max_discount_rate=Decimal("0.20"),
        min_margin_rate=Decimal("0.15"),
        max_products=3,
    )

    first = run_baseline_workflow(seeded_db, request)
    second = run_baseline_workflow(seeded_db, request)

    assert first.status == "DRAFT_CREATED"
    assert first.selected_products
    assert first.compliance.passed is True
    assert all(item.status == "DRAFT" for item in first.campaign_drafts)
    assert all(item.created is False for item in second.campaign_drafts)
    assert seeded_db.query(Campaign).count() == len(first.campaign_drafts)
    assert seeded_db.query(AgentRun).count() >= len(first.trace)


def test_baseline_workflow_handles_missing_candidates(seeded_db: Session) -> None:
    result = run_baseline_workflow(
        seeded_db,
        BaselineWorkflowRequest(category="不存在的类目", region="华南"),
    )

    assert result.status == "NO_CANDIDATES"
    assert result.campaign_drafts == []
    assert result.compliance.passed is False
