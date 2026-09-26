"""SQLite FTS5 index shared by public lessons and local private PDFs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from app.retrieval.markdown import chunk_markdown

_LATIN = re.compile(r"[a-zA-Z][a-zA-Z0-9_+-]*")
_CJK = re.compile(r"[\u3400-\u9fff]+")
_STOP = {
    "什么", "如何", "怎么", "的是", "一个", "可以", "哪些", "是否", "解释", "请问", "一下", "以及",
    "有什", "么区", "区别", "的定", "定义", "义是", "是什", "作用", "用是", "为什",
}


def search_terms(text: str) -> list[str]:
    terms = {part.lower() for part in _LATIN.findall(text) if len(part) > 1}
    for sequence in _CJK.findall(text):
        terms.update(sequence[i : i + 2] for i in range(len(sequence) - 1))
    return sorted(term for term in terms if term not in _STOP)


def connect_index(db_path: Path) -> sqlite3.Connection:
    """Open an index with named columns for both public and private ingesters."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def create_schema(connection: sqlite3.Connection, visibility: str) -> None:
    if visibility not in {"public", "private"}:
        raise ValueError("Unknown corpus visibility")
    connection.executescript("""
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE documents (
            document_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_url TEXT NOT NULL,
            author TEXT NOT NULL,
            translator TEXT NOT NULL,
            source_sha256 TEXT NOT NULL
        );
        CREATE TABLE chunks (
            rowid INTEGER PRIMARY KEY,
            chunk_id TEXT UNIQUE NOT NULL,
            document_id TEXT NOT NULL REFERENCES documents(document_id),
            heading TEXT NOT NULL,
            body TEXT NOT NULL,
            page INTEGER
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(search_text);
    """)
    connection.execute("INSERT INTO metadata VALUES ('visibility', ?)", (visibility,))


def add_chunk(connection: sqlite3.Connection, chunk_id: str, document_id: str,
              title: str, heading: str, body: str, page: int | None = None) -> None:
    cursor = connection.execute(
        "INSERT INTO chunks(chunk_id, document_id, heading, body, page) VALUES (?, ?, ?, ?, ?)",
        (chunk_id, document_id, heading, body, page),
    )
    terms = " ".join(search_terms(title + " " + heading + " " + body))
    connection.execute(
        "INSERT INTO chunks_fts(rowid, search_text) VALUES (?, ?)",
        (cursor.lastrowid, terms),
    )


def index_visibility(db_path: Path) -> str:
    if not db_path.is_file():
        raise FileNotFoundError(f"Index missing: {db_path}")
    with closing(connect_index(db_path)) as connection:
        try:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'visibility'"
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise ValueError("Index has no visibility metadata; rebuild it") from exc
    if row is None or row["value"] not in {"public", "private"}:
        raise ValueError("Index has invalid visibility metadata")
    return row["value"]


def build_index(corpus_dir: Path, db_path: Path) -> dict[str, int]:
    """Validate pinned source hashes, then atomically replace the local index."""
    corpus_dir, db_path = corpus_dir.resolve(), db_path.resolve()
    manifest_bytes = (corpus_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    license_name = manifest["license_file"]
    if Path(license_name).name != license_name:
        raise ValueError("Unsafe license path")
    license_hash = hashlib.sha256((corpus_dir / license_name).read_bytes()).hexdigest()
    if license_hash.lower() != manifest["license_sha256"].lower():
        raise ValueError("SHA-256 mismatch: license")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = db_path.with_name(db_path.name + ".building")
    if temporary.exists():
        temporary.unlink()
    connection = connect_index(temporary)
    document_count = 0
    chunk_count = 0
    try:
        create_schema(connection, "public")
        connection.execute(
            "INSERT INTO metadata VALUES (?, ?)",
            ("corpus_manifest_sha256", hashlib.sha256(manifest_bytes).hexdigest()),
        )
        for entry in manifest["files"]:
            name = entry["path"]
            if Path(name).name != name or not name.endswith(".md"):
                raise ValueError(f"Unsafe corpus path: {name}")
            source = corpus_dir / name
            payload = source.read_bytes()
            actual = hashlib.sha256(payload).hexdigest()
            if actual.lower() != entry["sha256"].lower():
                raise ValueError(f"SHA-256 mismatch: {name}")
            document_id = source.stem
            title = document_id.replace("-", " ")
            connection.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
                (document_id, title, entry["original_url"], entry["author"], entry["translator"], actual),
            )
            document_count += 1
            for chunk in chunk_markdown(document_id, payload.decode("utf-8-sig")):
                # A short section inherits its article title for technical queries.
                add_chunk(connection, chunk.chunk_id, chunk.document_id, title,
                          chunk.heading, chunk.text)
                chunk_count += 1
        connection.commit()
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()
    os.replace(temporary, db_path)
    return {"documents": document_count, "chunks": chunk_count}


@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    document_id: str
    title: str
    heading: str
    source_url: str
    author: str
    translator: str
    quote: str
    page: int | None
    rank: int
    matched_terms: int
    query_terms: int


def search(db_path: Path, question: str, limit: int = 5) -> list[Evidence]:
    if not db_path.is_file():
        raise FileNotFoundError(f"Index missing: {db_path}")
    # Remove common question scaffolding before CJK bigrams are formed.
    cleaned = re.sub(r"可以做什么|有什么区别|是什么|有什么用途|如何|怎么|请问", " ", question)
    terms = search_terms(cleaned)
    if not terms:
        return []
    expression = " OR ".join(f'"{term}"' for term in terms)
    with closing(connect_index(db_path)) as connection:
        rows = connection.execute(
            """SELECT c.chunk_id, c.document_id, c.heading, c.body, c.page,
                      d.title, d.source_url, d.author, d.translator,
                      f.search_text, bm25(chunks_fts) AS score
               FROM chunks_fts AS f JOIN chunks AS c ON c.rowid = f.rowid
               JOIN documents AS d ON d.document_id = c.document_id
               WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?""",
            (expression, min(max(limit * 20, 100), 250)),
        ).fetchall()
    ranked: list[tuple[float, int, float, sqlite3.Row]] = []
    total_weight = sum(4 if term.isascii() else 1 for term in terms)
    for row in rows:
        indexed_terms = set(row["search_text"].split())
        matched = indexed_terms.intersection(terms)
        overlap = len(matched)
        matched_weight = sum(4 if term.isascii() else 1 for term in matched)
        # OR queries otherwise admit a chunk matching only generic question words.
        if matched_weight / total_weight < 0.40:
            continue
        heading_terms = set(search_terms(row["heading"]))
        heading_match_weight = sum(4 if term.isascii() else 1 for term in matched.intersection(heading_terms))
        title_terms = set(search_terms(row["title"]))
        title_match_weight = sum(4 if term.isascii() else 1 for term in matched.intersection(title_terms))
        relevance = (matched_weight / total_weight + 0.15 * heading_match_weight / total_weight
                     + 0.30 * title_match_weight / total_weight)
        ranked.append((relevance, overlap, row["score"], row))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    # A comparison question needs evidence for each named technical term.
    # Keep one short, on-topic heading per term before filling remaining slots.
    latin_terms = [term for term in terms if term.isascii()]
    if latin_terms and ranked:
        preferred_document = ranked[0][3]["document_id"]
        selected: list[tuple[float, int, float, sqlite3.Row]] = []
        selected_ids: set[str] = set()
        for term in latin_terms:
            heading_candidates = [
                item for item in ranked
                if item[3]["document_id"] == preferred_document
                and term in search_terms(item[3]["heading"])
                and item[3]["chunk_id"] not in selected_ids
            ]
            if heading_candidates:
                definition_question = any(word in question for word in ("是什么", "定义", "区别"))
                chosen = min(
                    heading_candidates,
                    key=lambda item: (
                        0 if definition_question and item[3]["heading"].startswith("什么是") else 1,
                        len(item[3]["heading"]), item[2],
                    ),
                )
                selected.append(chosen)
                selected_ids.add(chosen[3]["chunk_id"])
        ranked = selected + [item for item in ranked if item[3]["chunk_id"] not in selected_ids]
    return [
        Evidence(
            chunk_id=row["chunk_id"], document_id=row["document_id"],
            title=row["title"], heading=row["heading"], source_url=row["source_url"],
            author=row["author"], translator=row["translator"], quote=row["body"][:500],
            page=row["page"],
            rank=rank, matched_terms=overlap, query_terms=len(terms),
        )
        for rank, (_, overlap, _, row) in enumerate(ranked[:limit], start=1)
    ]
