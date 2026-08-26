from __future__ import annotations

import argparse

from app.evaluation.agent import evaluate_agent_workflow
from app.evaluation.agent_datasets import AGENT_EVALUATION_CASES
from app.infrastructure.database import SessionLocal
from app.llm.providers import (
    AgentModelProvider,
    DeterministicAgentModelProvider,
    get_agent_model_provider,
)
from app.rag.providers import DeterministicRagProvider, RagProvider, get_rag_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="执行无业务写入的 Agent 端到端评测")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="强制使用确定性 LLM 与 RAG Provider，不读取 .env 的 Provider 选择",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--limit",
        type=int,
        help="只运行前 N 个场景，适合控制真实模型评测成本",
    )
    selection.add_argument(
        "--case-id",
        choices=[case.case_id for case in AGENT_EVALUATION_CASES],
        help="只运行指定场景，适合复现单个失败或对抗用例",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit 必须大于 0")
    if args.case_id:
        cases = tuple(
            case for case in AGENT_EVALUATION_CASES if case.case_id == args.case_id
        )
    else:
        cases = AGENT_EVALUATION_CASES[: args.limit]
    agent_provider: AgentModelProvider
    rag_provider: RagProvider
    if args.offline:
        agent_provider = DeterministicAgentModelProvider()
        rag_provider = DeterministicRagProvider()
        mode = "offline"
    else:
        agent_provider = get_agent_model_provider()
        rag_provider = get_rag_provider()
        mode = "configured"
    with SessionLocal() as db:
        report = evaluate_agent_workflow(
            db, agent_provider, rag_provider, cases
        )
    print(
        f"mode={mode} cases={report.case_count} "
        f"task_success_rate={report.task_success_rate:.4f} "
        f"constraint_violation_rate={report.constraint_violation_rate:.4f} "
        f"fallback_rate={report.fallback_rate:.4f} "
        f"retry_rate={report.retry_rate:.4f} "
        f"input_tokens={report.total_input_tokens} "
        f"output_tokens={report.total_output_tokens} "
        f"avg_model_latency_ms={report.average_model_latency_ms:.2f}"
    )
    for case in report.cases:
        print(
            f"{case.case_id}: expected={case.expected_outcome} "
            f"actual={case.actual_outcome} success={case.task_succeeded} "
            f"selected={case.selected_products} fallbacks={case.fallback_calls} "
            f"attempts={case.model_attempts} models={list(case.models)} "
            f"violations={list(case.violations)} "
            f"fallback_errors={list(case.fallback_errors)}"
        )


if __name__ == "__main__":
    main()
