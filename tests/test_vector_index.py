"""VectorIndex tests — top-k order, exact recall, remove/renumber. No torch."""

from __future__ import annotations

import numpy as np

from services.knowledge_base import ChunkMeta, FakeEmbedder, VectorIndex


def _meta(doc_id: str, chunk_id: int, text: str) -> ChunkMeta:
    return ChunkMeta(
        doc_id=doc_id,
        chunk_id=chunk_id,
        page=chunk_id + 1,
        section="",
        text=text,
        char_len=len(text),
    )


def _build(texts: list[tuple[str, str]]) -> tuple[VectorIndex, FakeEmbedder]:
    """texts: list of (doc_id, text). Returns a populated index + the embedder."""
    emb = FakeEmbedder(dim=48)
    vecs = emb.encode([t for _, t in texts])
    metas = [_meta(doc_id, i, text) for i, (doc_id, text) in enumerate(texts)]
    index = VectorIndex(emb.dim)
    index.add(vecs, metas)
    return index, emb


class TestSearch:
    def test_exact_match_recall(self) -> None:
        index, emb = _build(
            [
                ("d1", "kubernetes deployment guide"),
                ("d1", "database backup schedule"),
                ("d2", "network firewall rules"),
            ]
        )
        q = emb.encode(["kubernetes deployment guide"])[0]
        results = index.search(q, k=3)
        # The exact-text chunk is the top hit with ~1.0 cosine.
        top_score, top_meta = results[0]
        assert top_meta.text == "kubernetes deployment guide"
        assert top_score > 0.99

    def test_topk_descending_order(self) -> None:
        index, emb = _build([("d", f"chunk number {i}") for i in range(10)])
        q = emb.encode(["chunk number 4"])[0]
        results = index.search(q, k=5)
        scores = [s for s, _ in results]
        assert scores == sorted(scores, reverse=True)
        assert len(results) == 5

    def test_k_larger_than_index(self) -> None:
        index, emb = _build([("d", "only one")])
        results = index.search(emb.encode(["only one"])[0], k=10)
        assert len(results) == 1

    def test_empty_index_returns_empty(self) -> None:
        index = VectorIndex(8)
        assert index.search(np.ones(8, dtype=np.float32), k=4) == []

    def test_zero_k_returns_empty(self) -> None:
        index, emb = _build([("d", "text")])
        assert index.search(emb.encode(["text"])[0], k=0) == []


class TestRemoveDoc:
    def test_remove_drops_right_rows_and_renumbers(self) -> None:
        index, emb = _build(
            [
                ("d1", "alpha one"),
                ("d2", "beta two"),
                ("d1", "alpha three"),
                ("d2", "beta four"),
            ]
        )
        assert index.size == 4
        removed = index.remove_doc("d1")
        assert removed == 2
        assert index.size == 2
        # Only d2 chunks survive, and the matrix row count matches the meta count.
        assert {m.doc_id for m in index.metas} == {"d2"}
        assert index.matrix.shape[0] == 2

        # Surviving rows still search correctly (row i <-> meta i preserved).
        q = emb.encode(["beta four"])[0]
        top_score, top_meta = index.search(q, k=1)[0]
        assert top_meta.text == "beta four"
        assert top_score > 0.99

    def test_remove_missing_doc_noop(self) -> None:
        index, _ = _build([("d1", "x")])
        assert index.remove_doc("nope") == 0
        assert index.size == 1

    def test_remove_all_leaves_empty_matrix(self) -> None:
        index, _ = _build([("d1", "x"), ("d1", "y")])
        index.remove_doc("d1")
        assert index.is_empty
        assert index.matrix.shape == (0, index.dim)


class TestAddValidation:
    def test_dim_mismatch_raises(self) -> None:
        index = VectorIndex(4)
        bad = np.ones((1, 8), dtype=np.float32)
        try:
            index.add(bad, [_meta("d", 0, "t")])
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError on dim mismatch")

    def test_count_mismatch_raises(self) -> None:
        index = VectorIndex(4)
        vecs = np.ones((2, 4), dtype=np.float32)
        try:
            index.add(vecs, [_meta("d", 0, "t")])
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError on count mismatch")

    def test_stored_vectors_are_normalized(self) -> None:
        index = VectorIndex(4)
        vecs = np.array([[3.0, 4.0, 0.0, 0.0]], dtype=np.float32)  # norm 5
        index.add(vecs, [_meta("d", 0, "t")])
        row = index.matrix[0]
        assert abs(float(np.linalg.norm(row)) - 1.0) < 1e-6
