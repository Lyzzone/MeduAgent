"""Rule-only grading preview; subjective answers require teacher review."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class GradeRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    reference_answer: str = Field(min_length=1, max_length=3000)
    student_answer: str = Field(min_length=1, max_length=3000)
    question_type: Literal["objective", "subjective"]
    max_points: int = Field(ge=1, le=100)


class GradeResult(BaseModel):
    status: Literal["rule_scored", "teacher_review_required"]
    suggested_points: int | None
    max_points: int
    reason: str
    review_required: bool


def _normalize_answer(value: str) -> str:
    # This is exact matching after whitespace/case normalization, not semantic grading.
    return re.sub(r"\s+", "", value).casefold()


def grade_answer(request: GradeRequest) -> GradeResult:
    if request.question_type == "subjective":
        return GradeResult(
            status="teacher_review_required", suggested_points=None,
            max_points=request.max_points,
            reason="主观题需要评分 rubric 和教师复核；当前仅记录参考答案与学员答案，不自动给分。",
            review_required=True,
        )

    correct = _normalize_answer(request.student_answer) == _normalize_answer(request.reference_answer)
    return GradeResult(
        status="rule_scored",
        suggested_points=request.max_points if correct else 0,
        max_points=request.max_points,
        reason=("客观题按去空白、忽略大小写后的精确匹配评分。" if correct else
                "客观题答案与参考答案不完全一致；当前规则不识别同义答案，需人工复核边界情况。"),
        review_required=not correct,
    )
