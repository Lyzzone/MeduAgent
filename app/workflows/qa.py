"""Course question-answer graph with explicit evidence and refusal paths."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.providers.generation import ExtractiveGenerator, Generator
from app.retrieval.store import Evidence, index_visibility, search


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    heading: str
    source_url: str
    author: str
    translator: str
    quote: str
    page: int | None = None


class QAResult(BaseModel):
    status: Literal["answered", "retrieval_preview", "insufficient_evidence"]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    generation_mode: str


class QAState(TypedDict, total=False):
    question: str
    evidence: list[Evidence]
    answer: str
    citation_ids: list[str]
    status: str
    generation_mode: str


def build_qa_graph(db_path: Path, generator: Generator):
    if index_visibility(db_path) == "private" and not isinstance(generator, ExtractiveGenerator):
        raise ValueError("Private index only supports local extractive generation")

    def retrieve(state: QAState) -> QAState:
        return {"evidence": search(db_path, state["question"])}

    def choose(state: QAState) -> Literal["answer", "refuse"]:
        return "answer" if state["evidence"] else "refuse"

    def answer(state: QAState) -> QAState:
        draft = generator.generate(state["question"], state["evidence"])
        return {"answer": draft.answer, "citation_ids": draft.citation_ids,
                "generation_mode": draft.mode}

    def validate(state: QAState) -> QAState:
        allowed = {item.chunk_id for item in state["evidence"]}
        citations = state.get("citation_ids", [])
        if (not citations or any(chunk_id not in allowed for chunk_id in citations)
                or state["answer"].strip().startswith("资料不足")):
            return {"status": "insufficient_evidence", "answer": "资料不足，无法回答。", "citation_ids": []}
        return {"status": "retrieval_preview" if state["generation_mode"] == "extractive" else "answered"}

    def refuse(state: QAState) -> QAState:
        return {"status": "insufficient_evidence", "answer": "资料不足，无法回答。",
                "citation_ids": [], "generation_mode": "none"}

    graph = StateGraph(QAState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("answer", answer)
    graph.add_node("validate", validate)
    graph.add_node("refuse", refuse)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", choose, {"answer": "answer", "refuse": "refuse"})
    graph.add_edge("answer", "validate")
    graph.add_edge("validate", END)
    graph.add_edge("refuse", END)
    return graph.compile()


def ask(graph, question: str) -> QAResult:
    state = graph.invoke({"question": question})
    cited = set(state["citation_ids"])
    # Return only evidence IDs accepted by the graph's citation validator.
    citations = [
        Citation(
            chunk_id=item.chunk_id, document_id=item.document_id,
            title=item.title, heading=item.heading, source_url=item.source_url,
            author=item.author, translator=item.translator,
            quote=item.quote, page=item.page,
        )
        for item in state["evidence"] if item.chunk_id in cited
    ]
    return QAResult(status=state["status"], answer=state["answer"],
                    citations=citations, generation_mode=state["generation_mode"])
