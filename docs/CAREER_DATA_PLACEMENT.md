# 求职资料放置与使用边界

项目中的“求职资料”可能是公开教程、虚构演示案例，也可能是本人简历和岗位记录。按是否允许公开、是否含个人信息决定位置；文件扩展名并不能决定权限。

| 资料 | 放置位置 | GitHub | 当前能否被功能使用 |
| --- | --- | --- | --- |
| 本人简历、投递记录、面试笔记、未确认转载许可的岗位描述 | `data/career_private/` | 整个 `data/` 已忽略 | 默认不会自动进入网页或课程索引 |
| 上述资料中的 PDF，且只想在本机做摘录检索 | `data/career_private/pdf_corpus/`，通过 CLI 导入 | 忽略 | `ask-private` 本地摘录可用；与已有课程 PDF 分库 |
| 自制且明显标为虚构的简历、岗位、题目及回答 | `demo/public_cases.json`，将来可拆为 `demo/career/` | 可提交 | 当前演示脚本会调用规则接口 |
| 已核实作者、版本和再分发许可的公开求职教程 | 计划放 `corpus/career_zh/`，附 `manifest.json`、许可与哈希 | 核实后才提交 | 当前索引器只读取 `corpus/freecodecamp_zh/`；新目录不会自动生效 |

**请不要把真实简历或抓取来的招聘网页直接复制到 `corpus/` 或 `demo/`。**公开可访问的招聘网页不自动等于允许原文再分发；若许可不清楚，先按私有资料保存。学习笔记继续放 `.learning-notes/`，它也由 Git 忽略。

## 本机单独检索求职 PDF

在项目根目录运行；把示例路径替换成你的文件。导入命令会复制 PDF 并生成带哈希的清单，因此不要手工把 PDF 丢进 `pdfs/` 后跳过导入。

```powershell
.\.venv\Scripts\python.exe -m app.cli import-private-pdf "E:\资料\示例求职文档.pdf" --corpus data/career_private/pdf_corpus
.\.venv\Scripts\python.exe -m app.cli ingest-private-pdf --corpus data/career_private/pdf_corpus --db data/career_private/pdf_index.sqlite3
.\.venv\Scripts\python.exe -m app.cli ask-private "文档中写了哪些岗位要求？" --db data/career_private/pdf_index.sqlite3
```

`ask-private` 只做本机检索摘录，不把私有 PDF 内容发给 DeepSeek、百炼或火山引擎，也不会通过公开网页 API 访问。导入同一私有语料目录时，新导入清单会替换旧清单；要保留多个 PDF，请一次提供所有文件或使用不同目录。简历审查和模拟面试的正式多轮工作流属于后续阶段，当前不会自动读取这里的文件。

## 公开求职教程以后如何接入

先核实许可、作者、原始 URL、版本和 SHA-256，再为 `corpus/career_zh/` 建独立 manifest。接入时需要扩展索引器或建立单独的职业资料索引与访问路由，并为新来源单独评测；不能只复制文件就声称知识库已经使用了它。
