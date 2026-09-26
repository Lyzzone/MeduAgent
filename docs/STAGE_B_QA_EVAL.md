# 阶段 B：公开课程问答语料与冻结评测 v1

日期：2026-09-26。状态：九篇公开教程的 FTS5 基线与单人标注冻结集已运行；真实模型和向量对照尚未运行。

## 语料快照与来源

从固定的 [freeCodeCamp/chinese 上游提交](https://github.com/freeCodeCamp/chinese/tree/0e1648565ab60cadc70d2bdfbd9fae0b57208383) 增加 HTTP/HTTPS、Docker 容器和 SQL 注入三篇教程。三篇按原字节复制，作者、译者、原文 URL、下载日期和 SHA-256 记录在 [manifest](../corpus/freecodecamp_zh/manifest.json)。整个目录仍按上游 [CC BY-SA 4.0](../corpus/freecodecamp_zh/LICENSE.md) 使用。当前为 9 篇、199 个片段；并非完整 IT 课程，也不代表最新官方产品文档。

冻结集 [holdout_qa_v1.json](../eval/holdout_qa_v1.json) 有 20 条可回答题和 8 条无答案题。它在已有 12 正例、3 负例开发集调参结束后编写，固定语料 manifest SHA-256 为 `78bd4fabd439cfc66b60dc07afeb77c814ba498a738bdb190435685a455c`，每条正例记录可核对的片段 ID 与人工答案要点。标签由同一开发者单人核对，尚无第二标注者复核；“独立”仅指没有参与此前检索规则调参，不能等同外部独立测试。

## 首轮离线基线

命令：

```powershell
.\.venv\Scripts\python.exe -m app.cli ingest
.\.venv\Scripts\python.exe -m eval.holdout --output eval/reports/holdout_v1_fts5.json
.\.venv\Scripts\python.exe -m pytest -q
```

逐题原始结果见 [holdout_v1_fts5.json](../eval/reports/holdout_v1_fts5.json)。环境是本机 Windows、Python 3.14；检索为 SQLite FTS5 字面词匹配，`top_k=5`；回答是本地原文摘录，外部模型调用数为 0。

| 指标 | 原始计数 | 含义 |
| --- | --- | --- |
| Recall@5 | 14/20 | 前 5 个片段至少命中一个标注证据 |
| 引用命中标注证据 | 12/20 | 当前摘录实际引用了标注证据 |
| 非空且合法的引用 ID | 14/20 | 引用属于当次检索的片段；未检索到时无引用 |
| 无答案拒答 | 8/8 | 这 8 个样例返回资料不足且无引用 |

28 次检索的本机中位延迟 3.35 ms、p95 6.08 ms，仅用于同一机器本地参考；没有并发压测或线上延迟。费用为 0 次外部模型调用，不能据此估算真实生成费用。旧开发集扩充语料后仍为 12/12 Recall@5、3/3 明显范围外拒答，见 [开发集报告](../eval/reports/dev_qa_v6_fts5.json)；它仍不是独立结果。

## 失败分析与下一步对照

- 6 条未召回证据：`h02,h04,h05,h07,h11,h16`。其中多条使用不含标题词的改写问法；现有字面匹配的词项重合阈值会直接返回空列表。
- 2 条检索命中但摘录没引用金标准：`h01` 在第 3 位、`h18` 在第 4 位，而当前摘录只取前 2 条。把“检索命中”和“最终引用命中”分开报告能看出这个差距。
- 8 条无答案题涵盖课程内未覆盖、版本/时效和跨领域；全部拒答只说明这一小组样例，不证明真实学员提问都能安全拒答。
- 原有 Python JSON API 教程含较长网页 HTML 代码样式噪声，可能降低切分与命中质量；本轮保留原文及哈希，将清洗策略放到后续开发集验证。

固定当前报告作为 FTS5 对照。后续若增加向量召回、重排或查询改写，先在**另建的开发样本**上定方案，再在同一语料、同一冻结集和 `top_k=5` 下对照原始命中数、引用命中数、延迟和费用；不能按本报告失败题直接调阈值再宣称独立提升。

## 真实模型验证边界

[DeepSeek 官方 JSON 输出说明](https://api-docs.deepseek.com/guides/json_mode/)要求在提示中明确 JSON、提供格式示例并合理设置最大输出长度；[Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)提供 token usage 字段。[百炼向量接口](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api/)支持 `text-embedding-v4` 的可选维度及每批输入限制。当前机器未配置 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`，本轮没有真实 API 调用，也没有模型答案正确率、token/费用或向量混合检索成绩。启用时仅允许公开语料进入外部服务；私有 PDF 和求职个人资料继续保持本地。

求职文档的具体放置位置及现有功能支持见 [求职资料放置说明](CAREER_DATA_PLACEMENT.md)。
## 受控的真实生成探针（待本机配置密钥后运行）

`app/providers/generation.py` 现在记录模型 ID、提示词版本、API 返回的 token 用量和请求耗时，并由问答结果透传；`eval/live_qa.py` 仅接受公开索引、与冻结标签匹配的语料哈希和 1–10 个不重复的题号。示例（仅在本机环境变量 `DEEPSEEK_API_KEY` 已配置时执行）：

```powershell
.\.venv\Scripts\python.exe -m eval.live_qa --ids h01 h02 n01 --output data/live_qa_probe.json
```

输出默认示例位于被 Git 忽略的 `data/`；检查 `answer`、`gold_chunk_ids` 和 `answer_points_for_manual_review` 后，再人工判定答案是否正确及每句话是否受证据支持。脚本只验证引用 ID 的结构合法性，不能自动验证语义忠实度。选定的少量题仅是接口探针，不能当全量准确率。token 用量不直接等于费用；本项目没有固定价格表，费用需按调用时的官方计费规则另算。真实调用会将**公开课程片段及问题**发送到 DeepSeek，绝不能传入个人求职资料或私有 PDF。当前未配置密钥，尚无真实探针报告。
## 跨平台语料快照修复记录

首次提交在 Windows 上生成冻结标签时，`manifest.json` 工作区使用 CRLF，而 GitHub Ubuntu 检出为 LF；内容相同但原始字节 SHA-256 不同，导致 [首次阶段 B CI 运行](https://github.com/Lyzzone/MeduAgent/actions/runs/36218146630) 的测试因快照校验失败。现用 `.gitattributes` 将语料清单、冻结标签和报告固定为 LF，并将标签中的清单哈希更新为 Git 实际字节的 `ff6c1fbe733490147bfc901a3abe22600fa364d833cc66630ce07a8466a7ed81`。题目、金标准片段与检索逻辑未改；重建后四个原始计数仍为 14/20、12/20、14/20、8/8。更新后的 Windows 与 Ubuntu WSL 项目测试均为 22/22；仍需 GitHub Actions 复核。
