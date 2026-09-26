const agent = location.pathname.split("/").pop();
const config = {
  resume: {
    label: "简历审查 / RESUME REVIEW", title: "让经历更有依据。",
    description: "粘贴简历和目标岗位要求，先做技能关键词与结构检查。页面不会替你编造经历。",
    endpoint: "/v1/resume/review", button: "检查简历",
    fields: `
      <label for="resume_text">简历内容</label>
      <textarea id="resume_text" name="resume_text" minlength="20" maxlength="12000" required placeholder="粘贴一份自制或已获授权的简历文本"></textarea>
      <label for="job_description">目标岗位描述</label>
      <textarea id="job_description" name="job_description" minlength="10" maxlength="5000" required placeholder="例如：熟悉 Python、SQL 和 Docker，有项目交付经验"></textarea>`,
    example: {resume_text: "项目经历：使用 Python 和 SQL 开发课程管理演示系统，负责数据查询和接口实现。", job_description: "AI 应用开发工程师：熟悉 Python、SQL、Docker 和 FastAPI，能独立完成项目交付。"},
    render: result => [
      ["已在简历中识别", result.matched_skills.length ? result.matched_skills.join("、") : "当前规则未识别到岗位技能关键词。"],
      ["岗位提及但简历未写", result.missing_skills.length ? result.missing_skills.join("、") : "无"],
      ["结构检查", result.checks.length ? result.checks.join("\n") : "未发现当前规则覆盖的结构缺口。"],
      ["修改建议", result.suggestions.length ? result.suggestions.join("\n") : "请人工核对岗位要求与经历事实。"],
    ],
  },
  grading: {
    label: "试卷批改 / GRADING", title: "先给依据，再谈分数。",
    description: "客观题只做严格规则匹配；主观题不自动给分，等待教师依据评分标准复核。",
    endpoint: "/v1/grading/check", button: "检查作答",
    fields: `
      <label for="question_type">题目类型</label>
      <select id="question_type" name="question_type"><option value="objective">客观题</option><option value="subjective">主观题</option></select>
      <label for="question">题目</label><textarea id="question" name="question" minlength="3" maxlength="2000" required placeholder="请输入题目"></textarea>
      <label for="reference_answer">参考答案</label><textarea id="reference_answer" name="reference_answer" maxlength="3000" required placeholder="请输入参考答案"></textarea>
      <label for="student_answer">学员作答</label><textarea id="student_answer" name="student_answer" maxlength="3000" required placeholder="请输入学员答案"></textarea>
      <label for="max_points">本题满分</label><input id="max_points" name="max_points" type="number" min="1" max="100" value="10" required />`,
    example: {question_type: "objective", question: "HTTP 中用于读取资源的常见请求方法是什么？", reference_answer: "GET", student_answer: "GET", max_points: "10"},
    render: result => [
      ["评分状态", result.review_required ? "需要教师复核" : "规则匹配完成"],
      ["分数预览", result.suggested_points === null ? `暂不自动给分 / 满分 ${result.max_points}` : `${result.suggested_points} / ${result.max_points}`],
      ["规则依据", result.reason],
    ],
  },
  interview: {
    label: "模拟面试 / INTERVIEW", title: "把回答说具体。",
    description: "选择方向，先获取一道练习题；提交回答后查看关键词覆盖提示与追问。",
    endpoint: "/v1/interview/turn", button: "获取题目 / 查看提示",
    fields: `
      <label for="track">练习方向</label>
      <select id="track" name="track"><option value="ai">AI 应用开发</option><option value="backend">后端开发</option><option value="data">数据工程</option></select>
      <label for="answer">你的回答（可先留空获取题目）</label>
      <textarea id="answer" name="answer" maxlength="4000" placeholder="先获取题目，再在这里输入你的回答"></textarea>`,
    example: {track: "ai", answer: "RAG 流程先检索资料，再根据证据回答，并校验引用是否指向检索到的片段。"},
    render: result => [
      ["练习题", result.question],
      ["练习提示", result.feedback],
      ...(result.follow_up ? [["继续追问", result.follow_up]] : []),
    ],
  },
}[agent];

function readPayload(form) {
  const payload = Object.fromEntries(new FormData(form));
  if (agent === "grading") payload.max_points = Number(payload.max_points);
  return payload;
}

function renderSections(container, sections) {
  container.replaceChildren();
  for (const [heading, value] of sections) {
    const section = document.createElement("section");
    section.className = "result-block";
    const title = document.createElement("h2");
    title.textContent = heading;
    const text = document.createElement("p");
    // API text is data, never markup from a resume or student answer.
    text.textContent = value;
    section.append(title, text);
    container.append(section);
  }
}

if (!config) {
  location.replace("/");
} else {
  document.title = `MEduAgent · ${config.label.split(" /")[0]}`;
  document.getElementById("workbench-kind").textContent = config.label;
  document.getElementById("workbench-title").textContent = config.title;
  document.getElementById("workbench-description").textContent = config.description;
  const form = document.getElementById("agent-form");
  // fields and button are fixed application copy, not user-supplied HTML.
  form.innerHTML = `${config.fields}<div class="form-actions"><button type="button" id="fill-example" class="example-action">填入示例</button><button type="submit" class="primary-action">${config.button} ↗</button></div>`;
  document.getElementById("fill-example").addEventListener("click", () => {
    for (const [name, value] of Object.entries(config.example)) form.elements[name].value = value;
    form.elements[Object.keys(config.example)[0]].focus();
  });
  const status = document.getElementById("agent-status");
  const output = document.getElementById("agent-result");
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    output.hidden = true;
    status.textContent = "正在按当前规则检查…";
    status.classList.remove("error");
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const response = await fetch(config.endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(readPayload(form)),
      });
      const body = await response.json();
      if (!response.ok) {
        const message = response.status === 422
          ? "输入内容不符合长度或格式要求，请检查后重试。"
          : (body.detail || `请求失败（HTTP ${response.status}）`);
        throw new Error(message);
      }
      renderSections(output, config.render(body));
      output.hidden = false;
      status.textContent = "规则检查完成。请结合原始资料人工复核。";
    } catch (error) {
      status.textContent = error.message || "检查失败，请稍后重试。";
      status.classList.add("error");
    } finally {
      button.disabled = false;
    }
  });
}
