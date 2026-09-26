import json
from pathlib import Path

import pytest

from app.retrieval.store import build_index
from eval.holdout import evaluate


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus" / "freecodecamp_zh"
LABELS = ROOT / "eval" / "holdout_qa_v1.json"


def test_holdout_report_keeps_raw_evidence_counts(tmp_path):
    db = tmp_path / "course.sqlite3"
    build_index(CORPUS, db)
    report = evaluate(db, LABELS)
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    assert report["metrics"]["retrieval_recall_at_5"]["total"] == len(labels["positive"])
    assert report["metrics"]["no_answer_refusal"]["total"] == len(labels["negative"])
    assert report["metrics"]["retrieval_recall_at_5"]["hits"] == sum(
        item["retrieval_hit"] for item in report["positive_samples"]
    )
    assert report["baseline"]["external_model_calls"] == 0


def test_holdout_rejects_wrong_corpus_snapshot(tmp_path):
    db = tmp_path / "course.sqlite3"
    build_index(CORPUS, db)
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    labels["corpus_manifest_sha256"] = "0" * 64
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps(labels), encoding="utf-8")
    with pytest.raises(ValueError, match="corpus manifest differs"):
        evaluate(db, wrong)
