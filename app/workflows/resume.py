"""Deterministic resume checks for the local demo; no experience is invented."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


SKILLS = (
    "Python", "Java", "SQL", "Git", "Docker", "Linux", "FastAPI",
    "Redis", "MySQL", "PostgreSQL", "RAG", "LangGraph",
)


class ResumeRequest(BaseModel):
    resume_text: str = Field(min_length=20, max_length=12000)
    job_description: str = Field(min_length=10, max_length=5000)


class ResumeResult(BaseModel):
    status: Literal["rule_preview"] = "rule_preview"
    matched_skills: list[str]
    missing_skills: list[str]
    checks: list[str]
    suggestions: list[str]


def _mentioned(text: str, skill: str) -> bool:
    # Only ASCII letters/digits are word boundaries: Chinese may touch "Python" directly.
    pattern = rf"(?<![A-Za-z0-9]){re.escape(skill)}(?![A-Za-z0-9])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def review_resume(request: ResumeRequest) -> ResumeResult:
    required = [skill for skill in SKILLS if _mentioned(request.job_description, skill)]
    matched = [skill for skill in required if _mentioned(request.resume_text, skill)]
    missing = [skill for skill in required if skill not in matched]

    checks = []
    if not re.search(r"项目|project", request.resume_text, re.IGNORECASE):
        checks.append("没有识别到项目经历标题，请确认是否写清项目背景、职责和结果。")
    if not re.search(r"\d+(?:\.\d+)?\s*(?:%|％|人|次|小时|ms|秒|万|千)", request.resume_text):
        checks.append("没有识别到量化结果；仅在有真实数据时补充指标及统计口径。")

    suggestions = []
    if missing:
        suggestions.append(
            "岗位要求中出现但简历未提及：" + "、".join(missing)
            + "。仅补充实际掌握并有证据支持的技能。"
        )
    if not checks and not missing:
        suggestions.append("已匹配到当前规则识别的岗位关键词；下一步仍需人工检查经历真实性和表达清晰度。")

    return ResumeResult(
        matched_skills=matched, missing_skills=missing,
        checks=checks, suggestions=suggestions,
    )
