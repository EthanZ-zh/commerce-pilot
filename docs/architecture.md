# CommercePilot 五阶段核心架构与评测扩展

## 1. 分层

```text
FastAPI
  -> Baseline workflow（确定性编排）
      -> sales tool
      -> inventory tool
      -> pricing tool
      -> policy tool
      -> compliance tool
      -> campaign draft tool
          -> SQLAlchemy repositories/models
              -> PostgreSQL（生产）/ SQLite（测试）
```

第一阶段刻意不使用 LLM。第二阶段已将编排升级为 LangGraph Supervisor-Worker 图，并继续复用相同工具契约。

第二阶段已经实现以下图结构：

```text
START
  -> Supervisor
      ├─> Business Analyst Agent ─────┐
      ├─> Inventory & Pricing Agent ──┼─> Strategy Planner
      └─> Policy RAG Agent ───────────┘       -> Compliance Reviewer
                                                  -> Execution Service
                                                      -> END
```

三个 Worker 由 LangGraph 并行调度并使用独立数据库 Session。多入边 join 保证策略节点等待三份证据全部完成。执行服务仍只能创建 `DRAFT`，Agent 不能绕过人工审批。

第五阶段将 Supervisor 和 Strategy Planner 接入百炼。固定拓扑、低复杂度的 Supervisor 使用 `qwen3.7-flash`，证据综合和文案生成使用 `qwen3.7-plus`；Strategy 输入只保留任务约束、入选商品的关键指标和政策规则，避免发送重复业务字段。LangGraph 扇出、汇合和审批边仍由代码固定；模型不能改变商品集合、折扣、毛利或执行动作。无 Key 或 HTTP、Schema、语义校验失败时，节点降级为可重复验证的规则实现。

模型输出依次经过严格 JSON Schema、Pydantic 领域语义 validator 和独立 Compliance Reviewer。结构正确但声明未实现能力、反转库存指标、使用无证据热销词或高风险条款时，输出被拒绝或工作流终止。失败模型调用的 Token、延迟和错误仍被保留，避免降级掩盖成本。

政策 Worker 已进入第四阶段的混合 RAG：政策正文按内容分块，Embedding 写入 PostgreSQL pgvector；查询时分别执行 BM25 词法召回和 HNSW 向量 Top-K，再通过 RRF 融合并用 Reranker 精排。每条证据返回 chunk ID、词法分数、向量分数、融合分数、重排分数以及政策来源和版本。SQLite 测试使用等价的 Python 余弦回退。

RAG Provider 有两种模式：

- `deterministic`：本地哈希向量与词法重排，不需要 Key，供 CI 和降级使用；
- `dashscope`：百炼 `text-embedding-v4` 与 `qwen3-rerank`，用于真实模型演示。

政策语料由版本化目录维护，`sync_policy_catalog` 按政策 code 幂等新增或更新，不删除用户自定义政策，也不要求重置业务数据。评测层使用带相关政策 code 标注的查询集，统一计算 Recall@K、MRR 和 nDCG@K；pytest 使用确定性 Provider，真实百炼评测由显式脚本触发，防止 CI 产生费用。

Agent 端到端评测复用同一张 LangGraph，但向 `WorkflowContext` 注入独立 LLM/RAG Provider，并设置 `write_enabled=false`、`persist_audit=false`。因此 Supervisor、三个 Worker、Strategy 和 Compliance 都真实执行，Execution Service 则不能写活动，评测轨迹也不会污染业务审计表。评分器重新检查类目、区域、周转阈值、最大商品数、折扣、毛利、证据完整性和高风险文案，避免只相信工作流自报的 `compliance.passed`。

第三阶段在合规节点和执行服务之间加入持久化审批门：

```text
Compliance Reviewer
  ├─ 不通过 -> 终止，不创建活动
  └─ 通过 -> interrupt(BATCH approval payload)
                |
                | PostgreSQL Checkpointer
                | 服务可以停止或重启
                v
        APPROVED -> Execution Service -> DRAFT_CREATED
        REJECTED -> Terminal          -> REJECTED
```

`workflow_tasks` 保存面向 API 的任务状态和审批摘要，`workflow_approvals` 保存操作人、整批决定与理由。LangGraph 自有 checkpoint 表只保存图恢复状态，避免业务查询依赖框架内部表结构。

## 2. 关键边界

- Agent/Workflow 负责“选择做什么”；
- Tool 负责“可靠地执行”；
- Domain Service 负责价格、毛利和状态流转等确定性规则；
- Database 保存业务事实；
- 人工审批是活动从草稿进入执行态的唯一入口。

## 3. 后续多 Agent 映射

| 第一阶段工具 | 第二阶段使用者 |
|---|---|
| 销量查询 | Business Analyst Agent |
| 库存查询、折扣模拟 | Inventory & Pricing Agent |
| 政策检索 | Policy RAG Agent |
| 合规检查 | Compliance Reviewer Agent |
| 活动草稿创建 | 人工审批后的 Execution Service |

## 4. 状态与审计

- LangGraph state 只传递 Pydantic 业务对象和内部审计摘要；
- 并行节点只写各自字段，审计事件通过 reducer 合并；
- 每个 Agent 记录节点名、耗时、输入摘要、输出摘要和状态；
- 每次 LLM 调用记录 Provider、模型、输入/输出 Token、延迟、fallback 和错误；
- 任务 ID 包含工作流版本，避免与确定性基线的幂等键冲突；
- 返回轨迹按业务拓扑排序，便于 API 展示和离线评测。
- Checkpoint 反序列化只允许项目明确注册的 Pydantic 类型；
- 政策索引记录内容哈希和 Embedding 模型，模型切换时自动重建；
- 政策目录同步不删除非目录数据，检索质量由版本化评测集回归；
- Agent dry-run 使用依赖注入切换 Provider，并在执行层强制禁止业务写入；
- PostgreSQL 向量召回使用 cosine distance 和 HNSW 索引；
- `SELECT ... FOR UPDATE` 串行化同一任务的审批请求；
- 已结束任务再次审批返回 HTTP `409`；
- 审批通过前不会调用活动写入工具。

## 5. 数据与安全

- SQL 全部参数化；
- 工具入参和返回值全部使用 Pydantic；
- 活动草稿使用唯一幂等键；
- 三条工作流的执行服务都只能写入 `DRAFT`；
- 第三阶段只有 `APPROVED` 分支能够进入执行服务；
- 工具异常转换成可审计的工作流失败，不静默吞错。

## 6. 身份认证与权限边界

API 使用 FastAPI `HTTPBearer` 读取 JWT，由 PyJWT 校验 HS256 签名、`exp`、`iat`、`iss`、`aud`、`sub` 和角色声明。算法在 Settings 中限制为 HS256，避免请求或环境配置切换到未支持算法；生产环境拒绝开发默认 Secret 和少于 32 字节的 Secret。

| 角色 | 权限 |
|---|---|
| `analyst` | 运行 baseline/multi-agent，发起人工审批工作流 |
| `approver` | 查询审批任务并执行批准或拒绝 |
| `viewer` | 只读审批任务详情 |
| `admin` | 以上全部权限 |

审批 HTTP Schema 只接受决定和理由，领域层需要的 `operator` 由已验证 Principal 的 `sub` 创建，调用方无法通过请求体冒充他人。本地开发脚本只负责生成演示 Token，并在 `APP_ENV=production` 时拒绝运行；生产部署应改为 OIDC/OAuth2 身份提供方和非对称签名/JWKS。

## 7. OpenTelemetry 与 CI

FastAPI 自动埋点生成 HTTP SERVER/ASGI spans，业务层手工生成 `commerce_pilot.workflow.multi_agent`、`commerce_pilot.llm.generate` 和 `commerce_pilot.rag.retrieve` spans。工作流 span 记录 task ID、状态、商品数、Token、retry 和 fallback；LLM span 记录 Provider、模型、Token、attempts、异常和重试事件；RAG span 记录 Provider 模型、类别、limit、结果数和政策 codes。原始 Prompt、营销文案和 API Key 不写入 span。

遥测默认关闭，可选择 OTLP HTTP Batch exporter 或本地 Console exporter。`/api/v1/health` 被排除，避免健康探针制造大量无价值 Trace；启用遥测却未配置 exporter 时 Settings 校验直接失败。

GitHub Actions 使用 Python 3.11 和 pgvector PostgreSQL service，依次执行 Ruff、mypy、85% 覆盖率门禁、`pip check`、Alembic 全量升级和 `alembic check`。CI 环境强制 deterministic Provider，不配置 DashScope Key，因此 Pull Request 不产生外部模型调用。
