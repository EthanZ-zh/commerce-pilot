import { lazy, Suspense, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, Badge, Button, Card, Layout, Segmented, Space, Spin, Tag, Typography } from "antd";
import { commerceApi } from "./api";
import { Icon } from "./components/Icon";
import { ScenarioPanel } from "./components/ScenarioPanel";
import { formatDuration, summarizeRun } from "./lib";
import type { ApprovalStartResult, ScenarioInput, WorkflowResult } from "./types";

const ResultPanel = lazy(() =>
  import("./components/ResultPanel").then((module) => ({ default: module.ResultPanel })),
);
const ApprovalCenter = lazy(() =>
  import("./components/ApprovalCenter").then((module) => ({ default: module.ApprovalCenter })),
);

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function createDefaultScenario(): ScenarioInput {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  return {
    category: "耳机",
    region: "华南",
    date_from: isoDate(start),
    date_to: isoDate(end),
    turnover_days_threshold: 60,
    max_discount_rate: 0.2,
    min_margin_rate: 0.15,
    budget: 10000,
    goal: "清理积压库存并保持合理毛利",
    max_products: 5,
  };
}

export default function App() {
  const [scenario, setScenario] = useState(createDefaultScenario);
  const [section, setSection] = useState<"run" | "approval">("run");
  const [viewMode, setViewMode] = useState<"agent" | "baseline">("agent");
  const [agentResult, setAgentResult] = useState<WorkflowResult>();
  const [baselineResult, setBaselineResult] = useState<WorkflowResult>();
  const [approvalResult, setApprovalResult] = useState<ApprovalStartResult>();

  const health = useQuery({ queryKey: ["health"], queryFn: commerceApi.health, retry: 1 });
  const stats = useQuery({ queryKey: ["stats"], queryFn: commerceApi.stats, retry: 1 });
  const analystSession = useQuery({
    queryKey: ["demo-session", "analyst"],
    queryFn: () => commerceApi.demoSession("analyst"),
    retry: false,
  });
  const approverSession = useQuery({
    queryKey: ["demo-session", "approver"],
    queryFn: () => commerceApi.demoSession("approver"),
    retry: false,
  });

  const runAgent = useMutation({
    mutationFn: () => commerceApi.runMultiAgent(scenario, analystSession.data?.access_token ?? ""),
    onSuccess: (result) => {
      setAgentResult(result);
      setViewMode("agent");
    },
  });
  const runBaseline = useMutation({
    mutationFn: () => commerceApi.runBaseline(scenario, analystSession.data?.access_token ?? ""),
    onSuccess: (result) => {
      setBaselineResult(result);
      setViewMode("baseline");
    },
  });
  const startApproval = useMutation({
    mutationFn: () => commerceApi.startApproval(scenario, analystSession.data?.access_token ?? ""),
    onSuccess: (result) => {
      setApprovalResult(result);
      setSection("approval");
    },
  });

  const activeResult = viewMode === "agent" ? agentResult : baselineResult;
  const authReady = Boolean(analystSession.data && approverSession.data);
  const requestError = runAgent.error ?? runBaseline.error ?? startApproval.error;
  const comparison = useMemo(() => {
    if (!agentResult || !baselineResult) return undefined;
    return {
      agent: summarizeRun(agentResult),
      baseline: summarizeRun(baselineResult),
    };
  }, [agentResult, baselineResult]);

  return (
    <Layout className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Icon name="sparkles" size={22} /></div>
          <div><strong>CommercePilot</strong><span>Agent Operations Console</span></div>
        </div>
        <nav>
          <Button type={section === "run" ? "primary" : "text"} onClick={() => setSection("run")}>
            运行中心
          </Button>
          <Button
            type={section === "approval" ? "primary" : "text"}
            onClick={() => setSection("approval")}
          >
            审批中心
          </Button>
        </nav>
        <div className="system-state">
          <Badge status={health.data?.status === "ok" ? "success" : "error"} />
          <span>{health.data?.status === "ok" ? "Backend online" : "Backend offline"}</span>
          <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
            API <Icon name="external" size={13} />
          </a>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="hero-copy">
            <Tag color="geekblue">DETERMINISTIC-FIRST · HUMAN-GATED</Tag>
            <Typography.Title>把多 Agent 决策，变成可解释的运营动作。</Typography.Title>
            <Typography.Paragraph>
              Supervisor 调度销量、库存定价与政策 RAG Worker，结构化策略经过合规护栏和人工批准后，才允许生成活动草稿。
            </Typography.Paragraph>
            <Space wrap>
              <span><Icon name="bot" size={16} /> LangGraph Supervisor-Worker</span>
              <span><Icon name="shield" size={16} /> JWT / RBAC / Approval</span>
              <span><Icon name="activity" size={16} /> Trace / Token / Fallback</span>
            </Space>
          </div>
          <div className="platform-stats">
            <div><Icon name="boxes" /><strong>{stats.data?.products ?? "-"}</strong><span>商品</span></div>
            <div><Icon name="database" /><strong>{stats.data?.sales_daily ?? "-"}</strong><span>销售记录</span></div>
            <div><Icon name="shield" /><strong>{stats.data?.policies ?? "-"}</strong><span>版本化政策</span></div>
          </div>
        </section>

        {!authReady && !analystSession.isLoading && !approverSession.isLoading ? (
          <Alert
            className="global-alert"
            type="error"
            showIcon
            title="无法创建本地演示会话"
            description="确认 APP_ENV=development，FastAPI 已重启并包含 /api/v1/auth/demo-session。"
          />
        ) : null}

        {requestError ? (
          <Alert
            className="global-alert"
            type="error"
            showIcon
            closable
            title="工作流执行失败"
            description={requestError.message}
          />
        ) : null}

        {section === "run" ? (
          <div className="workspace-grid">
            <aside>
              <ScenarioPanel
                value={scenario}
                onChange={setScenario}
                onRunAgent={() => runAgent.mutate()}
                onRunBaseline={() => runBaseline.mutate()}
                onSubmitApproval={() => startApproval.mutate()}
                agentLoading={runAgent.isPending}
                baselineLoading={runBaseline.isPending}
                approvalLoading={startApproval.isPending}
                authReady={authReady}
              />
              {comparison ? (
                <Card className="comparison-card" variant="borderless">
                  <div className="section-heading compact">
                    <div><Typography.Text className="eyebrow">A/B COMPARISON</Typography.Text><Typography.Title level={4}>基线 vs 多 Agent</Typography.Title></div>
                    <Icon name="compare" size={22} />
                  </div>
                  <div className="comparison-row"><span>节点延迟</span><strong>{formatDuration(comparison.baseline.latencyMs)}</strong><strong>{formatDuration(comparison.agent.latencyMs)}</strong></div>
                  <div className="comparison-row"><span>模型 Token</span><strong>0</strong><strong>{comparison.agent.inputTokens + comparison.agent.outputTokens}</strong></div>
                  <div className="comparison-row"><span>重试 / 降级</span><strong>0 / 0</strong><strong>{comparison.agent.retries} / {comparison.agent.fallbacks}</strong></div>
                  <div className="comparison-legend"><span>指标</span><span>基线</span><span>Agent</span></div>
                </Card>
              ) : null}
            </aside>
            <section className="result-column">
              {(agentResult || baselineResult) ? (
                <Segmented
                  className="mode-switch"
                  value={viewMode}
                  onChange={(value) => setViewMode(value as "agent" | "baseline")}
                  options={[
                    { label: "多 Agent", value: "agent", disabled: !agentResult },
                    { label: "确定性基线", value: "baseline", disabled: !baselineResult },
                  ]}
                />
              ) : null}
              <Suspense fallback={<div className="loading-panel"><Spin size="large" /></div>}>
                <ResultPanel result={activeResult} label={viewMode === "agent" ? "MULTI-AGENT" : "BASELINE"} />
              </Suspense>
            </section>
          </div>
        ) : (
          <Suspense fallback={<div className="loading-panel"><Spin size="large" /></div>}>
            <ApprovalCenter token={approverSession.data?.access_token} latest={approvalResult} />
          </Suspense>
        )}
      </main>

      <footer>
        <span>CommercePilot · Portfolio Demo</span>
        <span>React → FastAPI → LangGraph → PostgreSQL / pgvector</span>
      </footer>
    </Layout>
  );
}
