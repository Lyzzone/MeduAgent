# M1 课程问答本地原型

日期：2026-09-25。状态：**本地检索预览可运行，完整 M1 尚未验收**。

## 已实现的路径

1. `app.cli ingest` 读取 pinned `manifest.json`，校验六篇 Markdown 及许可证 SHA-256。
2. 按 Markdown 标题和段落切成 156 个片段，保存文章来源、作者、译者、章节和稳定片段 ID。
3. SQLite FTS5 索引英文技术词、中文双字词、章节标题及文章标题；查询时用参数化 `MATCH`、BM25 和明确的标题/覆盖率规则排序。
4. LangGraph 状态图运行 `retrieve → answer/refuse → validate`。默认 `ExtractiveGenerator` 只回显最多两个原文片段，状态为 `retrieval_preview`；无检索结果或非法引用时返回 `insufficient_evidence`。
5. FastAPI 提供 `/health/live`、`/health/ready`、`POST /v1/qa` 和 `POST /v1/qa/events`。SSE 当前只有 `status`、`done`、`error` 事件，没有 token 级流式生成。
6. `/` 提供本地演示页。页面用 POST SSE 查资料、显示出处和作者/译者，文本通过 DOM `textContent` 呈现。

代码位置：`app/retrieval/`、`app/workflows/qa.py`、`app/providers/generation.py`、`app/api.py`、`web/`。运行命令见根目录 README。

## 生成模型状态

提供了 DeepSeek Chat Completions 适配器，只有设置 `QA_GENERATION_MODE=deepseek` 和服务端 `DEEPSEEK_API_KEY` 才会调用。已用 `httpx.MockTransport` 验证请求格式、响应解析与引用 ID 映射，但**没有使用用户账号做在线请求**；真实模型兼容性、费用、超时及答案忠实度未实测。ID 合法本身不能证明答案的每句话受证据支持。真实调用前仍需费用上限、模型版本记录和人工答案评审。

## 开发集与原始结果

`eval/dev_qa.json` 是手工编写的 12 个带文档/章节标签的问题和 3 个范围外问题。脚本在索引中解析章节为相关片段 ID；`Recall@5` 的分子是前五命中任一标注片段的问题数，分母是 12。范围外拒答率统计没有返回片段的问题数，分母是 3。

| 阶段 | Recall@5 | 范围外无检索 | 说明 |
| --- | --- | --- | --- |
| v1 | 10/12 | 3/3 | Git 定义、Python 分页漏检 |
| v2 | 11/12 | 3/3 | 加入文章标题后，Git 定义仍漏检；HTTP 回归失败 |
| v3 | 11/12 | 3/3 | 调整标题权重与问句清理，Git 定义仍漏检 |
| v4/v5 | 12/12 | 3/3 | 定义/比较类问题优先短定义章节；v5 保持结果 |

上述版本均基于同一**开发集**反复调整，绝不能表述为独立测试上的性能提升。每个报告保留逐题 gold chunk ID、召回 ID 和首次命中排名。没有 dense、混合或重排实验，也没有与其他模型的质量比较。

## 已验证与限制

- 本机 Python 3.14：11 个自动化测试通过，包括语料篡改拒绝、技术词检索、无证据拒答、非法引用拒绝、API/SSE、缺失索引 503 及 DeepSeek 离线契约。
- 本地浏览器实测：页面加载，示例问题可填入；SSE 能显示预览和原文出处。
- 当前无用户认证、租户隔离、文档上传和速率限制，**不能直接公开部署**。
- 目前只有 FTS5；轻量 dense 索引、百炼 embedding、混合检索和重排仍是方案。
- 只校验引用 ID 是否来自候选片段，没有逐句证据支持判定；抽取模式只是检索预览，不是成熟问答。
- 当前小样本标签由开发者建立，后续要补标注说明、冻结独立测试集和更多困难/反例，再报告指标。

下一阶段先完成独立测试样例与生成模型契约测试，然后接入实际服务并测答案证据支持率。需要公开部署前，再补认证、配额、日志脱敏、备份与负载验收。
