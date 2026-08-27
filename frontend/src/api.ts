import type {
  ApprovalDecisionResult,
  ApprovalStartResult,
  DemoRole,
  DemoSession,
  PlatformStats,
  ScenarioInput,
  WorkflowProgressEvent,
  WorkflowResult,
  WorkflowTask,
} from "./types";

const API_ROOT = import.meta.env.VITE_API_ROOT ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string | Array<{ msg?: string }> }
      | null;
    const detail = Array.isArray(payload?.detail)
      ? payload.detail.map((item) => item.msg).filter(Boolean).join("；")
      : payload?.detail;
    throw new ApiError(detail || `请求失败（HTTP ${response.status}）`, response.status);
  }
  return (await response.json()) as T;
}

async function parseError(response: Response): Promise<ApiError> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string | Array<{ msg?: string }> }
    | null;
  const detail = Array.isArray(payload?.detail)
    ? payload.detail.map((item) => item.msg).filter(Boolean).join("；")
    : payload?.detail;
  return new ApiError(detail || `请求失败（HTTP ${response.status}）`, response.status);
}

export async function consumeSseResponse(
  response: Response,
  onEvent: (event: WorkflowProgressEvent) => void,
): Promise<WorkflowResult> {
  if (!response.ok) throw await parseError(response);
  if (!response.body) throw new ApiError("浏览器未提供流式响应体", response.status);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: WorkflowResult | undefined;

  const consumeFrame = (frame: string) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!data) return;
    const event = JSON.parse(data) as WorkflowProgressEvent;
    onEvent(event);
    if (event.event === "workflow_failed") {
      throw new ApiError(event.detail || "工作流执行失败", 200);
    }
    if (event.event === "workflow_completed" && event.result) result = event.result;
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    frames.forEach(consumeFrame);
    if (done) break;
  }
  if (buffer.trim()) consumeFrame(buffer);
  if (!result) throw new ApiError("SSE 连接结束但未收到最终结果", 200);
  return result;
}

export const commerceApi = {
  health: () => request<{ status: string }>("/health"),
  stats: () => request<PlatformStats>("/stats"),
  demoSession: (role: DemoRole) =>
    request<DemoSession>("/auth/demo-session", {
      method: "POST",
      body: JSON.stringify({ role }),
    }),
  runBaseline: (input: ScenarioInput, token: string) =>
    request<WorkflowResult>(
      "/workflows/baseline",
      { method: "POST", body: JSON.stringify(input) },
      token,
    ),
  runMultiAgent: (input: ScenarioInput, token: string) =>
    request<WorkflowResult>(
      "/workflows/multi-agent",
      { method: "POST", body: JSON.stringify(input) },
      token,
    ),
  streamMultiAgent: async (
    input: ScenarioInput,
    token: string,
    onEvent: (event: WorkflowProgressEvent) => void,
  ) => {
    const response = await fetch(`${API_ROOT}/workflows/multi-agent/stream`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(input),
    });
    return consumeSseResponse(response, onEvent);
  },
  startApproval: (input: ScenarioInput, token: string) =>
    request<ApprovalStartResult>(
      "/workflows/approval",
      { method: "POST", body: JSON.stringify(input) },
      token,
    ),
  pendingApprovals: (token: string) =>
    request<WorkflowTask[]>("/workflows/approval/pending", {}, token),
  decideApproval: (
    threadId: string,
    decision: "APPROVED" | "REJECTED",
    reason: string,
    token: string,
  ) =>
    request<ApprovalDecisionResult>(
      `/workflows/approval/${threadId}/decision`,
      { method: "POST", body: JSON.stringify({ decision, reason }) },
      token,
    ),
};
