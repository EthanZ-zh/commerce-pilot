from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db
from app.main import app


def test_api_health_stats_and_baseline(
    seeded_db: Session,
    auth_headers: Callable[[str, str], dict[str, str]],
) -> None:
    def override_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            assert client.get("/").status_code == 200
            health = client.get("/api/v1/health")
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}

            stats = client.get("/api/v1/stats")
            assert stats.status_code == 200
            assert stats.json()["products"] == 120

            response = client.post(
                "/api/v1/workflows/baseline",
                json={
                    "category": "耳机",
                    "region": "华南",
                    "turnover_days_threshold": 1,
                    "max_products": 2,
                },
                headers=auth_headers("analyst", "campaign-analyst"),
            )
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "DRAFT_CREATED"
            assert body["compliance"]["passed"] is True
            assert len(body["campaign_drafts"]) == 2

            multi_agent = client.post(
                "/api/v1/workflows/multi-agent",
                json={
                    "category": "耳机",
                    "region": "华南",
                    "turnover_days_threshold": 1,
                    "max_products": 2,
                },
                headers=auth_headers("analyst", "campaign-analyst"),
            )
            assert multi_agent.status_code == 200
            agent_body = multi_agent.json()
            assert agent_body["execution_mode"] == "langgraph_supervisor_worker"
            assert agent_body["parallel_workers"] == [
                "business_analyst",
                "inventory_pricing",
                "policy_rag",
            ]
            assert agent_body["status"] == "DRAFT_CREATED"
    finally:
        app.dependency_overrides.clear()
