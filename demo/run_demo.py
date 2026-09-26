"""Run every public example through the real HTTP routes without external keys."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.api import create_app
from app.retrieval.store import build_index


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    # This command is intentionally offline even when a developer has API keys locally.
    os.environ["QA_GENERATION_MODE"] = "extractive"
    cases = json.loads((ROOT / "demo" / "public_cases.json").read_text(encoding="utf-8"))["cases"]

    with TemporaryDirectory(prefix="meduagent-demo-") as directory:
        db_path = Path(directory) / "public.sqlite3"
        build_index(ROOT / "corpus" / "freecodecamp_zh", db_path)
        client = TestClient(create_app(db_path))
        assert client.get("/health/ready").status_code == 200

        for case in cases:
            response = client.post(case["path"], json=case["input"])
            assert response.status_code == 200, f"{case['id']}: HTTP {response.status_code}"
            result = response.json()
            expected = case["expected"]
            for key, value in expected.items():
                if key == "citations_min":
                    assert len(result["citations"]) >= value, case["id"]
                elif key.endswith("_contains"):
                    assert value in result[key.removesuffix("_contains")], case["id"]
                else:
                    assert result[key] == value, f"{case['id']}: {key}"
            print(f"{case['id']}: {result['status']} OK")

    print(f"Public offline demo: {len(cases)}/{len(cases)} cases passed")


if __name__ == "__main__":
    main()
