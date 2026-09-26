"""Local QA API. Public deployment requires auth, limits and further hardening."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.providers.generation import configured_generator
from app.retrieval.store import index_visibility
from app.workflows.grading import GradeRequest, GradeResult, grade_answer
from app.workflows.interview import InterviewRequest, InterviewResult, interview_turn
from app.workflows.qa import QAResult, ask, build_qa_graph
from app.workflows.resume import ResumeRequest, ResumeResult, review_resume


class QARequest(BaseModel):
    question: str = Field(min_length=2, max_length=400)


def create_app(db_path: Path | None = None) -> FastAPI:
    path = db_path or Path(os.getenv("QA_INDEX_PATH", "data/course_index.sqlite3"))
    app = FastAPI(title="MEduAgent Local Workbenches", version="0.1.0")
    web_dir = Path(__file__).resolve().parents[1] / "web"
    app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

    def require_public_index() -> None:
        # This API has no private-document auth; reject private indexes even if configured by mistake.
        if not path.is_file():
            raise HTTPException(status_code=503, detail="Course index not built")
        if index_visibility(path) != "public":
            raise HTTPException(status_code=503, detail="Private index is unavailable over HTTP")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(web_dir / "index.html")

    @app.get("/agents/qa", include_in_schema=False)
    def qa_page():
        return FileResponse(web_dir / "qa.html")

    @app.get("/agents/{agent_name}", include_in_schema=False)
    def agent_page(agent_name: str):
        if agent_name not in {"resume", "grading", "interview"}:
            raise HTTPException(status_code=404, detail="Unknown agent")
        return FileResponse(web_dir / "workbench.html")

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready() -> dict[str, str]:
        require_public_index()
        return {"status": "ready"}

    def run(question: str) -> QAResult:
        require_public_index()
        graph = build_qa_graph(path, configured_generator())
        return ask(graph, question)

    @app.post("/v1/qa", response_model=QAResult)
    def qa(request: QARequest) -> QAResult:
        return run(request.question)

    @app.post("/v1/resume/review", response_model=ResumeResult)
    def resume_review(request: ResumeRequest) -> ResumeResult:
        return review_resume(request)

    @app.post("/v1/grading/check", response_model=GradeResult)
    def grading_check(request: GradeRequest) -> GradeResult:
        return grade_answer(request)

    @app.post("/v1/interview/turn", response_model=InterviewResult)
    def interview_practice(request: InterviewRequest) -> InterviewResult:
        return interview_turn(request)

    @app.post("/v1/qa/events", response_class=EventSourceResponse)
    def qa_events(request: QARequest):
        # Check before streaming starts so missing/private indexes can return HTTP 503.
        require_public_index()

        def events():
            yield ServerSentEvent(data={"stage": "retrieving"}, event="status", id="1")
            try:
                result = run(request.question)
            except Exception:
                # The stream has started, so report a safe error event instead of
                # leaking provider responses or pretending that a result arrived.
                yield ServerSentEvent(data={"message": "问答处理失败，请稍后重试。"}, event="error", id="2")
                return
            yield ServerSentEvent(data=result.model_dump(), event="done", id="2")

        return events()

    return app


app = create_app()
