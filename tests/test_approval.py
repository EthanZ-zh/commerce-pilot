from collections.abc import Callable
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session

from app.domain.models import Campaign, WorkflowApproval, WorkflowTask
from app.infrastructure.checkpoint import checkpoint_serializer, get_checkpoint_saver
from app.infrastructure.database import get_db
from app.main import app
from app.schemas.tools import ApprovalDecisionRequest, BaselineWorkflowRequest
from app.workflows.approval import (
    APPROVAL_NODE_ORDER,
    WorkflowStateConflictError,
    decide_approval_workflow,
    list_pending_workflow_tasks,
    start_approval_workflow,
)


def approval_request() -> BaselineWorkflowRequest:
    return BaselineWorkflowRequest(
        category="耳机",
        region="华南",
        turnover_days_threshold=1,
        max_discount_rate=Decimal("0.20"),
        min_margin_rate=Decimal("0.15"),
        max_products=3,
    )


def memory_saver() -> MemorySaver:
    return MemorySaver(serde=checkpoint_serializer())


def test_approval_workflow_interrupts_and_resumes_after_approval(
    seeded_db: Session,
) -> None:
    checkpointer = memory_saver()

    started = start_approval_workflow(seeded_db, approval_request(), checkpointer)

    assert started.status == "PENDING_APPROVAL"
    assert started.approval_payload is not None
    assert started.approval_payload["approval_scope"] == "BATCH"
    assert started.campaign_drafts == []
    assert seeded_db.query(Campaign).count() == 0
    assert len(list_pending_workflow_tasks(seeded_db)) == 1

    decided = decide_approval_workflow(
        seeded_db,
        started.thread_id,
        ApprovalDecisionRequest(
            operator="campus-intern",
            decision="APPROVED",
            reason="预算和毛利符合预期",
        ),
        checkpointer,
    )

    assert decided.status == "DRAFT_CREATED"
    assert len(decided.campaign_drafts) == len(started.selected_products)
    assert [event.node for event in decided.trace] == APPROVAL_NODE_ORDER
    assert seeded_db.query(Campaign).count() == len(decided.campaign_drafts)
    assert seeded_db.query(WorkflowApproval).count() == 1
    assert seeded_db.query(WorkflowTask).one().status == "DRAFT_CREATED"
    assert list_pending_workflow_tasks(seeded_db) == []

    with pytest.raises(WorkflowStateConflictError, match="不能重复审批"):
        decide_approval_workflow(
            seeded_db,
            started.thread_id,
            ApprovalDecisionRequest(operator="another", decision="APPROVED"),
            checkpointer,
        )


def test_approval_workflow_rejection_ends_without_campaign(seeded_db: Session) -> None:
    checkpointer = memory_saver()
    started = start_approval_workflow(seeded_db, approval_request(), checkpointer)

    decided = decide_approval_workflow(
        seeded_db,
        started.thread_id,
        ApprovalDecisionRequest(
            operator="campus-intern",
            decision="REJECTED",
            reason="预算暂不批准",
        ),
        checkpointer,
    )

    assert decided.status == "REJECTED"
    assert decided.campaign_drafts == []
    assert seeded_db.query(Campaign).count() == 0
    approval = seeded_db.query(WorkflowApproval).one()
    assert approval.decision == "REJECTED"
    assert approval.reason == "预算暂不批准"


def test_approval_workflow_skips_human_gate_without_candidates(seeded_db: Session) -> None:
    result = start_approval_workflow(
        seeded_db,
        BaselineWorkflowRequest(category="不存在的类目", region="华南"),
        memory_saver(),
    )

    assert result.status == "NO_CANDIDATES"
    assert result.approval_payload is None
    assert list_pending_workflow_tasks(seeded_db) == []


def test_approval_api_start_list_and_approve(
    seeded_db: Session,
    auth_headers: Callable[[str, str], dict[str, str]],
) -> None:
    checkpointer = memory_saver()

    def override_db():
        yield seeded_db

    def override_checkpointer():
        yield checkpointer

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_checkpoint_saver] = override_checkpointer
    try:
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/workflows/approval",
                json={
                    "category": "耳机",
                    "region": "华南",
                    "turnover_days_threshold": 1,
                    "max_products": 2,
                },
                headers=auth_headers("analyst", "campaign-analyst"),
            )
            assert started.status_code == 202
            body = started.json()
            assert body["status"] == "PENDING_APPROVAL"

            analyst_pending = client.get(
                "/api/v1/workflows/approval/pending",
                headers=auth_headers("analyst", "campaign-analyst"),
            )
            assert analyst_pending.status_code == 403

            pending = client.get(
                "/api/v1/workflows/approval/pending",
                headers=auth_headers("approver", "approval-lead"),
            )
            assert pending.status_code == 200
            assert [item["thread_id"] for item in pending.json()] == [body["thread_id"]]

            spoofed = client.post(
                f"/api/v1/workflows/approval/{body['thread_id']}/decision",
                json={
                    "operator": "forged-admin",
                    "decision": "APPROVED",
                    "reason": "试图伪造审批人",
                },
                headers=auth_headers("approver", "approval-lead"),
            )
            assert spoofed.status_code == 422

            approved = client.post(
                f"/api/v1/workflows/approval/{body['thread_id']}/decision",
                json={
                    "decision": "APPROVED",
                    "reason": "同意整批活动",
                },
                headers=auth_headers("approver", "approval-lead"),
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "DRAFT_CREATED"
            assert approved.json()["operator"] == "approval-lead"
            assert seeded_db.query(WorkflowApproval).one().operator == "approval-lead"

            duplicate = client.post(
                f"/api/v1/workflows/approval/{body['thread_id']}/decision",
                json={"decision": "APPROVED"},
                headers=auth_headers("approver", "approval-lead"),
            )
            assert duplicate.status_code == 409
    finally:
        app.dependency_overrides.clear()
