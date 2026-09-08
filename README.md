# CommercePilot

CommercePilot 是一个面向电商运营的多 Agent 协作平台。仓库已完成确定性基线、LangGraph Supervisor-Worker 和可恢复人工审批：三个并行 Worker 完成销量分析、库存定价和政策检索，策略与合规节点汇总后暂停执行，只有人工整批批准才能创建活动草稿。

## 为什么先做确定性基线

- 业务数字来自 SQL 或公式，不交给 LLM 猜测；
- 工具契约先稳定，后续 Agent 只负责规划和选择工具；
- 可以对比单工作流和多 Agent 的任务完成率、延迟与 Token 成本；
- 在接入外部模型前就能完成测试和运行。

## 已实现

- PostgreSQL 业务模型：商品、日销售、库存、评价、政策、活动、审批、运行轨迹；
- 固定随机种子的演示数据：默认 500 个商品、90 天销量（45,000 条）；
- 六个确定性工具：销量、库存、折扣模拟、政策检索、合规检查、活动草稿；
- 政策分块、pgvector HNSW 索引与可追溯的检索分数；
- 8 条版本化政策目录与非破坏、幂等的同步命令；
- BM25 + 向量 Top-K + RRF 融合 + Reranker 的混合 RAG；
- 24 条检索评测集及 Recall@K、MRR、nDCG 离线评测；
- 6 类 Agent 端到端/对抗场景及任务成功率、约束违规率、重试、fallback、Token、延迟评测；
- 百炼 `text-embedding-v4` / `qwen3-rerank` 与无 Key 确定性降级；
- 百炼 `qwen3.7-flash` Supervisor 与 `qwen3.7-plus` Strategy Planner 分流；
- 严格 JSON Schema、Pydantic 语义护栏和确定性模型降级；
- LLM Token、延迟、模型、attempts、fallback 和错误轨迹；
- OpenTelemetry FastAPI、Workflow、LLM、RAG spans 与 OTLP/Console exporter；
- 活动草稿幂等、强制 `DRAFT`、人工审批约束；
- 无 LLM 基线 Workflow；
- LangGraph Supervisor + 三个并行 Worker；
- 独立策略汇总、合规复核和草稿执行节点；
- 基线与多 Agent 使用不同任务指纹，可做效果、延迟和轨迹对比；
- PostgreSQL Checkpointer 持久化 LangGraph 状态，支持服务重启后恢复；
- 整批人工批准/拒绝、待审批列表和任务状态 API；
- Bearer JWT 身份认证、角色授权与不可伪造的审批人身份；
- 审批操作人、决定、理由和 Agent 轨迹持久化；
- 数据库行锁、任务状态机和活动幂等共同防止重复审批与重复写入；
- FastAPI 健康检查、数据统计和 Workflow API；
- Alembic 业务模型、审批与 pgvector 三阶段迁移；
- PostgreSQL + Redis Docker Compose；
- GitHub Actions 覆盖率门禁、静态检查、依赖检查与真实 PostgreSQL 迁移检查；
- React + TypeScript Agent 运营控制台：工作流图、RAG 证据、模型指标、基线对比与人工审批；
- LangGraph `tasks/values` 流通过受 JWT 保护的 SSE 接口实时驱动节点运行、完成和失败状态；
- Docker Compose `demo` profile 一键启动 API、前端、PostgreSQL 和 Redis；
- pytest 单元与集成测试。

## 技术栈

- Python 3.11+
- FastAPI / Pydantic
- SQLAlchemy 2 / Alembic
- PostgreSQL / Redis
- pytest / Ruff / mypy
- Docker Compose
- React / TypeScript / Vite / Ant Design / React Flow
- 下一阶段：OIDC/JWKS、遥测看板与人工标注对抗评测

## 快速开始

### 0. 打开开发控制台

确保 Docker Desktop 已启动，然后执行：

```powershell
docker compose --profile demo up -d --build
```

打开：

- React 控制台：http://127.0.0.1:5173
- Swagger：http://127.0.0.1:8000/docs

控制台会在后端 `development` 环境中自动创建 analyst/approver 临时会话，JWT 和 `thread_id` 只在页面内部流转。点击“运行多 Agent”后，页面通过 SSE 实时展示 7 个 LangGraph 节点的等待、运行、完成或失败状态。生产环境不会开放演示会话接口。停止服务但保留数据库卷：

```powershell
docker compose --profile demo stop
```

若默认端口被占用，可以临时修改映射：

```powershell
$env:API_PORT = "8001"
$env:FRONTEND_PORT = "5174"
docker compose --profile demo up -d --build
```

前端本地开发：

```powershell
npm ci --prefix frontend
npm run dev --prefix frontend
```

运行真实浏览器端到端测试前，先启动 PostgreSQL，并确保数据库已迁移和播种：

~~~powershell
docker compose up -d postgres
$env:DATABASE_URL = "postgresql+psycopg://commerce:commerce@127.0.0.1:5432/commerce_pilot_e2e"
$env:E2E_DATABASE_URL = $env:DATABASE_URL
docker compose exec postgres createdb -U commerce commerce_pilot_e2e
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.scripts.seed
npm exec --prefix frontend playwright install chromium
$env:E2E_PYTHON = ".\.venv\Scripts\python.exe"
npm run test:e2e --prefix frontend
~~~

首次创建数据库后，若 `createdb` 提示数据库已经存在，可以继续后续命令。Playwright 默认使用独立的 `commerce_pilot_e2e`，自动启动 FastAPI 与 Vite，并以 deterministic Provider 验证“运行多 Agent、查看 RAG 证据、提交审批、批准并生成 DRAFT 活动”的完整页面闭环。失败时报告保存在 `frontend/playwright-report/`，CI 会上传对应产物。

### 1. 创建环境

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -U pip
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

### 2. 启动基础设施

```powershell
docker compose up -d postgres redis
docker compose ps
```

### 3. 初始化数据库和开发数据

```powershell
./.venv/Scripts/python.exe -m alembic upgrade head
./.venv/Scripts/python.exe -m app.scripts.seed
./.venv/Scripts/python.exe -m app.scripts.index_policies
```

默认生成：

- 500 个商品；
- 45,000 条日销售记录；
- 500 条库存快照；
- 500 条商品评价；
- 8 条版本化模拟平台政策。

默认 `RAG_PROVIDER=deterministic`，不产生外部调用。启用百炼真实向量与重排模型：

```dotenv
RAG_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-...
LLM_PROVIDER=dashscope
```

修改 Provider 后重新运行 `app.scripts.index_policies`，系统会按当前 Embedding 模型重建索引。API Key 只写入被 Git 忽略的 `.env`，不要提交到仓库。

只更新政策目录而不重置商品、活动或审批数据，并执行检索评测：

```powershell
./.venv/Scripts/python.exe -m app.scripts.sync_policies
./.venv/Scripts/python.exe -m app.scripts.index_policies
./.venv/Scripts/python.exe -m app.scripts.evaluate_rag
```

当前 24 条合成 smoke query 在确定性 Provider 上取得 Recall@3、MRR、nDCG@3 均为 1.0；其中最初 8 条已在真实 `text-embedding-v4` + `qwen3-rerank` 上取得相同结果。该数据集用于防止检索回归，不等同于真实用户流量效果，扩充人工标注难例后才适合做模型选型结论。真实 Provider 可用 `--limit` 控制评测费用。

执行不创建活动、不写 Agent 审计的端到端评测：

```powershell
# 4 个场景全部使用本地确定性 Provider
./.venv/Scripts/python.exe -m app.scripts.evaluate_agent --offline

# 使用 .env 配置的真实模型，只跑前 2 个场景控制费用
./.venv/Scripts/python.exe -m app.scripts.evaluate_agent --limit 2
```

评测覆盖正常清库存、不同类目区域、无候选商品、不可满足毛利、Prompt 注入和单商品边界，报告任务成功率、约束违规场景比例、retry/fallback 率、输入输出 Token 和平均模型延迟。可用 `--case-id prompt-injection-auto-publish` 单独复现对抗场景。真实评测应重复运行并保留 retry/fallback 错误，不能用单次结果代表模型稳定性。

不连接数据库、只验证百炼 Embedding 与 Rerank 凭证和接口：

```powershell
./.venv/Scripts/python.exe -m app.scripts.check_rag_provider
```

### 4. 运行基线

```powershell
./.venv/Scripts/python.exe -m app.scripts.run_baseline
```

### 5. 启动 API

```powershell
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

- Swagger：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health
- 数据统计：http://127.0.0.1:8000/api/v1/stats

工作流接口需要 JWT。开发环境可签发开发 Token；生产环境应接入真实身份提供方，禁止使用该脚本：

```powershell
$analystToken = ./.venv/Scripts/python.exe -m app.scripts.issue_dev_token `
  --subject campaign-analyst --roles analyst
$approverToken = ./.venv/Scripts/python.exe -m app.scripts.issue_dev_token `
  --subject approval-lead --roles approver
```

角色边界：`analyst` 可运行分析和发起审批，`approver` 可查看并决策审批，`viewer` 只读审批任务，`admin` 拥有全部权限。审批接口不接受客户端传入 `operator`，审批人固定取自 Token 的 `sub`。开发默认 Secret 只能本地使用；生产环境必须在 `.env` 配置至少 32 字节的 `JWT_SECRET_KEY`。

### 6. 运行 LangGraph 多 Agent

```powershell
./.venv/Scripts/python.exe -m app.scripts.run_multi_agent
```

或者调用 API：

```powershell
$body = @{
  category = "耳机"
  region = "华南"
  turnover_days_threshold = 60
  max_discount_rate = 0.20
  min_margin_rate = 0.15
  budget = 10000
  goal = "清理积压库存并保持合理毛利"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/workflows/multi-agent `
  -Headers @{ Authorization = "Bearer $analystToken" } `
  -ContentType application/json `
  -Body $body
```

图中的 `business_analyst`、`inventory_pricing`、`policy_rag` 从 Qwen Supervisor 同时扇出，全部完成后才进入 Qwen Strategy Planner。`policy_rag` 使用混合检索；图拓扑、商品筛选、折扣、毛利、合规和审批仍由代码与确定性工具控制。模型输出通过 JSON Schema、Pydantic 业务语义和独立 Compliance Reviewer 三层校验，失败时记录成本并降级到规则计划。无模型密钥时系统可完整运行本地确定性路径。

React 控制台调用 `POST /api/v1/workflows/multi-agent/stream`，以 `text/event-stream` 接收 `workflow_started`、`node_started`、`node_completed`、`node_failed`、`workflow_completed` 和 `workflow_failed`。它使用流式 `fetch` 携带 Bearer JWT，不把 Token 放入 URL；原同步接口继续保留给脚本和普通 API 调用。

基线 API 使用相同的 `$body`：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/workflows/baseline `
  -Headers @{ Authorization = "Bearer $analystToken" } `
  -ContentType application/json `
  -Body $body
```

### 7. 运行可恢复的人工审批

启动工作流后，系统返回 `202 Accepted`，此时不会创建活动：

```powershell
$started = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/workflows/approval `
  -Headers @{ Authorization = "Bearer $analystToken" } `
  -ContentType application/json `
  -Body $body

$started.status       # PENDING_APPROVAL
$started.thread_id
```

查询待审批任务并整批批准：

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/api/v1/workflows/approval/pending `
  -Headers @{ Authorization = "Bearer $approverToken" }

$decision = @{
  decision = "APPROVED"
  reason = "预算和毛利符合预期"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/workflows/approval/$($started.thread_id)/decision" `
  -Headers @{ Authorization = "Bearer $approverToken" } `
  -ContentType application/json `
  -Body $decision
```

拒绝时将 `decision` 改为 `REJECTED` 并填写 `reason`。拒绝后任务直接结束且不会创建活动。Checkpointer 表在首次调用审批接口时自动初始化。

## 验证

```powershell
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy app tests
```

测试默认使用 SQLite 内存数据库，不依赖 Docker。

GitHub Actions 在 Python 3.11 上执行相同检查，并启动 `pgvector/pgvector:pg16` service 完成全部 Alembic 升级和 schema drift 检查；CI 强制使用确定性 LLM/RAG Provider，不读取开发机密钥或产生付费调用。

## OpenTelemetry

默认不开启遥测。开发环境可把 Trace 输出到控制台：

```dotenv
OTEL_ENABLED=true
OTEL_CONSOLE_EXPORTER=true
OTEL_EXPORTER_OTLP_ENDPOINT=
```

接入 Jaeger、Tempo、Langfuse 或其他 OTLP 后端时，设置 HTTP traces endpoint，例如：

```dotenv
OTEL_ENABLED=true
OTEL_CONSOLE_EXPORTER=false
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

Trace 包含 HTTP 请求、工作流状态、task ID、入选商品数、LLM 模型/Token/attempts/fallback、RAG Provider/Top-K 政策等属性；健康检查被排除以减少探针噪声。开启遥测却没有配置任何 exporter 时应用拒绝启动，避免静默丢弃 spans。

## 安全边界

- 当前系统只创建活动草稿，不提供发布接口；
- 工作流 API 使用 Bearer JWT，并按 analyst、approver、viewer、admin 执行 RBAC；
- 审批操作人来自验证后的 JWT `sub`，请求体不能覆盖；
- JWT 校验签名、有效期、issuer、audience 和角色声明，算法固定为 HS256；
- 价格和毛利由 Decimal 公式计算；
- SQLAlchemy 生成参数化 SQL；
- 所有工具均使用严格 Pydantic 输入输出；
- 同一幂等键不会重复创建活动；
- 政策检索结果包含来源和版本；
- 执行轨迹只保存摘要哈希，不保存完整敏感输入。
- 审批任务使用行锁和状态检查，重复审批返回冲突；
- Checkpoint 只允许显式注册的项目类型参与反序列化。

## 目录

```text
app/
├── api/              # FastAPI 路由
├── domain/           # SQLAlchemy 业务模型
├── evaluation/       # RAG 数据集与评测指标
├── infrastructure/   # 数据库适配
├── policies/         # 版本化政策目录与同步
├── schemas/          # Pydantic 工具契约
├── scripts/          # 初始化、种子数据和运行命令
├── tools/            # 六个确定性业务工具
└── workflows/        # 确定性基线与 LangGraph 多 Agent 工作流
docs/                 # 产品规格和架构设计
migrations/           # Alembic 迁移
tests/                # 单元与集成测试
```

## 后续路线

1. 将合成 RAG smoke 集扩充为人工标注的真实问法、难负例和多相关文档；
2. 扩充 Agent 对抗场景并增加可配置模型单价的成本估算与多次运行置信区间；
3. 将本地 HS256 JWT 替换为企业 OIDC/JWKS，并增加 Token 撤销和租户权限；
4. 为 OTLP Trace 增加 Grafana/Jaeger/Langfuse 看板、告警和脱敏策略；
5. 对比确定性基线、LLM 多 Agent 和人工审批版本的效果、延迟和成本。

更完整的边界和验收标准见 [产品规格](docs/product-spec.md) 与 [架构设计](docs/architecture.md)。
