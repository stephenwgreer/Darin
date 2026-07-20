"""End-to-end knowledge-base ingestion + retrieval with the REAL stack.

Requires the optional ``rag`` extra (pymupdf + sentence-transformers/torch);
skipped cleanly when it is absent so base CI stays green. The first run
downloads the embedding model (~130MB) from HuggingFace — network-gated.

Run with: UV_PROJECT_ENVIRONMENT=.venv-linux uv run pytest \
    tests/test_knowledge_integration.py -m integration --no-cov
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest


fitz = pytest.importorskip("fitz", reason="rag extra not installed (pymupdf)")
pytest.importorskip("sentence_transformers", reason="rag extra not installed")

from services.knowledge_base import KnowledgeBase  # noqa: E402


pytestmark = pytest.mark.integration


def _make_pdf(path: Path) -> None:
    """A tiny 2-page PDF with a distinctive, searchable fact."""
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text(
        (72, 72),
        "SAS Viya Deployment\n\n"
        "SAS Viya runs on Kubernetes and is supported on Red Hat OpenShift "
        "version 4.12 and later. The deployment uses a certified operator.",
        fontsize=11,
    )
    p2 = doc.new_page()
    p2.insert_text(
        (72, 72),
        "Data Management\n\nThe CAS engine handles in-memory analytics "
        "across the cluster nodes.",
        fontsize=11,
    )
    doc.save(str(path))
    doc.close()


def _wait_ready(kb: KnowledgeBase, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        docs = kb.summary()["docs"]
        if docs and all(d["status"] in ("ready", "failed") for d in docs):
            return
        time.sleep(0.5)
    raise AssertionError("KB ingestion did not finish in time")


def test_ingest_real_pdf_and_retrieve(tmp_path: Path) -> None:
    docs_dir = tmp_path / "sas_docs"
    docs_dir.mkdir()
    _make_pdf(docs_dir / "viya-admin.pdf")

    kb = KnowledgeBase(tmp_path / "storage", enabled=True)
    try:
        queued = kb.set_folder_and_scan(str(docs_dir))
        assert queued == 1
        _wait_ready(kb)

        summary = kb.summary()
        assert summary["doc_count"] == 1
        assert summary["chunk_count"] >= 1
        rec = summary["docs"][0]
        assert rec["status"] == "ready"
        assert rec["pages"] == 2

        # The distinctive fact must retrieve above the honesty threshold.
        hits = kb.search("Which OpenShift version does SAS Viya support?")
        assert hits, "expected a retrieval hit for a covered question"
        assert any("OpenShift" in h.text for h in hits)

        # An off-corpus question should return nothing (honesty guardrail),
        # letting the prompt defer to internal SAS sources instead of bluffing.
        off = kb.search("What is the price of a Tesla Model 3 in euros?")
        assert off == []

        # A rescan of the unchanged folder ingests nothing new.
        assert kb.set_folder_and_scan(str(docs_dir)) == 0
    finally:
        kb.stop()
