"""Private corpus ingestion and access-boundary tests with synthetic PDFs."""

import json
import sys

import fitz
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.cli import main
from app.providers.generation import ExtractiveGenerator
from app.retrieval.private_pdf import build_private_pdf_index, import_private_pdfs
from app.retrieval.store import index_visibility, search
from app.workflows.qa import ask, build_qa_graph


def _sample_pdf(path):
    document = fitz.open()
    first = document.new_page()
    first.insert_text((72, 72), "Vector retrieval uses a searchable index. " * 4)
    second = document.new_page()
    second.insert_text((72, 72), "Transformer attention scores relate query and key vectors. " * 4)
    document.new_page()
    document.save(path)
    document.close()


def test_private_pdf_page_citations_and_http_isolation(tmp_path):
    source = tmp_path / "sample.pdf"
    _sample_pdf(source)
    corpus = tmp_path / "private_corpus"
    db = tmp_path / "private.sqlite3"
    assert import_private_pdfs([source], corpus)["documents"] == 1
    stats = build_private_pdf_index(corpus, db)
    assert stats["documents"] == 1
    assert stats["pages"] == 3
    assert stats["zero_text_pages"]
    assert list(stats["zero_text_pages"].values()) == [[3]]
    assert index_visibility(db) == "private"
    hits = search(db, "Transformer attention")
    assert hits and hits[0].page == 2
    assert hits[0].source_url == ""
    result = ask(build_qa_graph(db, ExtractiveGenerator()), "Transformer attention")
    assert result.citations[0].page == 2
    client = TestClient(create_app(db))
    assert client.get("/health/ready").status_code == 503
    assert client.post("/v1/qa", json={"question": "Transformer attention"}).status_code == 503
    assert client.post("/v1/qa/events", json={"question": "Transformer attention"}).status_code == 503

    class ExternalGenerator:
        def generate(self, question, evidence):
            raise AssertionError("Private text must never reach this generator")

    with pytest.raises(ValueError, match="Private index"):
        build_qa_graph(db, ExternalGenerator())


def test_private_pdf_hash_mismatch_is_rejected(tmp_path):
    source = tmp_path / "sample.pdf"
    _sample_pdf(source)
    corpus = tmp_path / "private_corpus"
    import_private_pdfs([source], corpus)
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["visibility"] == "private"
    (corpus / "pdfs" / "sample.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_private_pdf_index(corpus, tmp_path / "private.sqlite3")


def test_private_cli_stays_local_even_with_external_mode(tmp_path, monkeypatch, capsys):
    source = tmp_path / "sample.pdf"
    _sample_pdf(source)
    corpus = tmp_path / "private_corpus"
    db = tmp_path / "private.sqlite3"
    import_private_pdfs([source], corpus)
    build_private_pdf_index(corpus, db)
    monkeypatch.setenv("QA_GENERATION_MODE", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["app.cli", "ask-private", "Transformer attention", "--db", str(db)])
    main()
    assert json.loads(capsys.readouterr().out)["generation_mode"] == "extractive"
    monkeypatch.setattr(sys, "argv", ["app.cli", "ask", "Transformer attention", "--db", str(db)])
    with pytest.raises(ValueError, match="Use ask-private"):
        main()
