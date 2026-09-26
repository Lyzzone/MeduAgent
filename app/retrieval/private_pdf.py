"""Local-only PDF import and page-aware FTS5 indexing.

The PDF files, manifest and derived index belong under ignored data/ paths.
No PDF content is sent to a model provider by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

import fitz

from app.retrieval.store import add_chunk, connect_index, create_schema


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def import_private_pdfs(sources: list[Path], corpus_dir: Path) -> dict[str, int]:
    """Copy user-supplied PDFs into the ignored private corpus and pin hashes."""
    if not sources:
        raise ValueError("At least one PDF is required")
    corpus_dir = corpus_dir.resolve()
    pdf_dir = corpus_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    seen_names: set[str] = set()
    for source in sources:
        source = source.resolve()
        if not source.is_file() or source.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF file: {source}")
        if source.name in seen_names:
            raise ValueError(f"Duplicate PDF name: {source.name}")
        seen_names.add(source.name)
        destination = pdf_dir / source.name
        expected_hash = _sha256(source)
        if source != destination:
            temporary = pdf_dir / (source.name + ".copying")
            try:
                shutil.copyfile(source, temporary)
                if _sha256(temporary) != expected_hash:
                    raise ValueError(f"Copy hash mismatch: {source.name}")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        entries.append({
            "path": source.name,
            "title": source.stem,
            "document_id": "pdf-" + expected_hash[:16],
            "sha256": expected_hash,
        })
    manifest = {"visibility": "private", "files": entries}
    temporary_manifest = corpus_dir / "manifest.json.writing"
    temporary_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_manifest, corpus_dir / "manifest.json")
    return {"documents": len(entries), "bytes": sum((pdf_dir / item["path"]).stat().st_size for item in entries)}


def _page_chunks(text: str, max_chars: int = 1000) -> list[str]:
    """Bound each chunk to one source page so citations cannot cross pages."""
    normalized = re.sub(r"[ \t]+", " ", text.replace("\x00", "")).strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        for start in range(0, len(paragraph), max_chars):
            piece = paragraph[start:start + max_chars]
            if buffer and len(buffer) + len(piece) + 2 > max_chars:
                if len(buffer) >= 40:
                    chunks.append(buffer)
                buffer = ""
            buffer = f"{buffer}\n\n{piece}" if buffer else piece
    if buffer:
        if len(buffer) < 40 and chunks:
            chunks[-1] += "\n\n" + buffer
        elif len(buffer) >= 40:
            chunks.append(buffer)
    return chunks


def build_private_pdf_index(corpus_dir: Path, db_path: Path) -> dict[str, object]:
    """Hash-check and index each PDF page into a separate, private database."""
    corpus_dir, db_path = corpus_dir.resolve(), db_path.resolve()
    manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("visibility") != "private":
        raise ValueError("Private PDF manifest must declare private visibility")
    entries = manifest.get("files", [])
    if not entries:
        raise ValueError("Private PDF manifest has no files")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = db_path.with_name(db_path.name + ".building")
    temporary.unlink(missing_ok=True)
    connection = connect_index(temporary)
    stats: dict[str, object] = {"documents": 0, "pages": 0, "chunks": 0, "zero_text_pages": {}, "low_text_pages": {}}
    try:
        create_schema(connection, "private")
        for entry in entries:
            name = entry["path"]
            if Path(name).name != name or not name.lower().endswith(".pdf"):
                raise ValueError(f"Unsafe PDF path: {name}")
            source = corpus_dir / "pdfs" / name
            actual_hash = _sha256(source)
            if actual_hash.lower() != entry["sha256"].lower():
                raise ValueError(f"SHA-256 mismatch: {name}")
            document_id, title = entry["document_id"], entry["title"]
            if not re.fullmatch(r"pdf-[0-9a-f]{16}", document_id):
                raise ValueError(f"Unsafe document ID: {document_id}")
            connection.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
                (document_id, title, "", "", "", actual_hash),
            )
            stats["documents"] += 1
            zero_pages: list[int] = []
            low_pages: list[int] = []
            with fitz.open(source) as document:
                for page_index in range(document.page_count):
                    page_number = page_index + 1
                    content = document[page_index].get_text("text", sort=True)
                    if not content.strip():
                        zero_pages.append(page_number)
                    elif len(content.strip()) < 50:
                        low_pages.append(page_number)
                    heading = f"第 {page_number} 页"
                    for chunk_number, body in enumerate(_page_chunks(content), start=1):
                        chunk_id = hashlib.sha256(
                            f"{actual_hash}\n{page_number}\n{chunk_number}\n{body}".encode("utf-8")
                        ).hexdigest()[:20]
                        add_chunk(connection, chunk_id, document_id, title, heading, body, page_number)
                        stats["chunks"] += 1
                    stats["pages"] += 1
            stats["zero_text_pages"][document_id] = zero_pages
            stats["low_text_pages"][document_id] = low_pages
        connection.commit()
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()
    os.replace(temporary, db_path)
    return stats
