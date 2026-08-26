import { describe, expect, it } from "vitest";

import { formatDuration, formatPercent, summarizeRun } from "./lib";

describe("run presentation helpers", () => {
  it("aggregates latency, tokens, retries and fallbacks", () => {
    const metrics = summarizeRun({
      trace: [
        { node: "supervisor", status: "ok", latency_ms: 20, detail: "" },
        { node: "strategy", status: "ok", latency_ms: 80, detail: "" },
      ],
      model_calls: [
        {
          node: "supervisor",
          provider: "dashscope",
          model: "flash",
          input_tokens: 10,
          output_tokens: 5,
          latency_ms: 20,
          attempts: 1,
          fallback_used: false,
          error: null,
        },
        {
          node: "strategy",
          provider: "dashscope",
          model: "plus",
          input_tokens: 20,
          output_tokens: 8,
          latency_ms: 80,
          attempts: 2,
          fallback_used: true,
          error: "timeout",
        },
      ],
    } as never);
    expect(metrics).toEqual({
      latencyMs: 100,
      inputTokens: 30,
      outputTokens: 13,
      retries: 1,
      fallbacks: 1,
    });
  });

  it("formats durations and rates for cards", () => {
    expect(formatDuration(420)).toBe("420 ms");
    expect(formatDuration(1250)).toBe("1.3 s");
    expect(formatPercent("0.2")).toBe("20.0%");
  });
});
