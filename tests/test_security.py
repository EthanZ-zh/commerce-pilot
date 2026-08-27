from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import DEVELOPMENT_JWT_SECRET, Settings, get_settings
from app.infrastructure.database import get_db
from app.main import app
from app.security import create_access_token, decode_access_token


def test_jwt_round_trip_and_expiration() -> None:
    settings = Settings(jwt_secret_key="unit-test-secret-key-at-least-thirty-two-bytes")
    token = create_access_token("approval-lead", {"approver"}, settings)

    principal = decode_access_token(token, settings)

    assert principal.subject == "approval-lead"
    assert principal.roles == {"approver"}

    expired = create_access_token(
        "approval-lead",
        {"approver"},
        settings,
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(expired, settings)
    assert exc_info.value.status_code == 401

    wrong_audience = settings.model_copy(update={"jwt_audience": "other-api"})
    with pytest.raises(HTTPException) as audience_error:
        decode_access_token(token, wrong_audience)
    assert audience_error.value.status_code == 401


def test_production_rejects_development_or_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="至少 32 字节"):
        Settings(app_env="production", jwt_secret_key=DEVELOPMENT_JWT_SECRET)
    with pytest.raises(ValidationError, match="至少 32 字节"):
        Settings(app_env="production", jwt_secret_key="too-short")


def test_demo_session_is_development_only() -> None:
    development = Settings(
        app_env="development",
        jwt_secret_key="development-test-secret-at-least-thirty-two-bytes",
    )
    app.dependency_overrides[get_settings] = lambda: development
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/demo-session", json={"role": "analyst"})
            assert response.status_code == 200
            body = response.json()
            assert body["subject"] == "demo-analyst"
            assert body["roles"] == ["analyst"]
            assert body["token_type"] == "bearer"
            assert decode_access_token(body["access_token"], development).roles == {
                "analyst"
            }

            invalid = client.post("/api/v1/auth/demo-session", json={"role": "admin"})
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()

    production = Settings(
        app_env="production",
        jwt_secret_key="production-secret-key-at-least-thirty-two-bytes",
    )
    app.dependency_overrides[get_settings] = lambda: production
    try:
        with TestClient(app) as client:
            unavailable = client.post(
                "/api/v1/auth/demo-session", json={"role": "approver"}
            )
            assert unavailable.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_workflow_api_enforces_authentication_and_roles(
    seeded_db: Session,
    auth_headers: Callable[[str, str], dict[str, str]],
) -> None:
    def override_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            missing = client.post("/api/v1/workflows/baseline", json={})
            assert missing.status_code == 401
            missing_stream = client.post("/api/v1/workflows/multi-agent/stream", json={})
            assert missing_stream.status_code == 401

            forbidden = client.post(
                "/api/v1/workflows/baseline",
                json={},
                headers=auth_headers("viewer", "audit-viewer"),
            )
            assert forbidden.status_code == 403

            invalid_token = create_access_token(
                "campaign-analyst",
                {"analyst"},
                Settings(jwt_secret_key="different-secret-key-at-least-thirty-two-bytes"),
            )
            invalid = client.post(
                "/api/v1/workflows/baseline",
                json={},
                headers={"Authorization": f"Bearer {invalid_token}"},
            )
            assert invalid.status_code == 401

            allowed = client.post(
                "/api/v1/workflows/baseline",
                json={"turnover_days_threshold": 1, "max_products": 1},
                headers=auth_headers("admin", "platform-admin"),
            )
            assert allowed.status_code == 200
    finally:
        app.dependency_overrides.clear()
