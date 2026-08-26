import type { ModelCallTrace, TraceEvent, WorkflowResult } from "./types";

export interface RunMetrics {
  latencyMs: number;
  inputTokens: number;
  outputTokens: number;
  retries: number;
  fallbacks: number;
}

export function summarizeRun(result?: WorkflowResult | null): RunMetrics {
  const trace = result?.trace ?? [];
  const calls = result?.model_calls ?? [];
  return {
    latencyMs: trace.reduce((sum: number, event: TraceEvent) => sum + event.latency_ms, 0),
    inputTokens: calls.reduce(
      (sum: number, call: ModelCallTrace) => sum + call.input_tokens,
      0,
    ),
    outputTokens: calls.reduce(
      (sum: number, call: ModelCallTrace) => sum + call.output_tokens,
      0,
    ),
    retries: calls.reduce(
      (sum: number, call: ModelCallTrace) => sum + Math.max(0, call.attempts - 1),
      0,
    ),
    fallbacks: calls.filter((call: ModelCallTrace) => call.fallback_used).length,
  };
}

export function formatDuration(milliseconds: number): string {
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

export function formatPercent(value: string | number): string {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(1)}%` : "-";
}
