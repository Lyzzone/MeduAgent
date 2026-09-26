# 5 分钟公开演示

本指南只使用仓库中的公开教程和虚构输入；不需要模型 API 密钥、私有 PDF 或真实个人资料。当前课程问答以 FTS5 检索和本地摘录展示证据；试卷批改、简历审查和模拟面试是规则基线。

## 从全新克隆启动

建议 Python 3.13；CI 在 Ubuntu 上执行相同的依赖安装、测试和演示脚本。以下命令在项目根目录运行。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m demo.run_demo
.\.venv\Scripts\python.exe -m app.cli ingest
.\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8765
```

Ubuntu：

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m demo.run_demo
.venv/bin/python -m app.cli ingest
.venv/bin/python -m uvicorn app.api:app --host 127.0.0.1 --port 8765
```

浏览器打开 `http://127.0.0.1:8765/`。若只想验证接口与案例，运行 `python -m demo.run_demo` 即可；它在临时目录创建公开索引，退出后删除，不调用外部模型。

## 按首页顺序展示

所有可复制的请求输入与预期状态保存在 [公开演示案例](../demo/public_cases.json)。输入均为虚构。

1. **课程资料问答**：输入“Git 和 GitHub 有什么区别？”。展示引用片段、原文来源和 `retrieval_preview`，说明这是可核查的本地摘录。
2. **试卷批改**：客观题使用 GET / “ get ”，展示规范化精确匹配；再用“解释为何 RAG 答案需要引用来源”主观题，展示 `teacher_review_required` 和空分数。
3. **简历审查**：粘贴案例中的虚构简历与岗位描述，展示 Python、FastAPI、SQL 命中和 Docker 缺口。解释“缺失”只代表简历文本没出现该关键词。
4. **模拟面试**：选择 AI 方向先领取问题，再输入案例回答，展示关键词提示与追问。该接口尚不保存多轮会话。

## 代码与证据

- 网页入口：[首页](../web/index.html)；接口入口：[FastAPI 路由](../app/api.py)。
- 问答工作流：[LangGraph 图](../app/workflows/qa.py)；业务规则：[批改](../app/workflows/grading.py)、[简历](../app/workflows/resume.py)、[面试](../app/workflows/interview.py)。
- 公开语料的上游署名、许可与哈希：[语料清单](../corpus/freecodecamp_zh/README.md)。根目录代码许可证尚待项目所有者选择，语料许可证不随代码许可证改变。
- 自动检查：[GitHub Actions](../.github/workflows/ci.yml)。本地通过不代表云端 CI 已通过；上传后须查看实际 Actions 运行记录。

当前限制与下一阶段技术目标见 [面试展示版路线](INTERVIEW_SHOWCASE_ROADMAP.md)。简历中应准确表述为“实现四入口本地原型，课程问答有可引用的检索链路，其余三条为规则基线”。
