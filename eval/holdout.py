"""Evaluate the frozen QA set without tuning on its results."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.providers.generation import ExtractiveGenerator
from app.retrieval.store import search
from app.workflows.qa import ask, build_qa_graph


def _rate(hits: int, total: int) -> dict[str, int | float]:
    return {"hits": hits, "total": total, "value": hits / total}


def evaluate(db: Path, labels: Path) -> dict:
    label_bytes = labels.read_bytes()
    dataset = json.loads(label_bytes)
    if dataset["top_k"] != 5:
        raise ValueError("QA graph currently retrieves five chunks; holdout top_k must be 5")

    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'corpus_manifest_sha256'"
        ).fetchone()
        actual_manifest_hash = row[0] if row else None
        if actual_manifest_hash != dataset["corpus_manifest_sha256"].lower():
            raise ValueError("Index corpus manifest differs from frozen QA labels; rebuild or use the matching snapshot")
        indexed_ids = {row[0] for row in connection.execute("SELECT chunk_id FROM chunks")}

    all_samples = dataset["positive"] + dataset["negative"]
    ids = [item["id"] for item in all_samples]
    if len(ids) != len(set(ids)) or not dataset["positive"] or not dataset["negative"]:
        raise ValueError("Holdout needs unique IDs and nonempty positive/negative groups")

    graph = build_qa_graph(db, ExtractiveGenerator())
    positive: list[dict] = []
    negative: list[dict] = []
    retrieval_times: list[float] = []

    for sample in dataset["positive"]:
        gold = set(sample["gold_chunk_ids"])
        if not gold or not gold <= indexed_ids:
            raise ValueError(f"Gold chunk missing from index: {sample['id']}")
        start = time.perf_counter()
        hits = search(db, sample["question"], dataset["top_k"])
        retrieval_times.append((time.perf_counter() - start) * 1000)
        found = next((hit.rank for hit in hits if hit.chunk_id in gold), None)
        result = ask(graph, sample["question"])
        cited = {citation.chunk_id for citation in result.citations}
        retrieved = {hit.chunk_id for hit in hits}
        positive.append({
            "id": sample["id"], "category": sample["category"],
            "question": sample["question"], "gold_chunk_ids": sorted(gold),
            "retrieved_chunk_ids": [hit.chunk_id for hit in hits],
            "first_gold_rank": found, "retrieval_hit": found is not None,
            "qa_status": result.status, "cited_chunk_ids": sorted(cited),
            "citation_ids_valid": bool(cited) and cited <= retrieved,
            "cites_gold": bool(cited & gold),
            "answer_points_for_manual_review": sample["answer_points"],
        })

    for sample in dataset["negative"]:
        start = time.perf_counter()
        hits = search(db, sample["question"], dataset["top_k"])
        retrieval_times.append((time.perf_counter() - start) * 1000)
        result = ask(graph, sample["question"])
        negative.append({
            "id": sample["id"], "category": sample["category"],
            "question": sample["question"], "reason": sample["reason"],
            "retrieved_chunk_ids": [hit.chunk_id for hit in hits],
            "retrieval_refused": not hits,
            "qa_status": result.status,
            "qa_refused": result.status == "insufficient_evidence" and not result.citations,
        })

    pos_hits = sum(item["retrieval_hit"] for item in positive)
    cited_gold = sum(item["cites_gold"] for item in positive)
    legal_citations = sum(item["citation_ids_valid"] for item in positive)
    neg_refusals = sum(item["qa_refused"] for item in negative)
    ordered_times = sorted(retrieval_times)
    return {
        "dataset": dataset["name"],
        "dataset_sha256": hashlib.sha256(label_bytes).hexdigest(),
        "corpus_manifest_sha256": actual_manifest_hash,
        "corpus_commit": dataset["corpus_commit"],
        "annotation": dataset["annotation"],
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version},
        "baseline": {"retriever": "SQLite FTS5 lexical", "top_k": 5,
                     "generator": "local extractive", "external_model_calls": 0},
        "metrics": {
            "retrieval_recall_at_5": _rate(pos_hits, len(positive)),
            "cites_gold_at_5": _rate(cited_gold, len(positive)),
            "valid_nonempty_citations": _rate(legal_citations, len(positive)),
            "no_answer_refusal": _rate(neg_refusals, len(negative)),
        },
        "retrieval_latency_ms": {
            "median": round(statistics.median(ordered_times), 2),
            "p95": round(ordered_times[math.ceil(0.95 * len(ordered_times)) - 1], 2),
            "count": len(ordered_times),
        },
        "failures": {
            "positive_ids": [item["id"] for item in positive if not item["cites_gold"]],
            "negative_ids": [item["id"] for item in negative if not item["qa_refused"]],
        },
        "positive_samples": positive,
        "negative_samples": negative,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the frozen public QA set")
    parser.add_argument("--db", type=Path, default=Path("data/course_index.sqlite3"))
    parser.add_argument("--labels", type=Path, default=Path("eval/holdout_qa_v1.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.db, args.labels)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"metrics": report["metrics"], "failures": report["failures"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
