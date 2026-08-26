import { useMemo } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";

import type { TraceEvent } from "../types";

const flowNodes: Array<{
  id: string;
  label: string;
  subtitle: string;
  position: { x: number; y: number };
}> = [
  { id: "supervisor", label: "Supervisor", subtitle: "目标拆解与路由", position: { x: 350, y: 0 } },
  {
    id: "business_analyst",
    label: "Sales Worker",
    subtitle: "销量与转化证据",
    position: { x: 20, y: 145 },
  },
  {
    id: "inventory_pricing",
    label: "Pricing Worker",
    subtitle: "库存、折扣与毛利",
    position: { x: 350, y: 145 },
  },
  {
    id: "policy_rag",
    label: "RAG Worker",
    subtitle: "政策检索与重排",
    position: { x: 680, y: 145 },
  },
  {
    id: "strategy_planner",
    label: "Strategy Planner",
    subtitle: "证据汇总与策略生成",
    position: { x: 200, y: 300 },
  },
  {
    id: "compliance_reviewer",
    label: "Compliance",
    subtitle: "政策与业务护栏",
    position: { x: 510, y: 300 },
  },
  {
    id: "execution_service",
    label: "Approval Gate",
    subtitle: "只允许 DRAFT 写入",
    position: { x: 350, y: 450 },
  },
];

const flowEdges: Edge[] = [
  ["supervisor", "business_analyst"],
  ["supervisor", "inventory_pricing"],
  ["supervisor", "policy_rag"],
  ["business_analyst", "strategy_planner"],
  ["inventory_pricing", "strategy_planner"],
  ["policy_rag", "compliance_reviewer"],
  ["strategy_planner", "compliance_reviewer"],
  ["compliance_reviewer", "execution_service"],
].map(([source, target], index) => ({
  id: `edge-${index}`,
  source,
  target,
  animated: true,
  markerEnd: { type: MarkerType.ArrowClosed },
  style: { stroke: "#6f7bff", strokeWidth: 1.5 },
}));

interface AgentFlowProps {
  trace: TraceEvent[];
}

export function AgentFlow({ trace }: AgentFlowProps) {
  const nodes = useMemo<Node[]>(
    () =>
      flowNodes.map((node) => {
        const event = trace.find((item) => item.node === node.id);
        const completed = Boolean(event);
        return {
          id: node.id,
          position: node.position,
          data: {
            label: (
              <div className="flow-node-content">
                <strong>{node.label}</strong>
                <span>{node.subtitle}</span>
                <small>{completed ? `${event?.latency_ms ?? 0} ms` : "等待运行"}</small>
              </div>
            ),
          },
          style: {
            width: 200,
            borderRadius: 16,
            border: completed ? "1px solid #57d9a3" : "1px solid #34405f",
            color: "#eef2ff",
            background: completed
              ? "linear-gradient(145deg, rgba(38, 116, 91, .96), rgba(22, 42, 57, .98))"
              : "linear-gradient(145deg, #182238, #11192b)",
            boxShadow: completed ? "0 12px 32px rgba(44, 190, 137, .18)" : "none",
            padding: 2,
          },
        };
      }),
    [trace],
  );

  return (
    <div className="agent-flow">
      <ReactFlow
        nodes={nodes}
        edges={flowEdges}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2d3753" gap={22} size={1} />
        <MiniMap pannable zoomable nodeColor="#6374ff" maskColor="rgba(7, 12, 23, .75)" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
