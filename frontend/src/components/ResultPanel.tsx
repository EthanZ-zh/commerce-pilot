import { Card, Collapse, Empty, Progress, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDuration, formatPercent, summarizeRun } from "../lib";
import type {
  ModelCallTrace,
  PolicyEvidence,
  PricingResult,
  WorkflowProgressEvent,
  WorkflowResult,
} from "../types";
import { AgentFlow } from "./AgentFlow";
import { Icon } from "./Icon";

interface ResultPanelProps {
  result?: WorkflowResult;
  label: string;
  progress?: WorkflowProgressEvent[];
}

const pricingColumns: ColumnsType<PricingResult> = [
  { title: "商品 ID", dataIndex: "product_id", width: 88 },
  { title: "原价", dataIndex: "original_price" },
  { title: "折后价", dataIndex: "discounted_price" },
  {
    title: "折扣率",
    dataIndex: "discount_rate",
    render: (value: string | number) => formatPercent(value),
  },
  {
    title: "毛利率",
    dataIndex: "margin_rate",
    render: (value: string | number) => formatPercent(value),
  },
  {
    title: "结果",
    dataIndex: "eligible",
    render: (eligible: boolean) => (
      <Tag color={eligible ? "success" : "error"}>{eligible ? "可执行" : "拦截"}</Tag>
    ),
  },
];

const modelColumns: ColumnsType<ModelCallTrace> = [
  { title: "节点", dataIndex: "node" },
  { title: "模型", dataIndex: "model" },
  { title: "输入 Token", dataIndex: "input_tokens" },
  { title: "输出 Token", dataIndex: "output_tokens" },
  {
    title: "延迟",
    dataIndex: "latency_ms",
    render: (value: number) => formatDuration(value),
  },
  { title: "尝试次数", dataIndex: "attempts" },
  {
    title: "降级",
    dataIndex: "fallback_used",
    render: (value: boolean) => <Tag color={value ? "warning" : "success"}>{value ? "是" : "否"}</Tag>,
  },
];

function PolicyCard({ policy }: { policy: PolicyEvidence }) {
  const score = Math.max(policy.rerank_score, policy.fused_score, 0);
  return (
    <Card className="policy-card" variant="borderless">
      <div className="policy-title-row">
        <div>
          <Typography.Text className="policy-code">{policy.code}</Typography.Text>
          <Typography.Title level={5}>{policy.title}</Typography.Title>
        </div>
        <Tag color="blue">v{policy.version}</Tag>
      </div>
      <Typography.Paragraph ellipsis={{ rows: 3, expandable: true, symbol: "展开" }}>
        {policy.content}
      </Typography.Paragraph>
      <Progress
        percent={Math.min(100, Math.round(score * 100))}
        size="small"
        showInfo={false}
        strokeColor={{ "0%": "#6477ff", "100%": "#57d9a3" }}
      />
      <div className="policy-meta">
        <span>{policy.source}</span>
        <span>RRF {policy.fused_score.toFixed(3)}</span>
        <span>Rerank {policy.rerank_score.toFixed(3)}</span>
      </div>
    </Card>
  );
}

export function ResultPanel({ result, label, progress = [] }: ResultPanelProps) {
  if (!result) {
    if (progress.length) {
      const completed = progress.filter((event) => event.event === "node_completed").length;
      const failed = progress.some((event) => event.status === "FAILED");
      return (
        <div className="result-stack" data-testid="live-agent-progress">
          <Card className="result-header live-progress-header" variant="borderless">
            <div>
              <Typography.Text className="eyebrow">LIVE RUN · SSE</Typography.Text>
              <Typography.Title level={3}>{progress[0].task_id}</Typography.Title>
              <Typography.Text type="secondary">已完成 {completed} / 7 个 Agent 节点</Typography.Text>
            </div>
            <Tag color={failed ? "error" : "processing"}>{failed ? "执行失败" : "实时执行中"}</Tag>
          </Card>
          <div className="result-tabs live-progress-flow">
            <AgentFlow trace={[]} progress={progress} />
          </div>
        </div>
      );
    }
    return (
      <Card className="empty-result" variant="borderless">
        <Empty description="运行一个场景后，这里会展示真实 Agent 轨迹与证据" />
      </Card>
    );
  }

  const metrics = summarizeRun(result);
  const chartData = (result.model_calls ?? []).map((call) => ({
    node: call.node.replace("_planner", "").replace("_reviewer", ""),
    input: call.input_tokens,
    output: call.output_tokens,
  }));

  return (
    <div className="result-stack" data-testid="workflow-result">
      <Card className="result-header" variant="borderless">
        <div>
          <Typography.Text className="eyebrow">RUN RESULT · {label}</Typography.Text>
          <Typography.Title level={3}>{result.task_id}</Typography.Title>
          <Typography.Text type="secondary">
            {result.execution_mode ?? "deterministic_baseline"}
          </Typography.Text>
        </div>
        <div className="result-status-tags">
          {progress.length ? (
            <Tag color="processing" data-testid="sse-event-summary">
              SSE · {progress.length} 个实时事件
            </Tag>
          ) : null}
          <Tag color={result.compliance.passed ? "success" : "error"}>
            {result.compliance.passed ? "合规通过" : "策略被拦截"}
          </Tag>
        </div>
      </Card>

      <div className="metric-strip">
        <div><Icon name="layers" /><span>候选商品</span><strong>{result.selected_products.length}</strong></div>
        <div><Icon name="clock" /><span>节点总延迟</span><strong>{formatDuration(metrics.latencyMs)}</strong></div>
        <div><Icon name="coins" /><span>模型 Token</span><strong>{metrics.inputTokens + metrics.outputTokens}</strong></div>
        <div><Icon name="gauge" /><span>重试 / 降级</span><strong>{metrics.retries} / {metrics.fallbacks}</strong></div>
      </div>

      <Tabs
        className="result-tabs"
        defaultActiveKey="flow"
        items={[
          {
            key: "flow",
            label: "Agent 编排",
            children: (
              <>
                <AgentFlow trace={result.trace} progress={progress} />
                {result.supervisor_plan?.length ? (
                  <div className="plan-list">
                    {result.supervisor_plan.map((step, index) => (
                      <div key={`${step}-${index}`}><span>{index + 1}</span>{step}</div>
                    ))}
                  </div>
                ) : null}
              </>
            ),
          },
          {
            key: "evidence",
            label: "策略与证据",
            children: (
              <div className="evidence-layout">
                <Card className="evidence-card" variant="borderless">
                  <Typography.Title level={4}>定价模拟</Typography.Title>
                  <Table
                    rowKey="product_id"
                    columns={pricingColumns}
                    dataSource={result.pricing}
                    pagination={false}
                    size="small"
                    scroll={{ x: 680 }}
                  />
                </Card>
                <div className="policy-grid" data-testid="policy-evidence">
                  {result.policies.map((policy) => <PolicyCard key={policy.policy_id} policy={policy} />)}
                </div>
                <Collapse
                  items={[
                    {
                      key: "strategy",
                      label: "Strategy Planner 结构化输出",
                      children: <pre className="json-panel">{JSON.stringify(result.strategy, null, 2)}</pre>,
                    },
                    {
                      key: "copy",
                      label: "活动文案",
                      children: <pre className="json-panel">{JSON.stringify(result.content, null, 2)}</pre>,
                    },
                  ]}
                />
              </div>
            ),
          },
          {
            key: "observability",
            label: "模型与轨迹",
            children: (
              <div className="observability-grid">
                <Card className="chart-card" variant="borderless">
                  <Typography.Title level={4}>模型 Token 分布</Typography.Title>
                  {chartData.length ? (
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={chartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#273149" />
                        <XAxis dataKey="node" stroke="#8f9bb7" />
                        <YAxis stroke="#8f9bb7" />
                        <Tooltip contentStyle={{ background: "#111a2d", border: "1px solid #33405d" }} />
                        <Bar dataKey="input" fill="#6978ff" radius={[6, 6, 0, 0]} />
                        <Bar dataKey="output" fill="#57d9a3" radius={[6, 6, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : <Empty description="确定性基线没有模型调用" />}
                </Card>
                <Card className="evidence-card" variant="borderless">
                  <Typography.Title level={4}>模型调用</Typography.Title>
                  <Table
                    rowKey={(row) => `${row.node}-${row.model}`}
                    columns={modelColumns}
                    dataSource={result.model_calls ?? []}
                    pagination={false}
                    size="small"
                    scroll={{ x: 760 }}
                  />
                </Card>
                <div className="trace-list">
                  {result.trace.map((event) => (
                    <div key={`${event.node}-${event.latency_ms}`}>
                      {event.status.toLowerCase().includes("error") ? (
                        <Icon name="warning" size={17} />
                      ) : (
                        <Icon name="check" size={17} />
                      )}
                      <div><strong>{event.node}</strong><span>{event.detail || event.status}</span></div>
                      <small>{event.latency_ms} ms</small>
                    </div>
                  ))}
                </div>
              </div>
            ),
          },
          {
            key: "compliance",
            label: "合规结论",
            children: (
              <Card className="compliance-card" variant="borderless">
                <div className="compliance-hero">
                  {result.compliance.passed ? <Icon name="check" size={44} /> : <Icon name="warning" size={44} />}
                  <div>
                    <Typography.Title level={3}>
                      {result.compliance.passed ? "策略通过护栏" : "策略未通过护栏"}
                    </Typography.Title>
                    <Typography.Text type="secondary">
                      已检查政策：{result.compliance.checked_policy_codes.join("、") || "无"}
                    </Typography.Text>
                  </div>
                </div>
                {result.compliance.violations.length ? (
                  result.compliance.violations.map((item) => <Tag color="error" key={item}>{item}</Tag>)
                ) : (
                  <div className="compliance-ok"><Icon name="file" />未发现折扣、毛利或政策违规</div>
                )}
              </Card>
            ),
          },
        ]}
      />
    </div>
  );
}
