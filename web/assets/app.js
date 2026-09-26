const form = document.getElementById("question-form");
const input = document.getElementById("question");
const submit = document.getElementById("submit-button");
const status = document.getElementById("status");
const panel = document.getElementById("answer-panel");
const answer = document.getElementById("answer");
const answerType = document.getElementById("answer-type");
const sourceCount = document.getElementById("source-count");
const sources = document.getElementById("sources");

function setStatus(message, isError = false) {
  status.textContent = message;
  status.classList.toggle("error", isError);
}

function renderResult(result) {
  panel.hidden = false;
  answer.textContent = result.answer;
  answerType.textContent = result.status === "retrieval_preview" ? "检索预览 · 原文片段" :
    result.status === "answered" ? "资料回答" : "资料不足";
  sourceCount.textContent = `${result.citations.length} 条原文依据`;
  sources.replaceChildren();
  for (const [index, citation] of result.citations.entries()) {
    const card = document.createElement("article");
    card.className = "source-card";
    const label = document.createElement("div");
    label.className = "source-label";
    label.textContent = `SOURCE ${String(index + 1).padStart(2, "0")} · ${citation.document_id}`;
    const title = document.createElement("h3");
    title.textContent = citation.heading;
    const quote = document.createElement("p");
    quote.textContent = citation.quote;
    const meta = document.createElement("div");
    meta.className = "source-meta";
    const credit = document.createElement("span");
    credit.textContent = citation.page ? `${citation.title} · 第 ${citation.page} 页` :
      `作者 ${citation.author} · 译者 ${citation.translator}`;
    meta.append(credit);
    if (citation.source_url?.startsWith("https://")) {
      const link = document.createElement("a");
      link.href = citation.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "查看原文 ↗";
      meta.append(link);
    }
    card.append(label, title, quote, meta);
    sources.append(card);
  }
  setStatus(result.status === "insufficient_evidence" ? "没有找到足够的课程依据。" : "已找到对应的课程片段。");
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function readEvents(response) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败（HTTP ${response.status}）`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let doneEvent = false;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop();
    for (const block of blocks) {
      const event = block.match(/^event: (.+)$/m)?.[1];
      const data = block.match(/^data: (.+)$/m)?.[1];
      if (event === "status") setStatus("正在查找课程片段…");
      if (event === "error") throw new Error(data ? JSON.parse(data).message : "问答处理失败，请重试。");
      if (event === "done" && data) {
        renderResult(JSON.parse(data));
        doneEvent = true;
      }
    }
  }
  if (!doneEvent) throw new Error("连接结束，但没有收到结果。请重试。");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  submit.disabled = true;
  panel.hidden = true;
  sources.replaceChildren();
  setStatus("正在提交问题…");
  try {
    const response = await fetch("/v1/qa/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: input.value.trim() }),
    });
    await readEvents(response);
  } catch (error) {
    setStatus(error.message || "请求失败，请稍后重试。", true);
  } finally {
    submit.disabled = false;
  }
});

document.querySelectorAll("[data-question]").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.dataset.question;
    input.focus();
  });
});
