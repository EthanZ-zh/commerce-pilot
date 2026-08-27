import { describe, expect, it, vi } from "vitest";

import { consumeSseResponse } from "./api";
import type { WorkflowResult } from "./types";

function streamedResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": "text/event-stream" } },
  );
}

describe("SSE workflow client", () => {
  it("parses fragmented frames and returns the final workflow result", async () => {
    const result = { task_id: "agent-test", status: "DRAFT_CREATED" } as WorkflowResult;
    const started = {
      event: "node_started",
      task_id: "agent-test",
      sequence: 1,
      node: "supervisor",
      status: "RUNNING",
      latency_ms: null,
      detail: null,
      result: null,
    };
    const completed = {
      ...started,
      event: "workflow_completed",
      sequence: 2,
      node: null,
      status: "COMPLETED",
      result,
    };
    const onEvent = vi.fn();
    const payload = [
      `event: node_started\ndata: ${JSON.stringify(started)}\n\n`,
      `event: workflow_completed\ndata: ${JSON.stringify(completed)}\n\n`,
    ].join("");

    const parsed = await consumeSseResponse(
      streamedResponse([payload.slice(0, 37), payload.slice(37, 91), payload.slice(91)]),
      onEvent,
    );

    expect(parsed).toEqual(result);
    expect(onEvent).toHaveBeenCalledTimes(2);
  });

  it("turns a workflow_failed event into an API error", async () => {
    const failed = {
      event: "workflow_failed",
      task_id: "agent-test",
      sequence: 2,
      node: null,
      status: "FAILED",
      latency_ms: null,
      detail: "工作流执行失败（RuntimeError）",
      result: null,
    };

    await expect(
      consumeSseResponse(
        streamedResponse([`event: workflow_failed\ndata: ${JSON.stringify(failed)}\n\n`]),
        vi.fn(),
      ),
    ).rejects.toThrow(failed.detail);
  });
});
