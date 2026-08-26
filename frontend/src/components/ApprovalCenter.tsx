import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Empty, Input, Modal, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { commerceApi } from "../api";
import type { ApprovalDecisionResult, ApprovalStartResult, WorkflowTask } from "../types";
import { Icon } from "./Icon";

interface ApprovalCenterProps {
  token?: string;
  latest?: ApprovalStartResult;
}

export function ApprovalCenter({ token, latest }: ApprovalCenterProps) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<WorkflowTask>();
  const [decision, setDecision] = useState<"APPROVED" | "REJECTED">("APPROVED");
  const [reason, setReason] = useState("预算、毛利和政策约束符合预期");
  const [decisionResult, setDecisionResult] = useState<ApprovalDecisionResult>();

  const pending = useQuery({
    queryKey: ["pending-approvals"],
    queryFn: () => commerceApi.pendingApprovals(token as string),
    enabled: Boolean(token),
    refetchInterval: 10_000,
  });

  const decide = useMutation({
    mutationFn: () =>
      commerceApi.decideApproval(
        selected?.thread_id ?? "",
        decision,
        reason,
        token as string,
      ),
    onSuccess: (result) => {
      setDecisionResult(result);
      setSelected(undefined);
      void queryClient.invalidateQueries({ queryKey: ["pending-approvals"] });
    },
  });

  const openDecision = (task: WorkflowTask, next: "APPROVED" | "REJECTED") => {
    setSelected(task);
    setDecision(next);
    setReason(next === "APPROVED" ? "预算、毛利和政策约束符合预期" : "策略风险需要进一步评估");
  };

  const columns: ColumnsType<WorkflowTask> = [
    {
      title: "任务",
      dataIndex: "task_id",
      render: (value: string, row) => (
        <div className="task-cell"><strong>{value}</strong><span>{row.thread_id.slice(0, 8)}…</span></div>
      ),
    },
    {
      title: "场景",
      render: (_, row) => `${row.request.category} · ${row.request.region}`,
    },
    {
      title: "状态",
      dataIndex: "status",
      render: (value: string) => <Tag color="processing">{value}</Tag>,
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      render: (value: string) => new Date(value).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      render: (_, row) => (
        <Space>
          <Button type="primary" size="small" onClick={() => openDecision(row, "APPROVED")}>批准</Button>
          <Button danger size="small" onClick={() => openDecision(row, "REJECTED")}>拒绝</Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="approval-stack">
      <Card className="approval-hero" variant="borderless">
        <div>
          <Typography.Text className="eyebrow">HUMAN-IN-THE-LOOP</Typography.Text>
          <Typography.Title level={2}>人工审批中心</Typography.Title>
          <Typography.Paragraph>
            Agent 只能准备策略与活动草稿，审批身份来自 JWT，批准后仍强制写入 DRAFT。
          </Typography.Paragraph>
        </div>
        <Icon name="clipboard" size={64} />
      </Card>

      {latest ? (
        <Alert
          type="success"
          showIcon
          title={`任务 ${latest.task_id} 已进入 ${latest.status}`}
          description="thread_id 已由页面内部保存，无需手工复制。"
        />
      ) : null}

      {decisionResult ? (
        <Alert
          type={decisionResult.decision === "APPROVED" ? "success" : "warning"}
          showIcon
          title={`审批结果：${decisionResult.status}`}
          description={
            decisionResult.decision === "APPROVED"
              ? `已生成 ${decisionResult.campaign_drafts.length} 个活动草稿，操作人 ${decisionResult.operator}`
              : `任务已拒绝，操作人 ${decisionResult.operator}`
          }
        />
      ) : null}

      <Card className="approval-table-card" variant="borderless">
        <div className="section-heading">
          <div>
            <Typography.Text className="eyebrow">APPROVAL QUEUE</Typography.Text>
            <Typography.Title level={3}>待审批任务</Typography.Title>
          </div>
          <Button
            icon={<Icon name="refresh" size={15} />}
            loading={pending.isFetching}
            onClick={() => void pending.refetch()}
          >
            刷新
          </Button>
        </div>
        <Table
          rowKey="thread_id"
          columns={columns}
          dataSource={pending.data ?? []}
          loading={pending.isLoading}
          pagination={false}
          locale={{ emptyText: <Empty description="当前没有待审批任务" /> }}
          scroll={{ x: 780 }}
        />
      </Card>

      <Modal
        title={decision === "APPROVED" ? "确认批准策略" : "确认拒绝策略"}
        open={Boolean(selected)}
        okText={decision === "APPROVED" ? "批准并生成草稿" : "确认拒绝"}
        cancelText="取消"
        okButtonProps={{ danger: decision === "REJECTED", loading: decide.isPending }}
        onCancel={() => setSelected(undefined)}
        onOk={() => decide.mutate()}
      >
        <div className="decision-dialog">
          {decision === "APPROVED" ? <Icon name="check" size={36} /> : <Icon name="x" size={36} />}
          <Typography.Paragraph>
            {selected?.request.category} · {selected?.request.region} · 预算 {selected?.request.budget} 元
          </Typography.Paragraph>
          <Input.TextArea rows={4} value={reason} onChange={(event) => setReason(event.target.value)} />
          {decide.error ? <Alert type="error" title={decide.error.message} showIcon /> : null}
        </div>
      </Modal>
    </div>
  );
}
