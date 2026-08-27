from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SalesQuery(StrictModel):
    category: str = Field(min_length=1, max_length=80)
    region: str = Field(min_length=1, max_length=40)
    date_from: date
    date_to: date
    limit: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def validate_dates(self) -> SalesQuery:
        if self.date_from > self.date_to:
            raise ValueError("date_from 不能晚于 date_to")
        return self


class SalesMetric(StrictModel):
    product_id: int
    sku: str
    title: str
    category: str
    region: str
    views: int
    clicks: int
    orders: int
    revenue: Decimal
    conversion_rate: Decimal


class InventoryQuery(StrictModel):
    category: str = Field(min_length=1, max_length=80)
    region: str = Field(min_length=1, max_length=40)
    turnover_days_threshold: int = Field(default=60, ge=1, le=3650)
    limit: int = Field(default=50, ge=1, le=200)


class InventoryItem(StrictModel):
    product_id: int
    sku: str
    title: str
    cost_price: Decimal
    sale_price: Decimal
    available_stock: int
    inbound_stock: int
    turnover_days: int
    snapshot_date: date


class DiscountSimulationRequest(StrictModel):
    product_id: int
    cost_price: Decimal = Field(gt=0)
    sale_price: Decimal = Field(gt=0)
    max_discount_rate: Decimal = Field(ge=0, le=Decimal("0.90"))
    min_margin_rate: Decimal = Field(ge=0, lt=Decimal("1"))


class DiscountSimulationResult(StrictModel):
    product_id: int
    original_price: Decimal
    discounted_price: Decimal
    discount_rate: Decimal
    margin_rate: Decimal
    eligible: bool
    reason: str


class PolicyQuery(StrictModel):
    category: str = Field(default="营销", min_length=1, max_length=80)
    query_text: str = Field(
        default="促销活动价格、营销文案与审批规则", min_length=1, max_length=1000
    )
    as_of: date = Field(default_factory=date.today)
    limit: int = Field(default=10, ge=1, le=50)


class PolicyEvidence(StrictModel):
    policy_id: int
    code: str
    title: str
    content: str
    source: str
    version: str
    forbidden_terms: list[str]
    chunk_ids: list[int] = Field(default_factory=list)
    lexical_score: float = 0.0
    vector_score: float = 0.0
    fused_score: float = 0.0
    rerank_score: float = 0.0


class ComplianceRequest(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    marketing_copy: str = Field(min_length=1, max_length=3000)
    pricing: list[DiscountSimulationResult]
    policies: list[PolicyEvidence]
    max_discount_rate: Decimal = Field(ge=0, le=Decimal("0.90"))
    min_margin_rate: Decimal = Field(ge=0, lt=Decimal("1"))


class ComplianceResult(StrictModel):
    passed: bool
    violations: list[str]
    checked_policy_codes: list[str]


class CampaignDraftRequest(StrictModel):
    task_id: str = Field(min_length=1, max_length=50)
    product_id: int
    name: str = Field(min_length=1, max_length=200)
    discount_rate: Decimal = Field(ge=0, le=Decimal("0.90"))
    budget: Decimal = Field(gt=0)
    strategy: dict[str, Any]
    idempotency_key: str = Field(min_length=8, max_length=100)


class CampaignDraftResult(StrictModel):
    campaign_id: int
    task_id: str
    product_id: int
    status: str
    created: bool
    idempotency_key: str


class TraceEvent(StrictModel):
    node: str
    status: str
    latency_ms: int
    detail: str = ""


class ModelCallTrace(StrictModel):
    node: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    attempts: int = Field(default=1, ge=1)
    fallback_used: bool = False
    error: str | None = None


class DemoSessionRequest(StrictModel):
    role: Literal["analyst", "approver"]


class DemoSessionResult(StrictModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    subject: str
    roles: list[Literal["analyst", "approver"]]
    expires_in: int


class BaselineWorkflowRequest(StrictModel):
    category: str = Field(default="耳机", min_length=1, max_length=80)
    region: str = Field(default="华南", min_length=1, max_length=40)
    date_from: date = Field(default_factory=lambda: date.today() - timedelta(days=29))
    date_to: date = Field(default_factory=date.today)
    turnover_days_threshold: int = Field(default=60, ge=1, le=3650)
    max_discount_rate: Decimal = Field(default=Decimal("0.20"), ge=0, le=Decimal("0.90"))
    min_margin_rate: Decimal = Field(default=Decimal("0.15"), ge=0, lt=Decimal("1"))
    budget: Decimal = Field(default=Decimal("10000"), gt=0)
    goal: str = Field(default="清理积压库存并保持合理毛利", min_length=1, max_length=500)
    max_products: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def validate_dates(self) -> BaselineWorkflowRequest:
        if self.date_from > self.date_to:
            raise ValueError("date_from 不能晚于 date_to")
        return self


class BaselineWorkflowResult(StrictModel):
    task_id: str
    status: str
    selected_products: list[int]
    sales_evidence: list[SalesMetric]
    inventory_evidence: list[InventoryItem]
    pricing: list[DiscountSimulationResult]
    policies: list[PolicyEvidence]
    strategy: dict[str, Any]
    content: dict[str, str]
    compliance: ComplianceResult
    campaign_drafts: list[CampaignDraftResult]
    trace: list[TraceEvent]
    created_at: datetime


class MultiAgentWorkflowResult(BaselineWorkflowResult):
    execution_mode: Literal["langgraph_supervisor_worker"]
    supervisor_plan: list[str]
    parallel_workers: list[str]
    model_calls: list[ModelCallTrace]


class WorkflowProgressEvent(StrictModel):
    event: Literal[
        "workflow_started",
        "node_started",
        "node_completed",
        "node_failed",
        "workflow_completed",
        "workflow_failed",
    ]
    task_id: str
    sequence: int = Field(ge=0)
    node: str | None = None
    status: Literal["RUNNING", "COMPLETED", "FAILED"]
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None
    result: MultiAgentWorkflowResult | None = None


class ApprovalDecisionRequest(StrictModel):
    operator: str = Field(min_length=1, max_length=100)
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> ApprovalDecisionRequest:
        if self.decision == "REJECTED" and not self.reason.strip():
            raise ValueError("拒绝时必须填写 reason")
        return self


class ApprovalActionRequest(StrictModel):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> ApprovalActionRequest:
        if self.decision == "REJECTED" and not self.reason.strip():
            raise ValueError("拒绝时必须填写 reason")
        return self


class ApprovalWorkflowStartResult(StrictModel):
    thread_id: str
    task_id: str
    status: str
    selected_products: list[int]
    approval_payload: dict[str, Any] | None
    campaign_drafts: list[CampaignDraftResult]
    trace: list[TraceEvent]


class ApprovalWorkflowDecisionResult(StrictModel):
    thread_id: str
    task_id: str
    status: str
    decision: Literal["APPROVED", "REJECTED"]
    operator: str
    reason: str
    campaign_drafts: list[CampaignDraftResult]
    trace: list[TraceEvent]


class WorkflowTaskView(StrictModel):
    thread_id: str
    task_id: str
    workflow_type: str
    status: str
    request: dict[str, Any]
    approval_payload: dict[str, Any] | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime
