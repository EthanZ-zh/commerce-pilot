# CommercePilot MVP 产品规格

## 1. 产品目标

CommercePilot 面向电商运营人员，将“发现库存积压商品—分析经营数据—制定促销方案—合规检查—创建活动草稿”串成一条可追溯、可审批的工作流。

第一阶段实现确定性基线；第二阶段增加 LangGraph Supervisor-Worker；第三阶段增加 PostgreSQL Checkpointer 和可恢复的整批人工审批；第四阶段增加政策混合 RAG；第五阶段接入真实 Qwen Supervisor 与 Strategy Planner。所有执行路径继续复用相同工具契约。

## 2. 核心用户故事

运营人员输入：

> 分析华南地区耳机类目最近 30 天的销量和库存，筛选周转天数超过 60 天的商品，在毛利率不低于 15%、折扣不超过 20% 的条件下制定促销方案，并创建待审批活动草稿。

系统必须：

1. 从数据库查询销量与库存，不让生成模型计算业务数字；
2. 只选择同时满足类目、地区和库存条件的商品；
3. 用确定性公式模拟折扣和毛利；
4. 检索有效的平台政策并返回证据；
5. 检查禁用词、毛利和折扣约束；
6. 只创建 `DRAFT` 活动，不能绕过人工审批直接上线；
7. 记录节点耗时、输入摘要、输出摘要和错误。
8. 在 React 单页控制台展示 Agent 图、RAG 证据、模型指标和审批闭环，不要求演示者手工复制 JWT 或 `thread_id`。

## 3. 输入

- `category`：商品类目；
- `region`：经营地区；
- `date_from/date_to`：分析时间范围；
- `turnover_days_threshold`：积压阈值；
- `max_discount_rate`：最大折扣率；
- `min_margin_rate`：最低毛利率；
- `budget`：活动预算；
- `goal`：经营目标描述。

## 4. 输出

- 入选商品及销售、库存证据；
- 折扣模拟结果；
- 适用政策及来源；
- 营销策略和文案；
- 合规检查结果；
- 活动草稿 ID；
- 完整执行轨迹。

## 5. 成功标准

- 所有业务数字可追溯到 SQL 查询或确定性计算；
- 不满足约束的商品不会进入活动草稿；
- 同一幂等键不会创建重复活动；
- 合规失败时不创建草稿；
- 相同数据和输入得到相同结果；
- 基线工作流具备自动化测试。

## 6. 当前项目仍不做

- 大模型驱动的动态路由；
- 真实电商平台写操作；
- Kafka、Kubernetes、模型微调；
- 在线支付、退款或订单修改；
- 未经人工确认的活动发布。

混合政策 RAG 已纳入当前范围；LLM 驱动的动态路由仍留到下一阶段。

## 7. 第二阶段验收标准

- Supervisor 同时派发销量、库存定价和政策检索三个 Worker；
- 策略节点必须等待三个 Worker 全部完成后再汇总；
- 合规复核与活动执行是两个独立节点；
- 合规失败或无候选商品时不创建活动草稿；
- 重复请求不重复创建草稿；
- 每个 Agent 节点都有可查询的审计轨迹；
- 无外部模型密钥时也能在本地和 CI 完整运行。

## 8. 第三阶段验收标准

- 合规通过后在活动创建前中断，返回完整整批审批摘要；
- 中断时数据库中不存在该任务对应的活动草稿；
- 服务停止并重新启动后，可以根据 `thread_id` 恢复执行；
- 批准后只创建 `DRAFT`，拒绝后直接结束且不创建活动；
- 拒绝必须填写理由，批准和拒绝都记录操作人；
- 同一任务只能审批一次，重复或并发审批返回冲突；
- 待审批任务和任务详情可通过业务 API 查询；
- Checkpoint 反序列化采用显式类型白名单。

## 9. 第四阶段混合 RAG 验收标准

- 政策正文被稳定分块，并记录内容哈希、模型和 256 维向量；
- PostgreSQL 使用 pgvector HNSW 执行向量 Top-K；
- BM25 与向量召回通过 RRF 融合，融合候选再经过 Reranker；
- 检索结果包含政策来源、版本、chunk ID 和各阶段分数；
- 无 API Key 时确定性 Provider 可运行完整工作流和测试；
- 切换 Embedding 模型后自动重建不兼容索引；
- 外部 Provider 的请求格式由自动化测试覆盖。

## 10. 第五阶段真实 LLM Agent 验收标准

- Supervisor 可调用 `qwen3.7-flash`，Strategy Planner 可调用 `qwen3.7-plus` 严格结构化输出；
- 模型不能修改 LangGraph 拓扑、候选商品、折扣、毛利或审批状态；
- HTTP、JSON Schema 或业务语义失败时自动降级为确定性实现；
- 降级轨迹仍保留失败模型调用的 Token、延迟和错误；
- Strategy 文案经过独立确定性合规复核；
- 禁止未实现能力、最终解释权、反向周转指标和无证据热销词；
- pytest 强制离线 Provider，不因开发机 `.env` 产生付费调用；
- 工作流版本参与任务指纹，Prompt 或安全策略升级不复用旧草稿。

## 11. RAG 评测与模型路由增强验收标准

- 政策目录至少覆盖价格、文案、审批、预算、库存语义、区域、审计和模型边界；
- 政策同步按 code 幂等新增或更新，不删除用户自定义政策和其他业务数据；
- 检索评测计算 Recall@K、MRR 和 nDCG@K，并输出逐条排名用于定位回归；
- pytest 的评测只使用离线 Provider，真实 Embedding/Rerank 评测必须显式触发；
- Supervisor 与 Strategy 可配置不同模型，调用轨迹记录实际模型；
- Strategy 只接收生成文案所需的压缩证据，不接收重复的完整工具对象；
- 合成评测结果只作为 smoke 基线，不冒充真实流量或生产质量结论。

## 12. Agent 端到端评测验收标准

- 场景集至少包含正常任务、不同类目区域、无候选和不可满足约束；
- 评测执行完整 Agent 图，但不得创建活动草稿或写入业务 Agent 审计；
- LLM 和 RAG Provider 可显式注入，离线评测不读取开发机的付费 Provider；
- 评分器独立复核商品数量、类目、区域、库存、折扣、毛利、证据和高风险词；
- 输出任务成功率、约束违规场景比例、fallback 率、Token 和模型延迟；
- fallback 报告必须保留节点、模型和错误原因，不能只报告聚合比例；
- 真实模型评测支持限制场景数量，并明确单次小样本不代表稳定性。

## 13. JWT 与 RBAC 验收标准

- 工作流接口缺少、过期、签名错误或 audience 错误的 Token 返回 401；
- 已认证但角色不足时返回 403，管理员可以访问全部受保护接口；
- analyst 只能运行和发起任务，不能查看待审批列表或执行审批；
- approver 可以查询并决策审批，viewer 只能读取任务详情；
- 审批请求体不能传入或覆盖 operator，持久化操作人必须等于 JWT `sub`；
- JWT 必须校验签名、过期时间、issuer、audience、subject 和角色；
- 生产环境拒绝开发默认 Secret、短 Secret 和本地 Token 签发脚本；
- 当前开发签发器不是生产身份系统，生产化需接入 OIDC/JWKS 和 Token 撤销策略。

## 14. 可观测性与 CI 验收标准

- FastAPI 请求、Agent 工作流、LLM 调用和 RAG 检索生成可关联的 OpenTelemetry spans；
- spans 记录 task ID、模型、Token、attempts、fallback、检索结果数和策略状态，不记录密钥与完整 Prompt；
- 连接错误、超时、429 和 5xx 可执行有限重试，Schema/语义错误及其他 4xx 不重试；
- 模型轨迹与评测报告区分 retry 和 fallback，失败调用保留累计延迟与错误；
- 遥测默认关闭，启用时必须配置 OTLP 或 Console exporter，健康检查不产生 Trace；
- CI 强制离线 Provider，执行覆盖率门禁、Ruff、mypy、依赖和 pgvector PostgreSQL 迁移检查；
- Pull Request 在任一质量门禁失败时不得视为可交付。

## 15. React 演示控制台验收标准

- React 只通过 FastAPI 访问业务能力，不直连 PostgreSQL 或读取模型密钥；
- 页面提供预设业务场景、参数约束、确定性基线与多 Agent 执行入口；
- 展示 Supervisor-Worker 图、策略、定价结果、RAG 来源与分数、合规结论、Token、延迟、retry 和 fallback；
- 人工审批页面隐藏 JWT 和 `thread_id` 的技术操作，同时仍通过 analyst/approver API 权限边界执行；
- 演示会话接口只能在 development 环境使用，生产环境必须不可用；
- Docker Compose demo profile 可以启动 API、前端、PostgreSQL 与 Redis；
- 前端 Vitest、TypeScript 检查和 Vite 生产构建纳入 GitHub Actions；
- Playwright 在真实 Chromium 中完成“运行 Agent、查看 RAG 证据、提交审批、批准并生成 DRAFT”的端到端验证；
- E2E 使用独立数据库与端口，测试数据和活动草稿不得污染开发环境；
- SSE 进度必须来自 LangGraph 真实 `tasks/values` 事件；页面展示节点等待、运行、完成和失败状态，并在流结束时使用后端最终结构化结果；
- SSE 接口必须保持 analyst JWT/RBAC 边界，Token 不得放入 URL，原同步接口保持向后兼容。
