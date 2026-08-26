import {
  Alert,
  Button,
  Card,
  Input,
  InputNumber,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import type { ScenarioInput } from "../types";
import { Icon } from "./Icon";

interface ScenarioPanelProps {
  value: ScenarioInput;
  onChange: (value: ScenarioInput) => void;
  onRunBaseline: () => void;
  onRunAgent: () => void;
  onSubmitApproval: () => void;
  baselineLoading: boolean;
  agentLoading: boolean;
  approvalLoading: boolean;
  authReady: boolean;
}

const categories = ["耳机", "智能手表", "键盘", "显示器"];
const regions = ["华南", "华东", "华北", "西南"];

export function ScenarioPanel({
  value,
  onChange,
  onRunBaseline,
  onRunAgent,
  onSubmitApproval,
  baselineLoading,
  agentLoading,
  approvalLoading,
  authReady,
}: ScenarioPanelProps) {
  const update = <K extends keyof ScenarioInput>(key: K, next: ScenarioInput[K]) => {
    onChange({ ...value, [key]: next });
  };

  return (
    <Card className="scenario-card" variant="borderless">
      <div className="section-heading">
        <div>
          <Typography.Text className="eyebrow">OPERATING BRIEF</Typography.Text>
          <Typography.Title level={3}>定义本次运营目标</Typography.Title>
        </div>
        <Tag color="cyan">真实 API</Tag>
      </div>

      <Alert
        className="scenario-note"
        type="info"
        showIcon
        title="模型负责规划，价格、毛利与活动写入由确定性工具控制"
      />

      <div className="form-grid">
        <label>
          <span>商品类目</span>
          <Select
            value={value.category}
            options={categories.map((item) => ({ value: item, label: item }))}
            onChange={(next) => update("category", next)}
          />
        </label>
        <label>
          <span>运营区域</span>
          <Select
            value={value.region}
            options={regions.map((item) => ({ value: item, label: item }))}
            onChange={(next) => update("region", next)}
          />
        </label>
        <label>
          <span>开始日期</span>
          <Input
            type="date"
            value={value.date_from}
            onChange={(event) => update("date_from", event.target.value)}
          />
        </label>
        <label>
          <span>结束日期</span>
          <Input
            type="date"
            value={value.date_to}
            onChange={(event) => update("date_to", event.target.value)}
          />
        </label>
        <label>
          <span>积压阈值（天）</span>
          <InputNumber
            min={1}
            max={3650}
            value={value.turnover_days_threshold}
            onChange={(next) => update("turnover_days_threshold", next ?? 60)}
          />
        </label>
        <label>
          <span>最多商品数</span>
          <InputNumber
            min={1}
            max={20}
            value={value.max_products}
            onChange={(next) => update("max_products", next ?? 5)}
          />
        </label>
        <label>
          <span>最大折扣率</span>
          <InputNumber
            min={0}
            max={0.9}
            step={0.05}
            value={value.max_discount_rate}
            onChange={(next) => update("max_discount_rate", next ?? 0.2)}
          />
        </label>
        <label>
          <span>最低毛利率</span>
          <InputNumber
            min={0}
            max={0.99}
            step={0.05}
            value={value.min_margin_rate}
            onChange={(next) => update("min_margin_rate", next ?? 0.15)}
          />
        </label>
        <label className="span-two">
          <span>活动预算</span>
          <div className="budget-control">
            <InputNumber
              min={1}
              value={value.budget}
              onChange={(next) => update("budget", next ?? 10000)}
            />
            <span>元</span>
          </div>
        </label>
        <label className="span-two">
          <span>业务目标</span>
          <Input.TextArea
            rows={3}
            value={value.goal}
            maxLength={500}
            showCount
            onChange={(event) => update("goal", event.target.value)}
          />
        </label>
      </div>

      <Space orientation="vertical" size={10} className="action-stack">
        <Button
          type="primary"
          size="large"
          block
          icon={<Icon name="play" size={17} />}
          loading={agentLoading}
          disabled={!authReady}
          onClick={onRunAgent}
        >
          运行多 Agent 分析
        </Button>
        <div className="secondary-actions">
          <Button
            icon={<Icon name="compare" size={16} />}
            loading={baselineLoading}
            disabled={!authReady}
            onClick={onRunBaseline}
          >
            运行确定性基线
          </Button>
          <Button
            icon={<Icon name="send" size={16} />}
            loading={approvalLoading}
            disabled={!authReady}
            onClick={onSubmitApproval}
          >
            提交人工审批
          </Button>
        </div>
      </Space>
    </Card>
  );
}
