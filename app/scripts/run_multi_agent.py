import json

from app.infrastructure.database import SessionLocal
from app.schemas.tools import BaselineWorkflowRequest
from app.workflows.multi_agent import run_multi_agent_workflow


def main() -> None:
    with SessionLocal() as db:
        result = run_multi_agent_workflow(db, BaselineWorkflowRequest())
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
