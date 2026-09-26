# 模型服务接入决策 v0.1

状态：DeepSeek 生成适配器已写入本地原型，但尚未调用用户账号或产生 API 费用；百炼和火山引擎仍为接口设计。密钥不写入仓库或聊天记录，部署时由服务器受限配置注入。

## 默认分工

| 能力 | 默认提供方 | 初始模型/配置 | 何时更改 |
| --- | --- | --- | --- |
| 文本生成与流式输出 | DeepSeek | `deepseek-flash`，OpenAI 兼容 Chat Completions；模型 ID 放配置 | 同一冻结评测集证明其他模型在质量、延迟或费用上更合适 |
| 文本向量化 | 阿里云百炼 | `text-embedding-v4`，先用 512 维做小规模资源基线 | 在 512/1024 维的同集 Recall@5 与资源测量后冻结 |
| 候选重排 | 阿里云百炼 | 初始关闭；实验候选 `qwen3-rerank` | 同集对照能改善证据召回/排序，且延迟与费用可接受 |
| 生成模型对照 | 火山方舟 | 在控制台启用的具体 Doubao 模型 ID，由配置传入 | M1 基线完成后做独立对照，不自动切换生产流量 |

依据：DeepSeek [快速调用文档](https://api-docs.deepseek.com/)当前列出 `deepseek-flash` 与 OpenAI 兼容接口；百炼[向量化文档](https://help.aliyun.com/zh/model-studio/embedding)列出 `text-embedding-v4` 的可配置维度及 OpenAI 兼容调用；百炼[文本排序文档](https://help.aliyun.com/zh/model-studio/text-rerank-api)列出 `qwen3-rerank` 的单独接口；火山方舟[兼容接口文档](https://docs.volcengine.com/docs/ark/compatible-with-openai-sdk?lang=zh)列出聊天模型的 OpenAI 兼容方式。模型可用性、账户地域、配额和接口形式在真正接入时核查并锁定。火山方舟向量化接口不应直接假定与其聊天兼容接口相同，需按[官方向量化文档](https://docs.volcengine.com/docs/ark/vectorization?lang=zh&redirect=1)单独适配。

## 统一接口与配置

```text
GenerationProvider.generate(messages, response_schema, request_id) -> GenerationResult
GenerationProvider.stream(messages, request_id) -> event stream
EmbeddingProvider.embed_documents(texts) -> vectors + model_metadata
EmbeddingProvider.embed_query(text) -> vector + model_metadata
RerankProvider.rerank(query, candidates) -> ordered candidates
```

`GenerationResult` 至少记录 `provider`、`model_id`、`prompt_version`、`finish_reason`、token 用量、耗时和解析结果；失败结果记录错误类型，不记录敏感原文。所有模型调用设置超时、有限重试、并发上限和单任务 token 上限。结构化输出先使用提供方支持的格式约束，再经 Pydantic 校验；不把“返回了 JSON 字符串”当作业务字段完全正确。DeepSeek 的 [Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)支持 JSON 输出，但也提示必须明确要求 JSON 并处理截断。

建议的环境变量名（仅名称，**不放真实值**）：

```text
GENERATION_PROVIDER=deepseek
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_BASE_URL=https://api.deepseek.com
EMBEDDING_PROVIDER=bailian
DASHSCOPE_API_KEY=
BAILIAN_WORKSPACE_ID=
BAILIAN_REGION=cn-beijing
BAILIAN_EMBEDDING_MODEL=text-embedding-v4
BAILIAN_EMBEDDING_DIMENSIONS=512
RERANK_ENABLED=false
BAILIAN_RERANK_MODEL=qwen3-rerank
ARK_API_KEY=
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_CHAT_MODEL=
```

百炼的 API key 与 endpoint 受地域和业务空间约束，不能从以上占位符推断用户实际账号配置。火山模型 ID 以账户中已启用的模型为准。配置中只允许服务端选择提供方，普通用户请求不能传入任意 base URL 或模型 ID。

## 向量索引版本与安全

- 索引元数据绑定 `provider`、`model_id`、`dimensions`、文档版本、切分版本和归一化方式。查询向量与索引元数据不一致时拒绝检索并要求重建索引，不能混用不同模型的向量。
- 入库与查询使用同一模型配置。先用公开/自制教材做小样本调用；不将真实简历、学员作答或未授权课程资料发送到外部模型服务。
- 生成、embedding 与 rerank 按任务分开计数，记录每日调用量和估算费用；达到预算上限时返回明确错误或停用可选重排。关闭自动跨服务回退，避免同一用户输入在故障时被悄悄发送到另一家平台。
- 本地开发和 CI 使用确定性 fake provider，不要求在 GitHub Actions 中配置任何真实模型密钥。在线评测显式启用并记录提供方、模型、时间、参数、样本集版本与原始计数。

## M1 接入验收

1. 用非敏感固定样例分别验证 DeepSeek 生成、百炼向量化；检查模型 ID、维度、流式事件、token 用量和超时处理。
2. 同一问答评测集比较 FTS5、512 维 dense、混合检索；之后再比较 1024 维及重排，保留原始样本结果。
3. 火山方舟生成作为独立可切换对照；只有账号模型与配额确认后才启动调用。任何对照都使用相同提示词、资料版本、评测问题和评分口径。
4. 线上最终配置及实际使用模型在 README 的“部署版本”中公开说明，不把仅实验过的模型写成线上能力。
