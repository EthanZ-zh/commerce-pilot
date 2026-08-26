from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "commerce-pilot-dev-only-secret-change-before-production"


class Settings(BaseSettings):
    app_name: str = "CommercePilot"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://commerce:commerce@localhost:5432/commerce_pilot"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    rag_provider: str = "deterministic"
    dashscope_api_key: str = ""
    dashscope_embedding_url: str = (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    )
    dashscope_rerank_url: str = (
        "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
    )
    dashscope_embedding_model: str = "text-embedding-v4"
    dashscope_rerank_model: str = "qwen3-rerank"
    rag_embedding_dimensions: int = 256
    rag_request_timeout_seconds: float = 20.0
    llm_provider: str = "deterministic"
    dashscope_chat_url: str = (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    dashscope_chat_model: str = "qwen3.7-plus"
    dashscope_supervisor_model: str = "qwen3.7-flash"
    dashscope_strategy_model: str = "qwen3.7-plus"
    llm_max_output_tokens: int = 800
    llm_request_timeout_seconds: float = 30.0
    llm_max_attempts: int = Field(default=2, ge=1, le=5)
    llm_retry_backoff_seconds: float = Field(default=0.25, ge=0, le=10)
    jwt_secret_key: str = DEVELOPMENT_JWT_SECRET
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "commerce-pilot"
    jwt_audience: str = "commerce-pilot-api"
    jwt_access_token_minutes: int = 60
    otel_enabled: bool = False
    otel_service_name: str = "commerce-pilot"
    otel_exporter_otlp_endpoint: str = ""
    otel_console_exporter: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def reject_insecure_production_jwt(self) -> "Settings":
        if self.app_env == "production" and (
            self.jwt_secret_key == DEVELOPMENT_JWT_SECRET
            or len(self.jwt_secret_key.encode("utf-8")) < 32
        ):
            raise ValueError("生产环境必须配置至少 32 字节的 JWT_SECRET_KEY")
        if (
            self.otel_enabled
            and not self.otel_console_exporter
            and not self.otel_exporter_otlp_endpoint
        ):
            raise ValueError("启用 OpenTelemetry 时必须配置 OTLP endpoint 或 Console exporter")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
