import json

from app.infrastructure.database import SessionLocal
from app.schemas.tools import BaselineWorkflowRequest
from app.workflows.baseline import run_baseline_workflow


def main() -> None:
    with SessionLocal() as db:
        result = run_baseline_workflow(db, BaselineWorkflowRequest())
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
