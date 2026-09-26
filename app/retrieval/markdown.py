"""Small deterministic Markdown chunker for the curated text corpus."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    heading: str
    text: str


_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_IMAGE = re.compile(r"!?\[[^]]*\]\(https?://[^)]+\)")


def chunk_markdown(document_id: str, markdown: str, max_chars: int = 1100) -> list[Chunk]:
    """Split by heading then paragraph; preserve heading as chunk metadata."""
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    sections: list[tuple[str, list[str]]] = []
    heading = "导言"
    lines: list[str] = []
    in_fence = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
        match = _HEADING.match(line) if not in_fence else None
        if match:
            sections.append((heading, lines))
            heading, lines = match.group(1), []
            continue
        if line.startswith("> - 原文") or line.startswith("> - 译者") or line.startswith("> - 校对") or line.startswith("> - 原文作者"):
            continue
        line = _IMAGE.sub("", line).strip()
        lines.append(line)
    sections.append((heading, lines))

    result: list[Chunk] = []
    for section_heading, section_lines in sections:
        if section_heading in {"目录", "Table of Contents"}:
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(section_lines)) if p.strip()]
        buffer = ""

        def emit(text: str) -> None:
            if len(text) < 40:
                return
            digest = hashlib.sha256(f"{document_id}\n{section_heading}\n{text}".encode()).hexdigest()[:20]
            result.append(Chunk(digest, document_id, section_heading, text))

        for paragraph in paragraphs:
            if paragraph.startswith("- [") and "](#" in paragraph:
                continue
            pieces = [paragraph[i : i + max_chars] for i in range(0, len(paragraph), max_chars)]
            for piece in pieces:
                if buffer and len(buffer) + len(piece) + 2 > max_chars:
                    emit(buffer)
                    buffer = ""
                buffer = f"{buffer}\n\n{piece}" if buffer else piece
        emit(buffer)
    return result
