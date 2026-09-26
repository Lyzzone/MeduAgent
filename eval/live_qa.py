"""Bounded public-only live QA probe; semantic grading stays manual."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.providers.generation import DeepSeekGenerator, Generator
from app.retrieval.store import index_visibility, search
from app.workflows.qa import ask, build_qa_graph


def evaluate_live(db: Path, labels: Path, ids: list[str], generator: Generator) -> dict:
    if not ids or len(ids) > 10 or len(ids) != len(set(ids)):
        raise ValueError("Choose 1-10 unique sample IDs")
    if index_visibility(db) != "public":
        raise ValueError("Live evaluation only accepts a public index")
    label_bytes = labels.read_bytes()
    dataset = json.loads(label_bytes)
    if dataset["top_k"] != 5:
        raise ValueError("Live evaluation requires top_k=5")
    with sqlite3.connect(db) as connection:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = 'corpus_manifest_sha256'"
        ).fetchone()
    if row is None or row[0] != dataset["corpus_manifest_sha256"].lower():
        raise ValueError("Index corpus manifest differs from frozen labels")

    samples = {item["id"]: item for item in dataset["positive"] + dataset["negative"]}
    if any(sample_id not in samples for sample_id in ids):
        raise ValueError("Unknown holdout sample ID")
    graph = build_qa_graph(db, generator)
    records: list[dict] = []
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for sample_id in ids:
        sample = samples[sample_id]
        hits = search(db, sample["question"], 5)
        result = ask(graph, sample["question"])
        cited = {item.chunk_id for item in result.citations}
        retrieved = {item.chunk_id for item in hits}
        usage = result.token_usage or {}
        for key in totals:
            totals[key] += usage.get(key, 0)
        record = {
            "id": sample_id, "question": sample["question"],
            "retrieved_chunk_ids": [item.chunk_id for item in hits],
            "status": result.status, "answer": result.answer,
            "cited_chunk_ids": sorted(cited),
            "citation_ids_valid": bool(cited) and cited <= retrieved,
            "model_id": result.model_id, "prompt_version": result.prompt_version,
            "token_usage": result.token_usage, "latency_ms": result.latency_ms,
        }
        if "gold_chunk_ids" in sample:
            record["gold_chunk_ids"] = sample["gold_chunk_ids"]
            record["cites_gold"] = bool(cited.intersection(sample["gold_chunk_ids"]))
            record["answer_points_for_manual_review"] = sample["answer_points"]
        else:
            record["expected_no_answer_reason"] = sample["reason"]
            record["refused"] = result.status == "insufficient_evidence" and not cited
        records.append(record)
    return {
        "dataset": dataset["name"],
        "dataset_sha256": hashlib.sha256(label_bytes).hexdigest(),
        "corpus_manifest_sha256": row[0],
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selected_ids": ids,
        "sample_count": len(records),
        "token_totals": totals,
        "manual_answer_review_required": True,
        "cost_currency": None,
        "note": "Citation ID validity is structural; answer correctness and groundedness need manual review. This selected probe is not a full-set accuracy metric.",
        "samples": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe 1-10 frozen public QA cases with DeepSeek")
    parser.add_argument("--db", type=Path, default=Path("data/course_index.sqlite3"))
    parser.add_argument("--labels", type=Path, default=Path("eval/holdout_qa_v1.json"))
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_live(args.db, args.labels, args.ids, DeepSeekGenerator())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output), "sample_count": report["sample_count"],
        "token_totals": report["token_totals"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
