from collections.abc import Generator

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection
from psycopg.rows import dict_row

from app.config import get_settings
from app.schemas.tools import (
    BaselineWorkflowRequest,
    CampaignDraftResult,
    ComplianceResult,
    DiscountSimulationResult,
    InventoryItem,
    ModelCallTrace,
    PolicyEvidence,
    SalesMetric,
)


def checkpoint_database_url() -> str:
    database_url = get_settings().database_url
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            BaselineWorkflowRequest,
            CampaignDraftResult,
            ComplianceResult,
            DiscountSimulationResult,
            InventoryItem,
            ModelCallTrace,
            PolicyEvidence,
            SalesMetric,
        ]
    )


def get_checkpoint_saver() -> Generator[PostgresSaver, None, None]:
    with Connection.connect(
        checkpoint_database_url(),
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    ) as connection:
        saver = PostgresSaver(connection, serde=checkpoint_serializer())
        saver.setup()
        yield saver
