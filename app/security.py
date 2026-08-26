from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings, get_settings

Role = Literal["analyst", "approver", "viewer", "admin"]
KNOWN_ROLES: frozenset[str] = frozenset({"analyst", "approver", "viewer", "admin"})
bearer_scheme = HTTPBearer(auto_error=False)


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=100)
    roles: frozenset[Role] = Field(min_length=1)


class TokenClaims(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sub: str = Field(min_length=1, max_length=100)
    roles: frozenset[Role] = Field(min_length=1)


def create_access_token(
    subject: str,
    roles: set[Role],
    settings: Settings,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    principal = Principal(subject=subject, roles=roles)
    now = datetime.now(UTC)
    expires_at = now + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_minutes)
    )
    return jwt.encode(
        {
            "sub": principal.subject,
            "roles": sorted(principal.roles),
            "iat": now,
            "exp": expires_at,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings) -> Principal:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "roles", "iat", "exp", "iss", "aud"]},
        )
        claims = TokenClaims.model_validate(payload)
    except (InvalidTokenError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return Principal(subject=claims.sub, roles=claims.roles)


def get_current_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Bearer 访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(credentials.credentials, settings)


def require_roles(*required_roles: Role) -> Callable[..., Principal]:
    required = frozenset(required_roles)

    def authorize(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if "admin" not in principal.roles and principal.roles.isdisjoint(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要以下任一角色: {', '.join(sorted(required))}",
            )
        return principal

    return authorize
