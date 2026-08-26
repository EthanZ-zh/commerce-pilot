from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.domain.models import Policy, PolicyChunk, Product, SalesDaily
from app.infrastructure.checkpoint import get_checkpoint_saver
from app.infrastructure.database import get_db
from app.schemas.tools import (
    ApprovalActionRequest,
    ApprovalDecisionRequest,
    ApprovalWorkflowDecisionResult,
    ApprovalWorkflowStartResult,
    BaselineWorkflowRequest,
    BaselineWorkflowResult,
    DemoSessionRequest,
    DemoSessionResult,
    MultiAgentWorkflowResult,
    WorkflowTaskView,
)
from app.security import Principal, create_access_token, require_roles
from app.workflows.approval import (
    WorkflowNotFoundError,
    WorkflowStateConflictError,
    decide_approval_workflow,
    get_workflow_task,
    list_pending_workflow_tasks,
    start_approval_workflow,
)
from app.workflows.baseline import run_baseline_workflow
from app.workflows.multi_agent import run_multi_agent_workflow

router = APIRouter(prefix="/api/v1")
DatabaseSession = Annotated[Session, Depends(get_db)]
CheckpointSaver = Annotated[PostgresSaver, Depends(get_checkpoint_saver)]
AnalystPrincipal = Annotated[Principal, Depends(require_roles("analyst"))]
ApprovalReader = Annotated[
    Principal, Depends(require_roles("approver", "viewer"))
]
ApproverPrincipal = Annotated[Principal, Depends(require_roles("approver"))]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.post("/auth/demo-session", response_model=DemoSessionResult)
def create_demo_session(request: DemoSessionRequest, settings: AppSettings) -> DemoSessionResult:
    if settings.app_env != "development":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="演示会话不可用")
    subject = "demo-analyst" if request.role == "analyst" else "demo-approver"
    token = create_access_token(subject, {request.role}, settings)
    return DemoSessionResult(
        access_token=token,
        subject=subject,
        roles=[request.role],
        expires_in=settings.jwt_access_token_minutes * 60,
    )


@router.get("/health")
def health(db: DatabaseSession) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/stats")
def stats(db: DatabaseSession) -> dict:
    return {
        "products": db.scalar(select(func.count()).select_from(Product)) or 0,
        "sales_daily": db.scalar(select(func.count()).select_from(SalesDaily)) or 0,
        "policies": db.scalar(select(func.count()).select_from(Policy)) or 0,
        "policy_chunks": db.scalar(select(func.count()).select_from(PolicyChunk)) or 0,
    }


@router.post("/workflows/baseline", response_model=BaselineWorkflowResult)
def baseline_workflow(
    request: BaselineWorkflowRequest,
    db: DatabaseSession,
    _principal: AnalystPrincipal,
) -> BaselineWorkflowResult:
    return run_baseline_workflow(db, request)


@router.post("/workflows/multi-agent", response_model=MultiAgentWorkflowResult)
def multi_agent_workflow(
    request: BaselineWorkflowRequest,
    db: DatabaseSession,
    _principal: AnalystPrincipal,
) -> MultiAgentWorkflowResult:
    return run_multi_agent_workflow(db, request)


@router.post(
    "/workflows/approval",
    response_model=ApprovalWorkflowStartResult,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_approval(
    request: BaselineWorkflowRequest,
    db: DatabaseSession,
    checkpointer: CheckpointSaver,
    _principal: AnalystPrincipal,
) -> ApprovalWorkflowStartResult:
    return start_approval_workflow(db, request, checkpointer)


@router.get("/workflows/approval/pending", response_model=list[WorkflowTaskView])
def list_pending_approvals(
    db: DatabaseSession, _principal: ApproverPrincipal
) -> list[WorkflowTaskView]:
    return list_pending_workflow_tasks(db)


@router.get("/workflows/approval/{thread_id}", response_model=WorkflowTaskView)
def get_approval(
    thread_id: str, db: DatabaseSession, _principal: ApprovalReader
) -> WorkflowTaskView:
    try:
        return get_workflow_task(db, thread_id)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/workflows/approval/{thread_id}/decision",
    response_model=ApprovalWorkflowDecisionResult,
)
def decide_approval(
    thread_id: str,
    action: ApprovalActionRequest,
    db: DatabaseSession,
    checkpointer: CheckpointSaver,
    principal: ApproverPrincipal,
) -> ApprovalWorkflowDecisionResult:
    try:
        decision = ApprovalDecisionRequest(
            operator=principal.subject,
            decision=action.decision,
            reason=action.reason,
        )
        return decide_approval_workflow(db, thread_id, decision, checkpointer)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowStateConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
