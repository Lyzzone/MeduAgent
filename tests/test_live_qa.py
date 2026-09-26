from pathlib import Path

import pytest

from app.providers.generation import Draft
from app.retrieval.store import build_index
from eval.live_qa import evaluate_live


ROOT = Path(__file__).resolve().parents[1]


class FixedGenerator:
    def generate(self, question, evidence):
        return Draft(
            answer="根据资料回答。", citation_ids=[evidence[0].chunk_id],
            mode="deepseek", model_id="mock-model",
            prompt_version="qa-json-evidence-v1",
            token_usage={"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            latency_ms=1.5,
        )


def test_live_probe_records_provenance_and_usage(tmp_path):
    db = tmp_path / "public.sqlite3"
    build_index(ROOT / "corpus/freecodecamp_zh", db)
    report = evaluate_live(
        db, ROOT / "eval/holdout_qa_v1.json", ["h01"], FixedGenerator(),
    )
    assert report["sample_count"] == 1
    assert report["token_totals"] == {
        "prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14,
    }
    assert report["samples"][0]["model_id"] == "mock-model"
    assert report["samples"][0]["citation_ids_valid"] is True
    assert report["manual_answer_review_required"] is True


def test_live_probe_rejects_unbounded_or_duplicate_ids(tmp_path):
    labels = ROOT / "eval/holdout_qa_v1.json"
    with pytest.raises(ValueError, match="1-10 unique"):
        evaluate_live(tmp_path / "unused.sqlite3", labels, ["h01"] * 11, FixedGenerator())
    with pytest.raises(ValueError, match="1-10 unique"):
        evaluate_live(tmp_path / "unused.sqlite3", labels, ["h01", "h01"], FixedGenerator())
