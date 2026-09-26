import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.providers.generation import DeepSeekGenerator, Draft, ExtractiveGenerator
from app.retrieval.store import build_index, search
from app.workflows.qa import ask, build_qa_graph


CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "freecodecamp_zh"


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    db = tmp_path_factory.mktemp("index") / "course.sqlite3"
    counts = build_index(CORPUS, db)
    assert counts["documents"] == 6
    assert counts["chunks"] > 50
    return db


def test_source_hash_mismatch_is_rejected(tmp_path):
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / manifest["license_file"]).write_bytes((CORPUS / manifest["license_file"]).read_bytes())
    for entry in manifest["files"]:
        (tmp_path / entry["path"]).write_bytes((CORPUS / entry["path"]).read_bytes())
    (tmp_path / manifest["files"][0]["path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_index(tmp_path, tmp_path / "index.sqlite3")


@pytest.mark.parametrize(
    ("question", "expected_document"),
    [
        ("Git 和 GitHub 有什么区别？", "git-and-github-for-beginners"),
        ("HTTP 的 GET 和 POST 有什么区别？", "http-request-methods-explained"),
        ("SQL JOIN 有哪些类型？", "sql-joins-tutorial"),
    ],
)
def test_technical_term_retrieval(index, question, expected_document):
    hits = search(index, question)
    assert hits
    assert hits[0].document_id == expected_document


def test_unknown_question_refuses(index):
    result = ask(build_qa_graph(index, ExtractiveGenerator()), "量子纠缠的定义是什么？")
    assert result.status == "insufficient_evidence"
    assert result.citations == []


def test_answer_has_valid_source_citation(index):
    result = ask(build_qa_graph(index, ExtractiveGenerator()), "Git 和 GitHub 有什么区别？")
    assert result.status == "retrieval_preview"
    assert result.citations[0].document_id == "git-and-github-for-beginners"
    assert result.citations[0].source_url.startswith("https://www.freecodecamp.org/")
    assert result.citations[0].heading == "什么是 Git？"
    assert result.citations[1].heading == "什么是 GitHub？"


def test_unknown_citation_is_rejected(index):
    class BadGenerator:
        def generate(self, question, evidence):
            return Draft("unsupported claim", ["invented-id"], "fake")

    result = ask(build_qa_graph(index, BadGenerator()), "Git 和 GitHub 有什么区别？")
    assert result.status == "insufficient_evidence"
    assert result.answer == "资料不足，无法回答。"


def test_deepseek_adapter_contract_without_network(index, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "test-model")
    observed = {}
    original_client = httpx.Client

    def respond(request):
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["Authorization"]
        body = json.loads(request.content)
        observed["model"] = body["model"]
        evidence = json.loads(body["messages"][1]["content"])["evidence"]
        content = json.dumps({"answer": "Git 是版本控制系统。", "citation_ids": [evidence[0]["citation_id"]]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(respond), **kwargs))
    result = ask(build_qa_graph(index, DeepSeekGenerator()), "Git 是什么？")
    assert observed == {
        "url": "https://api.deepseek.com/chat/completions",
        "authorization": "Bearer test-only-key",
        "model": "test-model",
    }
    assert result.status == "answered"
    assert result.generation_mode == "deepseek"
    assert result.citations


def test_deepseek_requires_local_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekGenerator()


def test_http_api_and_sse(index):
    client = TestClient(create_app(index))
    assert client.get("/").status_code == 200
    assert "今天要解决" in client.get("/").text
    assert "从问题出发" in client.get("/agents/qa").text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/health/ready").status_code == 200
    response = client.post("/v1/qa", json={"question": "Git 和 GitHub 有什么区别？"})
    assert response.status_code == 200
    assert response.json()["citations"]
    stream = client.post("/v1/qa/events", json={"question": "量子纠缠的定义是什么？"})
    assert stream.status_code == 200
    assert "event: status" in stream.text
    assert "event: done" in stream.text
    assert "insufficient_evidence" in stream.text


def test_missing_index_is_not_ready(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503
    assert client.post("/v1/qa", json={"question": "Git 是什么"}).status_code == 503
    assert client.post("/v1/qa/events", json={"question": "Git 是什么"}).status_code == 503
