from __future__ import annotations

import json
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db
from app.main import app
from app.workflows.multi_agent import NODE_ORDER


def test_multi_agent_sse_stream_reports_every_node_and_final_result(
    seeded_db: Session,
    auth_headers: Callable[[str, str], dict[str, str]],
) -> None:
    def override_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/workflows/multi-agent/stream",
                json={
                    "category": "耳机",
                    "region": "华南",
                    "turnover_days_threshold": 1,
                    "max_products": 2,
                },
                headers=auth_headers("analyst", "campaign-analyst"),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[0]["event"] == "workflow_started"
    assert events[-1]["event"] == "workflow_completed"
    assert events[-1]["result"]["status"] == "DRAFT_CREATED"
    assert events[-1]["result"]["execution_mode"] == "langgraph_supervisor_worker"
    assert {event["node"] for event in events if event["event"] == "node_started"} == set(
        NODE_ORDER
    )
    assert {
        event["node"] for event in events if event["event"] == "node_completed"
    } == set(NODE_ORDER)
    assert [event["sequence"] for event in events] == sorted(
        event["sequence"] for event in events
    )
