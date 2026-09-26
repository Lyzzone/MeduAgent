from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.retrieval.store import build_index


CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "freecodecamp_zh"


def test_home_routes_and_assets(tmp_path):
    db = tmp_path / "public.sqlite3"
    build_index(CORPUS, db)
    client = TestClient(create_app(db))
    home = client.get("/")
    assert home.status_code == 200
    for path in ("/agents/qa", "/agents/resume", "/agents/grading", "/agents/interview"):
        assert f'href="{path}"' in home.text
        assert client.get(path).status_code == 200
    assert client.get("/agents/unknown").status_code == 404
    assert client.get("/assets/workbench.js").status_code == 200
    answer = client.post("/v1/qa", json={"question": "Git 和 GitHub 有什么区别？"})
    assert answer.status_code == 200
    assert answer.json()["citations"]


def test_resume_rule_preview(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))
    response = client.post("/v1/resume/review", json={
        "resume_text": "项目经历：掌握Python和SQL，完成课程接口演示。",
        "job_description": "需要 Python、SQL 和 Docker，负责课程平台开发。",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "rule_preview"
    assert result["matched_skills"] == ["Python", "SQL"]
    assert result["missing_skills"] == ["Docker"]
    assert result["checks"]
    assert "Docker" in result["suggestions"][0]


def test_grading_rules_and_review_boundary(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))
    payload = {"question": "读取资源的方法？", "reference_answer": "GET", "student_answer": " get ",
               "question_type": "objective", "max_points": 10}
    correct = client.post("/v1/grading/check", json=payload).json()
    assert correct["suggested_points"] == 10
    assert correct["review_required"] is False
    wrong = client.post("/v1/grading/check", json={**payload, "student_answer": "POST"}).json()
    assert wrong["suggested_points"] == 0
    assert wrong["review_required"] is True
    subjective = client.post("/v1/grading/check", json={**payload, "question_type": "subjective"}).json()
    assert subjective["suggested_points"] is None
    assert subjective["review_required"] is True


def test_interview_question_and_feedback(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.sqlite3"))
    question = client.post("/v1/interview/turn", json={"track": "ai"}).json()
    assert question["status"] == "question_ready"
    assert "RAG" in question["question"]
    feedback = client.post("/v1/interview/turn", json={
        "track": "ai", "answer": "先检索资料，再依据证据回答，最后校验引用。",
    }).json()
    assert feedback["status"] == "practice_feedback"
    assert set(feedback["covered_prompts"]) == {"检索", "引用", "证据"}
    assert "不是" in feedback["feedback"]
