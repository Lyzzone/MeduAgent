"""Fixed interview questions with keyword prompts, not ability assessment."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


INTERVIEW_BANK = {
    "backend": ("请解释 HTTP GET 与 POST 的语义区别，并举一个你在项目中使用的例子。", ("GET", "POST", "项目")),
    "ai": ("请描述一次 RAG 问答请求从检索到引用校验的完整流程。", ("检索", "引用", "证据")),
    "data": ("请说明 SQL JOIN 的常见类型，以及你会如何验证查询结果。", ("JOIN", "验证", "结果")),
}


class InterviewRequest(BaseModel):
    track: Literal["backend", "ai", "data"]
    answer: str = Field(default="", max_length=4000)


class InterviewResult(BaseModel):
    status: Literal["question_ready", "practice_feedback"]
    question: str
    feedback: str
    covered_prompts: list[str]
    follow_up: str


def interview_turn(request: InterviewRequest) -> InterviewResult:
    question, prompts = INTERVIEW_BANK[request.track]
    if not request.answer.strip():
        return InterviewResult(
            status="question_ready", question=question,
            feedback="先回答问题，再查看练习提示。",
            covered_prompts=[], follow_up="",
        )

    answer = request.answer.casefold()
    covered = [word for word in prompts if word.casefold() in answer]
    missing = [word for word in prompts if word not in covered]
    feedback = ("回答提到了提示词：" + "、".join(covered) + "。" if covered else "暂未命中预设提示词。")
    feedback += " 这是关键词覆盖提示，不是对回答正确性、能力或录用结果的评价。"
    follow_up = (
        "可以继续解释：" + "、".join(missing) + "。" if missing else
        "请补充具体项目例子，并解释你的验证方法。"
    )
    return InterviewResult(
        status="practice_feedback", question=question, feedback=feedback,
        covered_prompts=covered, follow_up=follow_up,
    )
