from __future__ import annotations

import time
from typing import Any, cast
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.models import AgentRun, WorkflowApproval, WorkflowTask
from app.llm.providers import get_agent_model_provider
from app.schemas.tools import (
    ApprovalDecisionRequest,
    ApprovalWorkflowDecisionResult,
    ApprovalWorkflowStartResult,
    BaselineWorkflowRequest,
    TraceEvent,
    WorkflowTaskView,
)
from app.workflows.multi_agent import (
    PARALLEL_WORKERS,
    AgentAudit,
    MultiAgentState,
    WorkflowContext,
    _audit,
    _digest,
    _jsonable,
    business_analyst,
    compliance_reviewer,
    execution_service,
    inventory_pricing,
    policy_rag,
    strategy_planner,
    supervisor,
)

APPROVAL_NODE_ORDER = [
    "supervisor",
    *PARALLEL_WORKERS,
    "strategy_planner",
    "compliance_reviewer",
    "approval_gate",
    "execution_service",
]
APPROVAL_WORKFLOW_VERSION = "approval-v5-evaluated-rag-routing"


class WorkflowNotFoundError(LookupError):
    pass


class WorkflowStateConflictError(RuntimeError):
    pass


def _approval_payload(state: MultiAgentState) -> dict[str, Any]:
    selected_ids = set(state["selected_products"])
    return {
        "approval_scope": "BATCH",
        "selected_products": state["selected_products"],
        "pricing": [
            row.model_dump(mode="json")
            for row in state["pricing"]
            if row.product_id in selected_ids
        ],
        "content": state["content"],
        "strategy": state["strategy"],
        "policies": [
            {
                "code": policy.code,
                "version": policy.version,
                "source": policy.source,
            }
            for policy in state["policies"]
        ],
        "compliance": state["compliance"].model_dump(mode="json"),
    }


def approval_gate(state: MultiAgentState) -> dict[str, Any]:
    started = time.monotonic()
    payload = _approval_payload(state)
    resumed = interrupt(payload)
    if not isinstance(resumed, dict):
        raise ValueError("审批恢复数据必须是对象")
    decision = resumed.get("decision")
    operator = resumed.get("operator")
    reason = resumed.get("reason", "")
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("审批决定必须为 APPROVED 或 REJECTED")
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError("审批操作人不能为空")
    if not isinstance(reason, str):
        raise ValueError("审批理由必须是字符串")
    output = {
        "approval_decision": decision,
        "approval_operator": operator.strip(),
        "approval_reason": reason.strip(),
    }
    return {
        **output,
        "audit_events": [_audit("approval_gate", payload, output, started)],
    }


def terminal_without_execution(state: MultiAgentState) -> dict[str, Any]:
    started = time.monotonic()
    if state.get("approval_decision") == "REJECTED":
        status = "REJECTED"
        detail = "batch approval rejected"
    elif state.get("candidate_count", 0):
        status = "COMPLIANCE_REJECTED"
        detail = "compliance did not pass"
    else:
        status = "NO_CANDIDATES"
        detail = "no candidate product"
    output = {"campaign_drafts": [], "terminal_status": status}
    return {
        **output,
        "audit_events": [
            _audit("execution_service", {"status": status}, output, started) | {"detail": detail}
        ],
    }


def route_after_compliance(state: MultiAgentState) -> str:
    if state["compliance"].passed and state["selected_products"]:
        return "approval_gate"
    return "terminal_without_execution"


def route_after_approval(state: MultiAgentState) -> str:
    if state["approval_decision"] == "APPROVED":
        return "execution_service"
    return "terminal_without_execution"


def build_approval_graph(checkpointer: BaseCheckpointSaver[Any]):
    builder = StateGraph(MultiAgentState, context_schema=WorkflowContext)
    builder.add_node("supervisor", supervisor)
    builder.add_node("business_analyst", business_analyst)
    builder.add_node("inventory_pricing", inventory_pricing)
    builder.add_node("policy_rag", policy_rag)
    builder.add_node("strategy_planner", strategy_planner)
    builder.add_node("compliance_reviewer", compliance_reviewer)
    builder.add_node("approval_gate", approval_gate)
    builder.add_node("execution_service", execution_service)
    builder.add_node("terminal_without_execution", terminal_without_execution)
    builder.add_edge(START, "supervisor")
    for worker in PARALLEL_WORKERS:
        builder.add_edge("supervisor", worker)
    builder.add_edge(PARALLEL_WORKERS, "strategy_planner")
    builder.add_edge("strategy_planner", "compliance_reviewer")
    builder.add_conditional_edges(
        "compliance_reviewer",
        route_after_compliance,
        {
            "approval_gate": "approval_gate",
            "terminal_without_execution": "terminal_without_execution",
        },
    )
    builder.add_conditional_edges(
        "approval_gate",
        route_after_approval,
        {
            "execution_service": "execution_service",
            "terminal_without_execution": "terminal_without_execution",
        },
    )
    builder.add_edge("execution_service", END)
    builder.add_edge("terminal_without_execution", END)
    return builder.compile(checkpointer=checkpointer, name="commerce-pilot-approval")


def _config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _ordered_audits(state: MultiAgentState) -> list[AgentAudit]:
    order = {node: index for index, node in enumerate(APPROVAL_NODE_ORDER)}
    return sorted(state["audit_events"], key=lambda item: order[item["node"]])


def _trace(audits: list[AgentAudit]) -> list[TraceEvent]:
    return [
        TraceEvent(
            node=event["node"],
            status=event["status"],
            latency_ms=event["latency_ms"],
            detail=event["detail"],
        )
        for event in audits
    ]


def _persist_audits(db: Session, task_id: str, audits: list[AgentAudit]) -> None:
    for event in audits:
        db.add(
            AgentRun(
                task_id=task_id,
                node=event["node"],
                input_digest=event["input_digest"],
                output_digest=event["output_digest"],
                latency_ms=event["latency_ms"],
                status=event["status"],
                error=event["error"],
            )
        )


def _task_view(task: WorkflowTask) -> WorkflowTaskView:
    return WorkflowTaskView(
        thread_id=task.thread_id,
        task_id=task.task_id,
        workflow_type=task.workflow_type,
        status=task.status,
        request=task.request_json,
        approval_payload=task.approval_payload,
        result=task.result_json,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def start_approval_workflow(
    db: Session,
    request: BaselineWorkflowRequest,
    checkpointer: BaseCheckpointSaver[Any],
) -> ApprovalWorkflowStartResult:
    thread_id = f"approval-{uuid4().hex}"
    fingerprint = _digest(
        {"workflow": APPROVAL_WORKFLOW_VERSION, **request.model_dump(mode="json")}
    )
    task_id = f"approval-{fingerprint[:16]}"
    task = WorkflowTask(
        thread_id=thread_id,
        task_id=task_id,
        workflow_type="approval_v1",
        status="RUNNING",
        request_json=request.model_dump(mode="json"),
    )
    db.add(task)
    db.commit()

    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    graph = build_approval_graph(checkpointer)
    try:
        raw_state = graph.invoke(
            {
                "request": request,
                "task_id": task_id,
                "audit_events": [],
                "model_calls": [],
            },
            config=_config(thread_id),
            context=WorkflowContext(
                session_factory=factory,
                agent_provider=get_agent_model_provider(),
            ),
        )
        state = cast(MultiAgentState, raw_state)
        interrupts = raw_state.get("__interrupt__", ())
        if interrupts:
            payload = cast(dict[str, Any], interrupts[0].value)
            status = "PENDING_APPROVAL"
        else:
            payload = None
            status = state["terminal_status"]
            audits = _ordered_audits(state)
            _persist_audits(db, task_id, audits)
        persisted_task = db.scalar(
            select(WorkflowTask).where(WorkflowTask.thread_id == thread_id)
        )
        if persisted_task is None:
            raise WorkflowNotFoundError(thread_id)
        persisted_task.status = status
        persisted_task.approval_payload = payload
        persisted_task.result_json = None if interrupts else _jsonable(state)
        db.commit()
        audits = _ordered_audits(state)
        return ApprovalWorkflowStartResult(
            thread_id=thread_id,
            task_id=task_id,
            status=status,
            selected_products=state["selected_products"],
            approval_payload=payload,
            campaign_drafts=state.get("campaign_drafts", []),
            trace=_trace(audits),
        )
    except Exception as exc:
        db.rollback()
        failed_task = db.scalar(
            select(WorkflowTask).where(WorkflowTask.thread_id == thread_id)
        )
        if failed_task is not None:
            failed_task.status = "FAILED"
            failed_task.error = str(exc)
            db.commit()
        raise


def decide_approval_workflow(
    db: Session,
    thread_id: str,
    decision: ApprovalDecisionRequest,
    checkpointer: BaseCheckpointSaver[Any],
) -> ApprovalWorkflowDecisionResult:
    task = db.scalar(
        select(WorkflowTask)
        .where(WorkflowTask.thread_id == thread_id)
        .with_for_update()
    )
    if task is None:
        raise WorkflowNotFoundError(thread_id)
    if task.status != "PENDING_APPROVAL":
        raise WorkflowStateConflictError(
            f"任务当前状态为 {task.status}，不能重复审批"
        )

    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    graph = build_approval_graph(checkpointer)
    resume_payload = decision.model_dump(mode="json")
    try:
        raw_state = graph.invoke(
            Command(resume=resume_payload),
            config=_config(thread_id),
            context=WorkflowContext(
                session_factory=factory,
                agent_provider=get_agent_model_provider(),
            ),
        )
        state = cast(MultiAgentState, raw_state)
        if raw_state.get("__interrupt__"):
            raise WorkflowStateConflictError("任务恢复后仍处于中断状态")
        drafts = state["campaign_drafts"]
        status = "DRAFT_CREATED" if decision.decision == "APPROVED" and drafts else "REJECTED"
        audits = _ordered_audits(state)
        _persist_audits(db, task.task_id, audits)
        db.add(
            WorkflowApproval(
                thread_id=thread_id,
                task_id=task.task_id,
                operator=decision.operator,
                decision=decision.decision,
                reason=decision.reason,
            )
        )
        task.status = status
        task.result_json = _jsonable(state)
        task.error = None
        db.commit()
        return ApprovalWorkflowDecisionResult(
            thread_id=thread_id,
            task_id=task.task_id,
            status=status,
            decision=decision.decision,
            operator=decision.operator,
            reason=decision.reason,
            campaign_drafts=drafts,
            trace=_trace(audits),
        )
    except Exception:
        db.rollback()
        raise


def get_workflow_task(db: Session, thread_id: str) -> WorkflowTaskView:
    task = db.scalar(select(WorkflowTask).where(WorkflowTask.thread_id == thread_id))
    if task is None:
        raise WorkflowNotFoundError(thread_id)
    return _task_view(task)


def list_pending_workflow_tasks(db: Session) -> list[WorkflowTaskView]:
    tasks = db.scalars(
        select(WorkflowTask)
        .where(WorkflowTask.status == "PENDING_APPROVAL")
        .order_by(WorkflowTask.created_at.asc())
    ).all()
    return [_task_view(task) for task in tasks]
