from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.telemetry import configure_telemetry

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Multi-agent commerce operations with durable human approval.",
)
app.include_router(router)
configure_telemetry(app, settings)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "phase": "durable-human-approval",
    }
