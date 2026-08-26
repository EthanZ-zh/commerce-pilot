from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, cast

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings
from app.llm.providers import DashScopeAgentModelProvider
from app.rag.providers import DeterministicRagProvider
from app.schemas.tools import BaselineWorkflowRequest
from app.workflows.multi_agent import run_multi_agent_workflow


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "goal_summary": "Clear constrained inventory",
                                "plan": [
                                    "Collect business evidence in parallel",
                                    "Generate a constrained strategy draft",
                                    "Review compliance before human approval",
                                ],
                                "risk_controls": [
                                    "Business numbers must come from tools",
                                    "Publishing requires human approval",
                                ],
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 42, "completion_tokens": 21},
        }


def test_enabled_telemetry_requires_an_exporter() -> None:
    with pytest.raises(ValidationError, match="OTLP endpoint 或 Console exporter"):
        Settings(otel_enabled=True)


def test_workflow_rag_and_llm_emit_diagnostic_spans(
    seeded_db: Session,
    monkeypatch,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    result = run_multi_agent_workflow(
        seeded_db,
        BaselineWorkflowRequest(
            turnover_days_threshold=1,
            max_products=2,
            max_discount_rate=Decimal("0.20"),
            min_margin_rate=Decimal("0.15"),
        ),
        rag_provider=DeterministicRagProvider(),
        write_enabled=False,
        persist_audit=False,
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResponse())
    DashScopeAgentModelProvider(
        Settings(dashscope_api_key="test-key")
    ).supervise(BaselineWorkflowRequest())

    spans = {span.name: span for span in exporter.get_finished_spans()}
    workflow_span = spans["commerce_pilot.workflow.multi_agent"]
    rag_span = spans["commerce_pilot.rag.retrieve"]
    llm_span = spans["commerce_pilot.llm.generate"]
    workflow_attributes = dict(workflow_span.attributes or {})
    rag_attributes = dict(rag_span.attributes or {})
    llm_attributes = dict(llm_span.attributes or {})

    assert workflow_attributes["commerce_pilot.task_id"] == result.task_id
    assert workflow_attributes["commerce_pilot.workflow.status"] == "EVALUATED"
    assert cast(int, rag_attributes["commerce_pilot.rag.result_count"]) >= 1
    assert llm_attributes["gen_ai.request.model"] == "qwen3.7-flash"
    assert llm_attributes["gen_ai.usage.input_tokens"] == 42
    assert llm_attributes["gen_ai.usage.output_tokens"] == 21
