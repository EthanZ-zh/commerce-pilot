from __future__ import annotations

import json
import time
from typing import Annotated, Any, Protocol, TypeVar

import httpx
from opentelemetry import trace as otel_trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import Settings, get_settings
from app.schemas.tools import BaselineWorkflowRequest, ModelCallTrace
from app.telemetry import get_tracer


class LLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SupervisorDecision(LLMOutput):
    goal_summary: str = Field(min_length=1, max_length=300)
    plan: list[Annotated[str, Field(min_length=8, max_length=160)]] = Field(
        min_length=3, max_length=6
    )
    risk_controls: list[Annotated[str, Field(min_length=8, max_length=100)]] = Field(
        min_length=2, max_length=6
    )

    @model_validator(mode="after")
    def reject_unsupported_capabilities(self) -> SupervisorDecision:
        text = " ".join([*self.plan, *self.risk_controls])
        unsupported = ["销量预测", "定时任务", "自动发布", "直接发布", "修改真实价格"]
        negations = ["不", "无", "禁止", "严禁", "不得", "不能", "不会", "不支持", "不允许"]
        matched: list[str] = []
        for term in unsupported:
            offset = 0
            while (position := text.find(term, offset)) >= 0:
                prefix = text[max(0, position - 24) : position]
                if not any(negation in prefix for negation in negations):
                    matched.append(term)
                    break
                offset = position + len(term)
        if matched:
            raise ValueError(f"Supervisor 声明了未支持能力: {', '.join(matched)}")
        placeholders = [item for item in [*self.plan, *self.risk_controls] if "_" in item]
        if placeholders:
            raise ValueError("Supervisor 输出包含未解析占位符")
        return self


class StrategyDecision(LLMOutput):
    method: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=80)
    marketing_copy: str = Field(min_length=1, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def reject_misleading_inventory_claims(self) -> StrategyDecision:
        text = f"{self.title}\n{self.marketing_copy}"
        misleading = ["高周转潜力", "热销", "畅销", "爆款"]
        matched = [term for term in misleading if term in text]
        if matched:
            raise ValueError(f"策略包含无证据或反向库存表述: {', '.join(matched)}")
        return self


class AgentModelProvider(Protocol):
    def supervise(
        self, request: BaselineWorkflowRequest
    ) -> tuple[SupervisorDecision, ModelCallTrace]: ...

    def plan_strategy(
        self, evidence: dict[str, Any]
    ) -> tuple[StrategyDecision, ModelCallTrace]: ...


class DeterministicAgentModelProvider:
    def supervise(
        self, request: BaselineWorkflowRequest
    ) -> tuple[SupervisorDecision, ModelCallTrace]:
        decision = SupervisorDecision(
            goal_summary=(
                f"在固定安全边界内执行{request.region}{request.category}库存优化任务"
            ),
            plan=[
                "并行分析销量、库存定价和营销政策",
                "汇总证据并生成受约束的营销策略",
                "独立执行合规复核",
                "仅在复核通过后创建待审批活动草稿",
            ],
            risk_controls=["业务数字只采用工具证据", "活动发布必须经过人工审批"],
        )
        return decision, self._trace("supervisor")

    def plan_strategy(
        self, evidence: dict[str, Any]
    ) -> tuple[StrategyDecision, ModelCallTrace]:
        request = evidence.get("task", evidence.get("request", {}))
        decision = StrategyDecision(
            method="汇总三个 Worker 的证据后，在最低毛利约束内使用最大可行折扣",
            title=f"{request['region']}{request['category']}库存优化限时活动",
            marketing_copy=(
                f"面向{request['region']}地区精选{request['category']}商品提供限时优惠，"
                "活动价格经过成本、毛利与平台政策校验，具体优惠以活动草稿为准。"
            ),
            rationale="优先处理高周转天数库存，同时保留确定性价格、合规和审批边界。",
        )
        return decision, self._trace("strategy_planner")

    @staticmethod
    def _trace(node: str) -> ModelCallTrace:
        return ModelCallTrace(node=node, provider="deterministic", model="rules-v1")


OutputT = TypeVar("OutputT", bound=LLMOutput)


class AgentModelCallError(ValueError):
    def __init__(self, message: str, trace: ModelCallTrace) -> None:
        super().__init__(message)
        self.trace = trace


class DashScopeAgentModelProvider:
    def __init__(self, settings: Settings) -> None:
        if not settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        self.settings = settings

    def supervise(
        self, request: BaselineWorkflowRequest
    ) -> tuple[SupervisorDecision, ModelCallTrace]:
        return self._generate(
            node="supervisor",
            model=self.settings.dashscope_supervisor_model,
            output_type=SupervisorDecision,
            system_prompt=(
                "你是电商运营多Agent系统的Supervisor。只负责解释任务和给出执行计划；"
                "实际图拓扑固定为销量、库存定价、政策检索三个并行Worker，之后依次执行策略、"
                "合规、人工审批和草稿写入。Business Analyst只能汇总SQL历史销量，不能预测；"
                "Inventory Pricing只能读取当前库存并调用确定性折扣模拟；Policy RAG只能检索"
                "政策证据；Execution只能创建DRAFT。不得声称存在销量预测、定时任务、自动发布、"
                "直接发布或修改真实价格能力，不得让模型计算业务数字，不得绕过合规或人工审批。"
                "plan和risk_controls中的每一项必须是完整自然语言句子，不得输出字段名或占位符。"
            ),
            payload=request.model_dump(mode="json"),
        )

    def plan_strategy(
        self, evidence: dict[str, Any]
    ) -> tuple[StrategyDecision, ModelCallTrace]:
        return self._generate(
            node="strategy_planner",
            model=self.settings.dashscope_strategy_model,
            output_type=StrategyDecision,
            system_prompt=(
                "你是电商运营策略Agent。只能基于给定的SQL、定价和政策证据生成策略说明、"
                "活动标题和文案；不得新增商品、修改折扣或毛利数字，不得使用政策禁用词或"
                "绝对化承诺，不得使用‘最终解释权归平台所有’。文案必须说明具体优惠以草稿"
                "审批结果为准。周转天数高表示慢周转或库存积压，不得描述为高周转潜力、热销、"
                "畅销或爆款。只输出符合JSON Schema的对象。"
            ),
            payload=evidence,
        )

    def _generate(
        self,
        *,
        node: str,
        model: str,
        output_type: type[OutputT],
        system_prompt: str,
        payload: dict[str, Any],
    ) -> tuple[OutputT, ModelCallTrace]:
        started = time.monotonic()
        with get_tracer().start_as_current_span(
            "commerce_pilot.llm.generate",
            attributes={
                "gen_ai.system": "dashscope",
                "gen_ai.request.model": model,
                "commerce_pilot.agent.node": node,
            },
        ) as span:
            for attempt in range(1, self.settings.llm_max_attempts + 1):
                try:
                    output, call_trace = self._generate_untraced(
                        node=node,
                        model=model,
                        output_type=output_type,
                        system_prompt=system_prompt,
                        payload=payload,
                    )
                except AgentModelCallError as exc:
                    failed_trace = exc.trace.model_copy(
                        update={
                            "attempts": attempt,
                            "latency_ms": int((time.monotonic() - started) * 1000),
                        }
                    )
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                    raise AgentModelCallError(str(exc), failed_trace) from exc
                except httpx.HTTPError as exc:
                    if self._is_retryable(exc) and attempt < self.settings.llm_max_attempts:
                        span.add_event(
                            "commerce_pilot.llm.retry",
                            attributes={
                                "commerce_pilot.llm.attempt": attempt,
                                "exception.type": type(exc).__name__,
                            },
                        )
                        time.sleep(self.settings.llm_retry_backoff_seconds * attempt)
                        continue
                    failed_trace = ModelCallTrace(
                        node=node,
                        provider="dashscope",
                        model=model,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        attempts=attempt,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                    raise AgentModelCallError(str(exc), failed_trace) from exc
                call_trace = call_trace.model_copy(
                    update={
                        "attempts": attempt,
                        "latency_ms": int((time.monotonic() - started) * 1000),
                    }
                )
                break
            else:
                raise RuntimeError("LLM retry loop exited unexpectedly")
            span.set_attribute("gen_ai.usage.input_tokens", call_trace.input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", call_trace.output_tokens)
            span.set_attribute("commerce_pilot.llm.attempts", call_trace.attempts)
            span.set_attribute(
                "commerce_pilot.llm.latency_ms", call_trace.latency_ms
            )
            return output, call_trace

    @staticmethod
    def _is_retryable(exc: httpx.HTTPError) -> bool:
        if isinstance(
            exc,
            (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError),
        ):
            return True
        return isinstance(exc, httpx.HTTPStatusError) and (
            exc.response.status_code == 429 or exc.response.status_code >= 500
        )

    def _generate_untraced(
        self,
        *,
        node: str,
        model: str,
        output_type: type[OutputT],
        system_prompt: str,
        payload: dict[str, Any],
    ) -> tuple[OutputT, ModelCallTrace]:
        started = time.monotonic()
        response = httpx.post(
            self.settings.dashscope_chat_url,
            headers={
                "Authorization": f"Bearer {self.settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, default=str),
                    },
                ],
                "temperature": 0.1,
                "enable_thinking": False,
                "max_tokens": self.settings.llm_max_output_tokens,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": output_type.__name__,
                        "strict": True,
                        "schema": output_type.model_json_schema(),
                    },
                },
            },
            timeout=self.settings.llm_request_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage", {})
        trace = ModelCallTrace(
            node=node,
            provider="dashscope",
            model=model,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        try:
            content = body["choices"][0]["message"]["content"]
            output = output_type.model_validate_json(content)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            failed_trace = trace.model_copy(
                update={"error": f"{type(exc).__name__}: {exc}"}
            )
            raise AgentModelCallError(str(exc), failed_trace) from exc
        return output, trace


class FallbackAgentModelProvider:
    def __init__(
        self,
        primary: AgentModelProvider,
        fallback: AgentModelProvider,
        primary_model: str,
        primary_strategy_model: str | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.primary_model = primary_model
        self.primary_strategy_model = primary_strategy_model or primary_model

    def supervise(
        self, request: BaselineWorkflowRequest
    ) -> tuple[SupervisorDecision, ModelCallTrace]:
        try:
            return self.primary.supervise(request)
        except AgentModelCallError as exc:
            output, trace = self.fallback.supervise(request)
            return output, self._fallback_trace(trace, exc, self.primary_model, exc.trace)
        except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError) as exc:
            output, trace = self.fallback.supervise(request)
            return output, self._fallback_trace(trace, exc, self.primary_model)

    def plan_strategy(
        self, evidence: dict[str, Any]
    ) -> tuple[StrategyDecision, ModelCallTrace]:
        try:
            return self.primary.plan_strategy(evidence)
        except AgentModelCallError as exc:
            output, trace = self.fallback.plan_strategy(evidence)
            return output, self._fallback_trace(
                trace, exc, self.primary_strategy_model, exc.trace
            )
        except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError) as exc:
            output, trace = self.fallback.plan_strategy(evidence)
            return output, self._fallback_trace(trace, exc, self.primary_strategy_model)

    def _fallback_trace(
        self,
        trace: ModelCallTrace,
        exc: Exception,
        primary_model: str,
        primary_trace: ModelCallTrace | None = None,
    ) -> ModelCallTrace:
        observed = primary_trace or trace
        otel_trace.get_current_span().add_event(
            "commerce_pilot.llm.fallback",
            attributes={
                "commerce_pilot.llm.primary_model": primary_model,
                "exception.type": type(exc).__name__,
            },
        )
        return trace.model_copy(
            update={
                "provider": "dashscope->deterministic",
                "model": primary_model,
                "input_tokens": observed.input_tokens,
                "output_tokens": observed.output_tokens,
                "latency_ms": observed.latency_ms,
                "attempts": observed.attempts,
                "fallback_used": True,
                "error": observed.error or f"{type(exc).__name__}: {exc}",
            }
        )


def get_agent_model_provider(settings: Settings | None = None) -> AgentModelProvider:
    resolved = settings or get_settings()
    fallback = DeterministicAgentModelProvider()
    if resolved.llm_provider == "deterministic":
        return fallback
    if resolved.llm_provider != "dashscope":
        raise ValueError("LLM_PROVIDER 必须为 deterministic 或 dashscope")
    primary = DashScopeAgentModelProvider(resolved)
    return FallbackAgentModelProvider(
        primary,
        fallback,
        resolved.dashscope_supervisor_model,
        resolved.dashscope_strategy_model,
    )
