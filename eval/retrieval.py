"""Report raw retrieval hits and no-answer behavior on the small dev set."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.retrieval.store import search


def evaluate(db: Path, labels: Path, top_k: int = 5) -> dict:
    dataset = json.loads(labels.read_text(encoding="utf-8"))
    details = []
    with sqlite3.connect(db) as connection:
        for sample in dataset["positive"]:
            gold = {row[0] for row in connection.execute(
                "SELECT chunk_id FROM chunks WHERE document_id = ? AND heading = ?",
                (sample["document_id"], sample["heading"]),
            )}
            if not gold:
                raise ValueError(f"Gold heading absent from index: {sample['id']}")
            hits = search(db, sample["question"], top_k)
            found = next((item.rank for item in hits if item.chunk_id in gold), None)
            details.append({"id": sample["id"], "question": sample["question"],
                            "gold_chunk_ids": sorted(gold), "retrieved_chunk_ids": [h.chunk_id for h in hits],
                            "first_gold_rank": found, "hit": found is not None})
    negative_details = []
    for sample in dataset["negative"]:
        hits = search(db, sample["question"], top_k)
        negative_details.append({"id": sample["id"], "question": sample["question"],
                                 "retrieved_chunk_ids": [h.chunk_id for h in hits], "refused": not hits})
    positive_hits = sum(item["hit"] for item in details)
    negative_refusals = sum(item["refused"] for item in negative_details)
    return {
        "dataset": dataset["name"], "kind": dataset["purpose"],
        "corpus_commit": dataset["corpus_commit"], "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "retrieval": {"metric": f"Recall@{top_k}", "hits": positive_hits,
                      "total": len(details), "value": positive_hits / len(details)},
        "out_of_scope": {"metric": "retrieval_refusal_rate", "refused": negative_refusals,
                         "total": len(negative_details), "value": negative_refusals / len(negative_details)},
        "positive_samples": details, "negative_samples": negative_details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("data/course_index.sqlite3"))
    parser.add_argument("--labels", type=Path, default=Path("eval/dev_qa.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.db, args.labels)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(json.dumps({"retrieval": report["retrieval"], "out_of_scope": report["out_of_scope"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
