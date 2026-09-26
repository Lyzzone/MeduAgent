# MEduAgent：面向 IT 教培的可评测 AI 助手

> 状态：四入口本地演示（2026-09-26）。课程问答可运行 FTS5 检索与 LangGraph 问答图；简历、批改、面试提供可交互的规则基线。真实模型调用、独立测试和上线仍待完成。

MEduAgent 计划提供课程资料问答、简历诊断、试卷批改和模拟面试四条业务流程。项目目标是做出能本地复现、能解释路由和检索决策、能展示人工审核与评测结果的 AI 应用工程项目。代码阅读顺序和关键边界见 [代码审查入口](docs/CODE_REVIEW_GUIDE.md)。

完整范围、架构、迭代顺序、接口与评测标准见 [项目方案](docs/PROJECT_PLAN.md)。面向求职演示的优先级与验收标准见 [面试展示版改造路线](docs/INTERVIEW_SHOWCASE_ROADMAP.md)。模型接入见 [模型服务决策](docs/MODEL_PROVIDER_PLAN.md)。最终交付包括 GitHub 仓库及云服务器上的 `agent` 子域名站点；部署链路和上线验收见 [部署方案](docs/DEPLOYMENT_PLAN.md)。

## 当前进度

- [x] 形成项目方案及框架选型依据
- [x] 明确轻量部署路线与模型服务分工，提供无密钥配置模板
- [x] 下载并核验首批开放许可的中文 IT 教程测试语料
- [x] 实现本地检索、带原文出处的预览、无结果拒答、API/SSE 和小型开发集评测
- [x] 增加本地私有 PDF 知识库：逐页索引、页码引用、哈希校验、与公开 API 隔离
- [x] 新增四业务首页路由及独立工作台；简历、批改、面试接入本地规则基线
- [x] 加入公开虚构演示数据、离线四业务案例脚本与 Ubuntu CI 配置（云端 CI 待首次上传验证）
- [ ] 完成真实生成模型验证、独立测试集、流式 token 与权限控制
- [ ] 扩展简历、批改、面试流程
- [ ] 完成部署、演示与公开 GitHub 仓库

图片中出现的准确率和召回率仅作为参考示例，不是本项目的结果。任何公开简历中的技术和指标都以仓库代码、提交记录、评测数据及可复现报告为准。

面试演示可按 [5 分钟公开演示指南](docs/DEMO_GUIDE.md) 操作；`python -m demo.run_demo` 不需密钥、私有 PDF 或已建立的本地索引。根目录自写代码的许可证尚未选择，公开教程仍按其独立许可证使用。

首批测试资料见 [freeCodeCamp 中文教程语料](corpus/freecodecamp_zh/README.md)，保留上游署名、CC BY-SA 4.0 许可证、提交号与文件哈希。现有问答开发集曾参与调参，独立测试集尚待冻结。

目标地址已确认为 `agent.cuitopendoor.top`，A 记录已解析。由于现有 Ubuntu 服务器仅约 1.6 GiB 内存，线上选用 SQLite FTS5 + 轻量向量索引，FastAPI 由 systemd 托管并复用现有 Nginx；模型走外部 API。详见部署方案。

## 本地运行课程问答原型

在项目根目录的 PowerShell 中执行（已在 Windows Python 3.14 验证）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m app.cli ingest
.\.venv\Scripts\python.exe -m app.cli ask "Git 和 GitHub 有什么区别？"
.\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8765
```

然后访问 `http://127.0.0.1:8765/`，首页选择课程问答、简历审查、试卷批改或模拟面试。课程问答默认 `QA_GENERATION_MODE=extractive`，只展示检索到的原文片段。其他三个页面使用独立规则接口，不调用大模型、不保存输入；它们的分析结果是功能基线，不能视作完整的智能诊断、正式成绩或面试评价。四入口实现和测试范围见 [网页工作台说明](docs/WEB_WORKBENCH_MVP.md)。Linux 启动时把上述解释器路径改为 `.venv/bin/python`。`data/`、`.venv/` 和个人学习笔记均由 `.gitignore` 排除。

运行检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m eval.retrieval --output eval/reports/local_check.json
```

开发集只有 12 个正例和 3 个范围外问题，曾用于调整检索规则；最新 `Recall@5=12/12` 只是开发集内的结果，不能作为独立测试成绩。原始逐题结果和早期失败版本保存在 `eval/reports/`。实现细节、运行限制与后续工作见 [M1 本地原型说明](docs/M1_LOCAL_MVP.md)。

面向更真实场景的数据覆盖、标注和冻结测试集要求见 [数据与评测扩充方案](docs/DATASET_EXPANSION_PLAN.md)。当前规模只支持开发期验证。

## 本地私有 PDF 知识库

只对自己有权使用的 PDF 执行以下命令。导入命令会复制文件到 `data/private_corpus/pdfs/`，生成包含 SHA-256 的私有清单；索引保存在 `data/private_pdf_index.sqlite3`。整个 `data/` 目录由 Git 忽略。

```powershell
.\.venv\Scripts\python.exe -m app.cli import-private-pdf "D:\资料\示例一.pdf" "D:\资料\示例二.pdf"
.\.venv\Scripts\python.exe -m app.cli ingest-private-pdf
.\.venv\Scripts\python.exe -m app.cli ask-private "Transformer 的注意力机制是什么？"
```

`ask-private` 固定采用本地摘录预览，不向 DeepSeek、百炼、火山引擎或其他外部模型发送 PDF 内容。私有索引按页切块，回答引用保留文档标题和 PDF 页码；纯图片页暂不支持 OCR。公开 FastAPI 服务只接受公开语料索引，私有索引即使被设置为 `QA_INDEX_PATH` 也会返回 503。当前检索是 SQLite FTS5 关键词基线；两份 PDF 的准确率、召回率及图表理解能力尚未形成独立评测结果。

重新导入会以本次提供的文件列表替换私有清单；已有文件仍保留在忽略目录中。运行前请核对来源与使用权限，不要将 `data/`、数据库、原文摘录或本地学习笔记强制加入公开仓库。实现和边界见 [私有 PDF 知识库说明](docs/PRIVATE_PDF_KB.md)。
