# 代码审查入口

当前项目是四入口本地演示：课程问答已有 LangGraph 图；简历、批改、面试是独立的确定性规则基线。审查代码时可按下列顺序阅读，避免把页面入口误认为完整 Agent 能力。

| 先读 | 文件 | 关注点 |
| --- | --- | --- |
| 1 | `app/api.py` | 页面/API 路由、Pydantic 请求入口、公开索引检查和 SSE 错误路径 |
| 2 | `app/workflows/qa.py` | LangGraph 检索→回答/拒答→引用校验；私有索引只能用本地摘录生成器 |
| 3 | `app/workflows/resume.py` | 简历关键词与结构检查；不生成经历 |
| 4 | `app/workflows/grading.py` | 客观题严格匹配，主观题必须教师复核 |
| 5 | `app/workflows/interview.py` | 固定题库和关键词提示；不评估真实能力 |
| 6 | `app/retrieval/store.py`、`private_pdf.py`、`markdown.py` | 公开/私有索引分离、哈希校验、切块与页码引用 |
| 7 | `app/providers/generation.py` | 本地摘录和可选 DeepSeek 适配器；私有 PDF 不送外部模型 |
| 8 | `web/index.html`、`qa.html`、`workbench.html`、`assets/*.js` | 四入口导航、各业务表单与结果展示 |

## 几条不能破坏的边界

- `data/` 里的原 PDF 和派生索引保持本地；无认证 HTTP 服务仅接受公开语料索引。
- 模型返回的引用 ID 必须出现在检索证据里；不接受编造的引用。
- 主观题不给自动分数；简历建议不得伪造经历；面试关键词提示不得表达为能力评分。
- UI 中用户或 API 返回的文本用 `textContent` 显示，不能直接当 HTML 插入。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check web\assets\app.js
node --check web\assets\workbench.js
```

目前没有完整认证、会话持久化、真实模型端到端验证和独立测试集成绩。公开部署这些新业务入口前需补隐私和访问控制。技术学习和面试复盘写在 Git 忽略的 `.learning-notes/` 下。
