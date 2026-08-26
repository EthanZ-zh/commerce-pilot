import type {
  ApprovalDecisionResult,
  ApprovalStartResult,
  DemoRole,
  DemoSession,
  PlatformStats,
  ScenarioInput,
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
