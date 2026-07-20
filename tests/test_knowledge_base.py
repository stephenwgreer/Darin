"""KnowledgeBase facade tests — ingest/persist/reload, delete, scan, guardrails.

No torch, no network: a deterministic FakeEmbedder is injected and
``parse_pdf`` is monkeypatched to return fabricated pages (so no real PDF is
needed). Ingestion is driven synchronously via ``_ingest_one`` to keep tests
deterministic; a separate test exercises the real background worker path.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import config
import services.knowledge_base as kb_mod
from services.knowledge_base import (
    ChunkMeta,
    FakeEmbedder,
    KnowledgeBase,
    ParsedPage,
)


class FakeClock:
    """Monotonic-ish injectable wall clock for reproducible ingested_at."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        self.now += 1.0
        return self.now


def _fake_pages(doc_marker: str, n_pages: int = 2) -> list[ParsedPage]:
    return [
        ParsedPage(
            page=i + 1,
            text=f"{doc_marker} page {i} " + " ".join(f"word{j}" for j in range(20)),
            headers=[f"{doc_marker}-section"],
        )
        for i in range(n_pages)
    ]


def _make_pdf(folder: Path, name: str, size: int = 100) -> Path:
    p = folder / name
    p.write_bytes(b"%PDF-1.4\n" + b"x" * size)
    return p


@pytest.fixture()
def patch_parse(monkeypatch: pytest.MonkeyPatch):
    """Patch parse_pdf to return fabricated pages keyed off the filename stem."""

    def fake_parse(path):  # noqa: ANN001
        return _fake_pages(Path(path).stem)

    monkeypatch.setattr(kb_mod, "parse_pdf", fake_parse)
    return fake_parse


def _kb(tmp_path: Path, **kw) -> KnowledgeBase:
    kw.setdefault("embedder", FakeEmbedder(dim=32))
    kw.setdefault("clock", FakeClock())
    return KnowledgeBase(tmp_path, **kw)


class TestConstruction:
    def test_directory_created(self, tmp_path: Path) -> None:
        kb = _kb(tmp_path)
        assert kb.directory == tmp_path / "knowledge"
        assert kb.directory.is_dir()

    def test_starts_empty(self, tmp_path: Path) -> None:
        kb = _kb(tmp_path)
        assert kb.is_empty
        assert kb.doc_count == 0
        assert kb.chunk_count == 0


class TestSearchGuardrails:
    def test_disabled_returns_empty(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path, enabled=False)
        kb._ingest_one(_make_pdf(tmp_path, "a.pdf"))
        assert kb.enabled is False
        assert kb.search("anything") == []

    def test_empty_returns_empty(self, tmp_path: Path) -> None:
        kb = _kb(tmp_path)
        assert kb.search("anything") == []

    def test_blank_query_returns_empty(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path)
        kb._ingest_one(_make_pdf(tmp_path, "a.pdf"))
        assert kb.search("   ") == []

    def test_min_score_filters_all_below_threshold(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path)
        kb._ingest_one(_make_pdf(tmp_path, "doc.pdf"))
        # A query with a floor of 1.01 can never be met -> empty (honesty guard).
        assert kb.search("doc page 0 word0", min_score=1.01) == []

    def test_exact_match_above_threshold(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path)
        kb._ingest_one(_make_pdf(tmp_path, "doc.pdf"))
        hits = kb.search("doc-section doc page 0 " + " ".join(f"word{j}" for j in range(20)))
        assert hits
        assert all(isinstance(h, ChunkMeta) for h in hits)


class TestFormatForPrompt:
    def test_empty_hits_empty_string(self, tmp_path: Path) -> None:
        kb = _kb(tmp_path)
        assert kb.format_for_prompt([]) == ""

    def test_header_and_citation(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path)
        kb._ingest_one(_make_pdf(tmp_path, "guide.pdf"))
        hits = kb.search("doc-section guide page 0 " + " ".join(f"word{j}" for j in range(20)))
        block = kb.format_for_prompt(hits)
        assert block.startswith("Relevant SAS documentation (cite the source doc + page):")
        assert "guide.pdf" in block
        assert "p." in block

    def test_context_budget_trimmed(self, tmp_path: Path, monkeypatch) -> None:
        kb = _kb(tmp_path)
        # Force a tiny budget so only the header + first entry fit.
        monkeypatch.setattr(config, "KB_CONTEXT_MAX_TOKENS", 15)
        big = " ".join(f"tok{i}" for i in range(200))
        hits = [
            ChunkMeta("d", 0, 1, "", big, len(big)),
            ChunkMeta("d", 1, 2, "", big, len(big)),
        ]
        kb._docs["d"] = kb_mod.DocRecord("d", "d.pdf", 1, 2, 0, 0.0, "ready")
        block = kb.format_for_prompt(hits)
        # Only one entry survives the budget (header + first chunk).
        assert block.count("[d.pdf p.") == 1


class TestIngestPersistReload:
    def test_round_trip_with_injected_clock(self, tmp_path: Path, patch_parse) -> None:
        clock = FakeClock(start=5000.0)
        kb = KnowledgeBase(tmp_path, embedder=FakeEmbedder(dim=32), clock=clock)
        kb._ingest_one(_make_pdf(tmp_path, "alpha.pdf"))

        assert kb.doc_count == 1
        assert kb.chunk_count > 0
        summary = kb.summary()
        assert summary["doc_count"] == 1
        rec = summary["docs"][0]
        assert rec["status"] == "ready"
        assert rec["ingested_at"] > 5000.0
        assert rec["pages"] == 2

        # Reload a fresh instance over the same dir with the SAME embedder name.
        kb2 = KnowledgeBase(tmp_path, embedder=FakeEmbedder(dim=32), clock=FakeClock())
        assert kb2.doc_count == 1
        assert kb2.chunk_count == kb.chunk_count
        hits = kb2.search("alpha-section alpha page 0 " + " ".join(f"word{j}" for j in range(20)))
        assert hits
        assert hits[0].doc_id == list(kb2._docs.keys())[0]

    def test_persisted_files_exist(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path)
        kb._ingest_one(_make_pdf(tmp_path, "a.pdf"))
        d = kb.directory
        assert (d / "index.npy").exists()
        assert (d / "chunks.jsonl").exists()
        assert (d / "manifest.json").exists()
        # chunks.jsonl row count matches the index matrix row count.
        rows = [ln for ln in (d / "chunks.jsonl").read_text().splitlines() if ln.strip()]
        matrix = np.load(d / "index.npy")
        assert len(rows) == matrix.shape[0] == kb.chunk_count


class TestDelete:
    def test_delete_drops_right_rows(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path)
        kb._ingest_one(_make_pdf(tmp_path, "one.pdf"))
        kb._ingest_one(_make_pdf(tmp_path, "two.pdf"))
        assert kb.doc_count == 2
        total = kb.chunk_count

        doc_ids = list(kb._docs.keys())
        one_id = next(d for d in doc_ids if kb._docs[d].filename == "one.pdf")
        one_chunks = kb._docs[one_id].chunk_count

        assert kb.delete(one_id) is True
        assert kb.doc_count == 1
        assert kb.chunk_count == total - one_chunks
        assert one_id not in kb._docs
        # Matrix rows renumbered: count still matches metas.
        assert kb._index.matrix.shape[0] == kb.chunk_count
        assert all(m.doc_id != one_id for m in kb._index.metas)

    def test_delete_missing_returns_false(self, tmp_path: Path) -> None:
        kb = _kb(tmp_path)
        assert kb.delete("nope") is False

    def test_delete_persists(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path)
        kb._ingest_one(_make_pdf(tmp_path, "one.pdf"))
        one_id = list(kb._docs.keys())[0]
        kb.delete(one_id)
        kb2 = _kb(tmp_path)
        assert kb2.doc_count == 0
        assert kb2.is_empty


class TestPreview:
    def test_preview_returns_chunks(self, tmp_path: Path, patch_parse) -> None:
        kb = _kb(tmp_path)
        kb._ingest_one(_make_pdf(tmp_path, "p.pdf"))
        doc_id = list(kb._docs.keys())[0]
        preview = kb.preview(doc_id, limit=2)
        assert 1 <= len(preview) <= 2
        assert set(preview[0].keys()) == {"chunk_id", "page", "section", "text"}

    def test_preview_missing_doc(self, tmp_path: Path) -> None:
        kb = _kb(tmp_path)
        assert kb.preview("nope") == []


class TestManifestMismatch:
    def test_embedder_change_clears_index(self, tmp_path: Path, patch_parse) -> None:
        kb = KnowledgeBase(
            tmp_path, embedder=FakeEmbedder(dim=32, name="embedder-A"), clock=FakeClock()
        )
        kb._ingest_one(_make_pdf(tmp_path, "a.pdf"))
        assert kb.chunk_count > 0

        # Reload with a DIFFERENT embedder identity -> stale index cleared.
        kb2 = KnowledgeBase(
            tmp_path, embedder=FakeEmbedder(dim=32, name="embedder-B"), clock=FakeClock()
        )
        assert kb2.is_empty
        assert kb2.doc_count == 0

    def test_same_embedder_keeps_index(self, tmp_path: Path, patch_parse) -> None:
        kb = KnowledgeBase(
            tmp_path, embedder=FakeEmbedder(dim=32, name="same"), clock=FakeClock()
        )
        kb._ingest_one(_make_pdf(tmp_path, "a.pdf"))
        kb2 = KnowledgeBase(
            tmp_path, embedder=FakeEmbedder(dim=32, name="same"), clock=FakeClock()
        )
        assert not kb2.is_empty
        assert kb2.doc_count == 1

    def test_fallback_index_survives_restart(self, tmp_path: Path, patch_parse) -> None:
        # Regression: primary model unloadable, so the index was built (and its
        # manifest identity recorded) under KB_EMBED_MODEL_FALLBACK. On restart
        # the real embedder is not yet constructed, so _load() sees the primary
        # as the "current" name. The persisted fallback name must be accepted as
        # a valid identity for the current config, NOT treated as a model change
        # that wipes the corpus on every restart.
        kb = KnowledgeBase(
            tmp_path,
            embedder=FakeEmbedder(dim=32, name=config.KB_EMBED_MODEL_FALLBACK),
            clock=FakeClock(),
        )
        kb._ingest_one(_make_pdf(tmp_path, "a.pdf"))
        assert kb.chunk_count > 0

        # Reload the way startup does: no injected embedder (constructed lazily).
        kb2 = KnowledgeBase(tmp_path, clock=FakeClock())
        assert not kb2.is_empty
        assert kb2.doc_count == 1
        # The persisted identity is preserved, so the next _persist() won't drift.
        assert kb2.summary()["embed_model"] == config.KB_EMBED_MODEL_FALLBACK

    def test_primary_index_survives_restart(self, tmp_path: Path, patch_parse) -> None:
        # The mirror case: index built under the primary model name survives a
        # lazy-embedder restart too (stored == KB_EMBED_MODEL == optimistic name).
        kb = KnowledgeBase(
            tmp_path,
            embedder=FakeEmbedder(dim=32, name=config.KB_EMBED_MODEL),
            clock=FakeClock(),
        )
        kb._ingest_one(_make_pdf(tmp_path, "a.pdf"))
        kb2 = KnowledgeBase(tmp_path, clock=FakeClock())
        assert not kb2.is_empty
        assert kb2.doc_count == 1

    def test_unknown_embedder_still_clears_on_restart(
        self, tmp_path: Path, patch_parse
    ) -> None:
        # A genuinely foreign embedder identity (neither primary nor fallback)
        # must still clear the stale index even on a lazy-embedder restart.
        kb = KnowledgeBase(
            tmp_path, embedder=FakeEmbedder(dim=32, name="some-other-model"), clock=FakeClock()
        )
        kb._ingest_one(_make_pdf(tmp_path, "a.pdf"))
        assert kb.chunk_count > 0

        kb2 = KnowledgeBase(tmp_path, clock=FakeClock())
        assert kb2.is_empty
        assert kb2.doc_count == 0


class TestFolderScan:
    def test_scan_queues_new_docs(self, tmp_path: Path, patch_parse) -> None:
        docs = tmp_path / "corpus"
        docs.mkdir()
        _make_pdf(docs, "one.pdf")
        _make_pdf(docs, "two.pdf")
        kb = _kb(tmp_path)
        queued = kb.set_folder_and_scan(str(docs))
        assert queued == 2
        assert kb.docs_folder == str(docs)
        # Both docs are registered (queued status before the worker runs).
        assert kb.doc_count == 2

    def test_scan_skips_already_ingested(self, tmp_path: Path, patch_parse) -> None:
        docs = tmp_path / "corpus"
        docs.mkdir()
        pdf = _make_pdf(docs, "one.pdf")
        kb = _kb(tmp_path)
        # Ingest it directly so its DocRecord is "ready" with a matching size.
        kb._ingest_one(pdf)
        assert kb.doc_count == 1
        # Re-scan: the unchanged, ready doc is a diff no-op.
        queued = kb.set_folder_and_scan(str(docs))
        assert queued == 0

    def test_scan_requeues_changed_doc(self, tmp_path: Path, patch_parse) -> None:
        docs = tmp_path / "corpus"
        docs.mkdir()
        pdf = _make_pdf(docs, "one.pdf", size=100)
        kb = _kb(tmp_path)
        kb._ingest_one(pdf)
        # Change the file size -> diff detects it as changed and requeues.
        pdf.write_bytes(b"%PDF-1.4\n" + b"y" * 500)
        queued = kb.set_folder_and_scan(str(docs))
        assert queued == 1

    def test_scan_missing_folder(self, tmp_path: Path) -> None:
        kb = _kb(tmp_path)
        assert kb.set_folder_and_scan(str(tmp_path / "does-not-exist")) == 0


class TestBackgroundWorker:
    def test_worker_ingests_and_persists(self, tmp_path: Path, patch_parse) -> None:
        docs = tmp_path / "corpus"
        docs.mkdir()
        _make_pdf(docs, "bg.pdf")
        events: list[dict] = []
        kb = KnowledgeBase(
            tmp_path,
            embedder=FakeEmbedder(dim=32),
            clock=FakeClock(),
            on_progress=events.append,
        )
        kb.set_folder_and_scan(str(docs))
        assert kb.wait_idle(timeout=10.0)
        # Give the worker a beat to finalize the last doc after the queue drains.
        import time as _t

        for _ in range(200):
            if kb.doc_count and kb.summary()["docs"][0]["status"] == "ready":
                break
            _t.sleep(0.02)
        kb.stop()

        assert kb.doc_count == 1
        assert kb.chunk_count > 0
        statuses = [e["status"] for e in events]
        assert "parsing" in statuses
        assert "ready" in statuses

    def test_worker_survives_bad_pdf(self, tmp_path: Path, monkeypatch) -> None:
        docs = tmp_path / "corpus"
        docs.mkdir()
        _make_pdf(docs, "bad.pdf")

        def boom(path):  # noqa: ANN001
            raise RuntimeError("parse exploded")

        monkeypatch.setattr(kb_mod, "parse_pdf", boom)
        events: list[dict] = []
        kb = KnowledgeBase(
            tmp_path,
            embedder=FakeEmbedder(dim=32),
            clock=FakeClock(),
            on_progress=events.append,
        )
        kb.set_folder_and_scan(str(docs))
        import time as _t

        for _ in range(200):
            if any(e["status"] == "failed" for e in events):
                break
            _t.sleep(0.02)
        kb.stop()

        assert any(e["status"] == "failed" for e in events)
        # The doc is marked failed but the worker did not die.
        assert kb.summary()["docs"][0]["status"] == "failed"
