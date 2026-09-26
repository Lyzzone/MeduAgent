"""Local corpus ingestion and QA command line entry points."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.providers.generation import ExtractiveGenerator, configured_generator
from app.retrieval.private_pdf import build_private_pdf_index, import_private_pdfs
from app.retrieval.store import build_index, index_visibility
from app.workflows.qa import ask, build_qa_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="MEduAgent local QA MVP")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Index the pinned public course corpus")
    ingest.add_argument("--corpus", type=Path, default=Path("corpus/freecodecamp_zh"))
    ingest.add_argument("--db", type=Path, default=Path("data/course_index.sqlite3"))
    private_import = sub.add_parser("import-private-pdf", help="Copy PDFs into ignored local storage")
    private_import.add_argument("sources", type=Path, nargs="+")
    private_import.add_argument("--corpus", type=Path, default=Path("data/private_corpus"))
    private_ingest = sub.add_parser("ingest-private-pdf", help="Build a separate private PDF index")
    private_ingest.add_argument("--corpus", type=Path, default=Path("data/private_corpus"))
    private_ingest.add_argument("--db", type=Path, default=Path("data/private_pdf_index.sqlite3"))
    qa = sub.add_parser("ask", help="Ask a question against the built index")
    qa.add_argument("question")
    qa.add_argument("--db", type=Path, default=Path("data/course_index.sqlite3"))
    private_qa = sub.add_parser("ask-private", help="Local extractive query; never calls a model API")
    private_qa.add_argument("question")
    private_qa.add_argument("--db", type=Path, default=Path("data/private_pdf_index.sqlite3"))
    args = parser.parse_args()
    if args.command == "ingest":
        print(json.dumps(build_index(args.corpus, args.db), ensure_ascii=False))
    elif args.command == "import-private-pdf":
        print(json.dumps(import_private_pdfs(args.sources, args.corpus), ensure_ascii=False))
    elif args.command == "ingest-private-pdf":
        print(json.dumps(build_private_pdf_index(args.corpus, args.db), ensure_ascii=False))
    elif args.command == "ask-private":
        if index_visibility(args.db) != "private":
            raise ValueError("ask-private requires a private index")
        print(ask(build_qa_graph(args.db, ExtractiveGenerator()), args.question).model_dump_json(indent=2))
    else:
        if index_visibility(args.db) != "public":
            raise ValueError("Use ask-private for private PDFs")
        print(ask(build_qa_graph(args.db, configured_generator()), args.question).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
