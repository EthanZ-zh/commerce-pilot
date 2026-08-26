export type DemoRole = "analyst" | "approver";

export interface DemoSession {
  access_token: string;
  token_type: "bearer";
  subject: string;
  roles: DemoRole[];
  expires_in: number;
}

export interface ScenarioInput {
  category: string;
  region: string;
  date_from: string;
  date_to: string;
  turnover_days_threshold: number;
  max_discount_rate: number;
  min_margin_rate: number;
  budget: number;
  goal: string;
  max_products: number;
}

export interface TraceEvent {
  node: string;
  status: string;
  latency_ms: number;
  detail: string;
}

export interface ModelCallTrace {
  node: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  attempts: number;
  fallback_used: boolean;
  error: string | null;
}

export interface PolicyEvidence {
  policy_id: number;
  code: string;
  title: string;
  content: string;
  source: string;
  version: string;
  forbidden_terms: string[];
  chunk_ids: number[];
  lexical_score: number;
  vector_score: number;
  fused_score: number;
  rerank_score: number;
}

export interface PricingResult {
  product_id: number;
  original_price: string | number;
  discounted_price: string | number;
  discount_rate: string | number;
  margin_rate: string | number;
  eligible: boolean;
  reason: string;
}

export interface CampaignDraft {
  campaign_id: number;
  task_id: string;
  product_id: number;
  status: string;
  created: boolean;
  idempotency_key: string;
}

export interface WorkflowResult {
  task_id: string;
  status: string;
  selected_products: number[];
  pricing: PricingResult[];
  policies: PolicyEvidence[];
  strategy: Record<string, unknown>;
  content: Record<string, string>;
  compliance: {
    passed: boolean;
    violations: string[];
    checked_policy_codes: string[];
  };
  campaign_drafts: CampaignDraft[];
  trace: TraceEvent[];
  created_at: string;
  execution_mode?: "langgraph_supervisor_worker";
  supervisor_plan?: string[];
  parallel_workers?: string[];
  model_calls?: ModelCallTrace[];
}

export interface ApprovalStartResult {
  thread_id: string;
  task_id: string;
  status: string;
  selected_products: number[];
  approval_payload: Record<string, unknown> | null;
  campaign_drafts: CampaignDraft[];
  trace: TraceEvent[];
}

export interface WorkflowTask {
  thread_id: string;
  task_id: string;
  workflow_type: string;
  status: string;
  request: ScenarioInput;
  approval_payload: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalDecisionResult {
  thread_id: string;
  task_id: string;
  status: string;
  decision: "APPROVED" | "REJECTED";
  operator: string;
  reason: string;
  campaign_drafts: CampaignDraft[];
  trace: TraceEvent[];
}

export interface PlatformStats {
  products: number;
  sales_daily: number;
  policies: number;
  policy_chunks: number;
}
