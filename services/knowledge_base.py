"""Local SAS Viya knowledge base — retrieval-augmented grounding over PDFs.

Ingests public Viya PDFs from a local folder, vectorizes them on-device with
``sentence-transformers``, and retrieves the most relevant passages for the
reactive / Ask / Auto-Answer lanes (never the latency-critical watcher). All
data stays on the machine.

Storage mirrors :mod:`services.context_pack` (a subdir under ``storage_path``);
the background ingest worker mirrors :mod:`services.watcher` (daemon thread +
lock + Event, and a "must never die" try/except).

Heavy dependencies (``fitz`` / PyMuPDF and ``sentence_transformers`` / torch)
are the optional ``rag`` extra. They are imported **lazily inside functions**,
never at module top, so ``import services.knowledge_base`` succeeds without the
extra; a clear "install darin[rag]" error is raised only when parsing or
embedding is actually invoked.

On-disk layout under ``<storage_path>/knowledge/``:
- ``index.npy``    — float32 (N x dim), pre-L2-normalized, row i <-> chunk i.
- ``chunks.jsonl`` — one ``ChunkMeta`` per row, row i <-> matrix row i.
- ``manifest.json``— ``{embedder, dim, version, docs:[DocRecord]}``. The embedder
  identity is recorded so a model change forces a reindex rather than mixing
  embedding spaces.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
from loguru import logger

import config
from services.context_pack import estimate_tokens


# Raised when a rag-only code path runs without the optional extra installed.
RAG_INSTALL_HINT = "install the optional extra: uv sync --extra rag (darin[rag])"


# ----------------------------------------------------------------------------
# Data shapes
# ----------------------------------------------------------------------------


@dataclass
class ChunkMeta:
    """One retrievable passage. Row i of the vector matrix <-> chunk i."""

    doc_id: str
    chunk_id: int
    page: int
    section: str
    text: str
    char_len: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> ChunkMeta:
        return cls(
            doc_id=str(raw["doc_id"]),
            chunk_id=int(raw["chunk_id"]),
            page=int(raw["page"]),
            section=str(raw.get("section", "")),
            text=str(raw.get("text", "")),
            char_len=int(raw.get("char_len", len(str(raw.get("text", ""))))),
        )


@dataclass
class DocRecord:
    """A single ingested document as tracked in the manifest."""

    doc_id: str
    filename: str
    pages: int
    chunk_count: int
    size_bytes: int
    ingested_at: float
    status: str  # "queued" | "parsing" | "embedding" | "ready" | "failed"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> DocRecord:
        return cls(
            doc_id=str(raw["doc_id"]),
            filename=str(raw.get("filename", "")),
            pages=int(raw.get("pages", 0)),
            chunk_count=int(raw.get("chunk_count", 0)),
            size_bytes=int(raw.get("size_bytes", 0)),
            ingested_at=float(raw.get("ingested_at", 0.0)),
            status=str(raw.get("status", "ready")),
        )


@dataclass
class ParsedPage:
    """One parsed PDF page — the input to pure chunking.

    ``headers`` is the ordered section-header path in effect on this page
    (e.g. ``["Deployment", "Kubernetes"]``). Constructable in tests without a
    real PDF, which is the whole point of splitting parse from chunk.
    """

    page: int
    text: str
    headers: list[str] = field(default_factory=list)


@dataclass
class RawChunk:
    """A pre-embedding chunk emitted by :func:`chunk_pages`."""

    page: int
    section: str
    text: str


# ----------------------------------------------------------------------------
# Pure chunking (no PDF, no torch — fully unit-testable)
# ----------------------------------------------------------------------------


def _coerce_page(raw: ParsedPage | dict) -> ParsedPage:
    if isinstance(raw, ParsedPage):
        return raw
    return ParsedPage(
        page=int(raw.get("page", 0)),
        text=str(raw.get("text", "")),
        headers=list(raw.get("headers", []) or []),
    )


def _section_path(headers: Sequence[str]) -> str:
    """Render the section-header path prepended to each chunk: ``# H1 > H2``."""
    parts = [h.strip() for h in headers if h and h.strip()]
    return "# " + " > ".join(parts) if parts else ""


def chunk_pages(parsed_pages: Sequence[ParsedPage | dict]) -> list[RawChunk]:
    """Header-aware chunking over already-parsed pages. Pure: no I/O.

    Splits each page's text into ``~config.KB_CHUNK_TOKENS``-token windows with
    ``~config.KB_CHUNK_OVERLAP_FRAC`` word overlap, and prepends the page's
    section-header path (``"# H1 > H2\\n\\n"``) to each chunk's stored text so
    the header travels with the passage into the prompt.

    Chunking is per-page (page numbers are load-bearing for citation), so a
    chunk never straddles a page boundary.
    """
    target_tokens = max(1, config.KB_CHUNK_TOKENS)
    # estimate_tokens ~= words * 1.3, so words-per-chunk ~= target / 1.3.
    words_per_chunk = max(1, int(round(target_tokens / 1.3)))
    overlap_words = max(0, int(round(words_per_chunk * config.KB_CHUNK_OVERLAP_FRAC)))
    # Guard: overlap must be strictly less than the window or we never advance.
    step = max(1, words_per_chunk - overlap_words)

    chunks: list[RawChunk] = []
    for raw in parsed_pages:
        page = _coerce_page(raw)
        words = page.text.split()
        if not words:
            continue
        section = _section_path(page.headers)
        prefix = f"{section}\n\n" if section else ""

        start = 0
        while start < len(words):
            window = words[start : start + words_per_chunk]
            body = " ".join(window)
            chunks.append(RawChunk(page=page.page, section=section, text=prefix + body))
            if start + words_per_chunk >= len(words):
                break
            start += step

    return chunks


# ----------------------------------------------------------------------------
# PDF parsing (the ONLY fitz-touching code; lazily imported)
# ----------------------------------------------------------------------------


def parse_pdf(path: str | Path) -> list[ParsedPage]:
    """Parse a PDF into :class:`ParsedPage` list. Lazily imports ``fitz``.

    Header detection is heuristic: a line noticeably larger than the page's
    median font size (and short) becomes the current H1/H2 path. This keeps
    chunking header-aware without a full layout model. The only rag-extra
    dependency in this module lives here.
    """
    try:
        import fitz  # type: ignore[import-not-found]  # PyMuPDF, optional rag extra
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(f"PDF parsing requires PyMuPDF — {RAG_INSTALL_HINT}") from e

    pages: list[ParsedPage] = []
    headers: list[str] = []  # rolling H1/H2 path carried across pages
    with fitz.open(str(path)) as doc:
        for page_index, page in enumerate(doc):
            data = page.get_text("dict")
            sizes: list[float] = []
            for block in data.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        sizes.append(float(span.get("size", 0.0)))
            median = float(np.median(sizes)) if sizes else 0.0

            body_parts: list[str] = []
            for block in data.get("blocks", []):
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    line_text = "".join(s.get("text", "") for s in spans).strip()
                    if not line_text:
                        continue
                    line_size = max((float(s.get("size", 0.0)) for s in spans), default=0.0)
                    is_header = (
                        median > 0
                        and line_size >= median * 1.2
                        and len(line_text) <= 80
                        and len(line_text.split()) <= 12
                    )
                    if is_header:
                        # H1 for the biggest text, else H2 under it.
                        if line_size >= median * 1.6:
                            headers = [line_text]
                        else:
                            headers = headers[:1] + [line_text]
                    else:
                        body_parts.append(line_text)

            text = " ".join(body_parts)
            pages.append(ParsedPage(page=page_index + 1, text=text, headers=list(headers)))
    return pages


# ----------------------------------------------------------------------------
# Embedders
# ----------------------------------------------------------------------------


@runtime_checkable
class Embedder(Protocol):
    """Turns texts into L2-normalized float32 vectors."""

    @property
    def dim(self) -> int: ...

    def encode(self, texts: list[str]) -> np.ndarray: ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """L2-normalize rows of a float32 matrix; zero rows stay zero (safe)."""
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (matrix / norms).astype(np.float32)


class FakeEmbedder:
    """Deterministic hash->vector embedder for tests. No torch, no network.

    Identical text always yields the identical unit vector, so exact-match
    recall and persistence round-trips are reproducible without a real model.
    """

    def __init__(self, dim: int = 32, *, name: str = "fake-embedder") -> None:
        self._dim = dim
        self._name = name

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def name(self) -> str:
        return self._name

    def _one(self, text: str) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        # Hash each token into the vector — stable, order-independent-ish bag.
        for token in text.lower().split() or [text.lower()]:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self._dim
            weight = (digest[4] / 255.0) + 0.1
            vec[idx] += weight
        if not np.any(vec):
            vec[0] = 1.0
        return vec

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._dim), dtype=np.float32)
        raw = np.stack([self._one(t) for t in texts]).astype(np.float32)
        return _normalize(raw)


class SentenceTransformerEmbedder:
    """Real embedder — lazy-loads ``config.KB_EMBED_MODEL`` once (fallback on failure)."""

    def __init__(self, model_name: str = config.KB_EMBED_MODEL) -> None:
        self._model_name = model_name
        self._model = None  # loaded on first encode / warmup
        self._loaded_name = model_name
        self._dim: int | None = None

    @property
    def name(self) -> str:
        return self._loaded_name

    def load(self) -> None:
        """Load the model once. Falls back to KB_EMBED_MODEL_FALLBACK on failure."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import (  # type: ignore[import-not-found]
                SentenceTransformer,
            )
        except ImportError as e:  # pragma: no cover - only without the rag extra
            raise RuntimeError(
                f"Embedding requires sentence-transformers — {RAG_INSTALL_HINT}"
            ) from e

        name = self._model_name
        try:
            model = SentenceTransformer(name)
        except Exception as e:  # noqa: BLE001 - any load failure -> fallback
            fallback = config.KB_EMBED_MODEL_FALLBACK
            logger.warning(
                "Embed model load failed, using fallback",
                model=name,
                fallback=fallback,
                error=str(e),
            )
            model = SentenceTransformer(fallback)
            name = fallback

        self._model = model
        self._loaded_name = name
        self._dim = int(model.get_sentence_embedding_dimension())
        logger.info("Embed model loaded", model=name, dim=self._dim)

    @property
    def dim(self) -> int:
        if self._dim is None:
            self.load()
        assert self._dim is not None
        return self._dim

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        self.load()
        assert self._model is not None
        vecs = self._model.encode(
            texts,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)


# ----------------------------------------------------------------------------
# In-memory vector index
# ----------------------------------------------------------------------------


class VectorIndex:
    """Brute-force cosine index: pre-normalized float32 matrix + ChunkMeta list.

    Vectors are stored L2-normalized so cosine similarity is a plain matrix @
    query dot product. Row i of the matrix corresponds to ``self.metas[i]``.
    """

    def __init__(self, dim: int) -> None:
        self._dim = dim
        self._matrix = np.zeros((0, dim), dtype=np.float32)
        self._metas: list[ChunkMeta] = []

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def size(self) -> int:
        return len(self._metas)

    @property
    def is_empty(self) -> bool:
        return not self._metas

    @property
    def matrix(self) -> np.ndarray:
        return self._matrix

    @property
    def metas(self) -> list[ChunkMeta]:
        return self._metas

    def add(self, vectors: np.ndarray, metas: list[ChunkMeta]) -> None:
        """Append rows. ``vectors`` must be (len(metas) x dim); it is normalized."""
        if len(metas) == 0:
            return
        vectors = _normalize(np.asarray(vectors, dtype=np.float32))
        if vectors.shape[1] != self._dim:
            raise ValueError(f"vector dim {vectors.shape[1]} != index dim {self._dim}")
        if vectors.shape[0] != len(metas):
            raise ValueError("vector count != meta count")
        self._matrix = np.vstack([self._matrix, vectors]) if self.size else vectors.copy()
        self._metas.extend(metas)

    def remove_doc(self, doc_id: str) -> int:
        """Drop every row for ``doc_id`` and renumber the matrix. Returns count."""
        keep = [i for i, m in enumerate(self._metas) if m.doc_id != doc_id]
        removed = self.size - len(keep)
        if removed == 0:
            return 0
        self._matrix = self._matrix[keep] if keep else np.zeros((0, self._dim), dtype=np.float32)
        self._metas = [self._metas[i] for i in keep]
        return removed

    def search(self, qvec: np.ndarray, k: int) -> list[tuple[float, ChunkMeta]]:
        """Top-k by cosine (matrix @ qvec), highest score first."""
        if self.is_empty or k <= 0:
            return []
        q = _normalize(np.asarray(qvec, dtype=np.float32)).reshape(-1)
        scores = self._matrix @ q
        k = min(k, scores.shape[0])
        # argpartition finds the top-k cheaply; then sort just those descending.
        top = np.argpartition(scores, -k)[-k:]
        top = top[np.argsort(scores[top])[::-1]]
        return [(float(scores[i]), self._metas[i]) for i in top]

    def replace(self, matrix: np.ndarray, metas: list[ChunkMeta]) -> None:
        """Replace the whole index (used on load)."""
        matrix = np.asarray(matrix, dtype=np.float32)
        if matrix.size == 0:
            self._matrix = np.zeros((0, self._dim), dtype=np.float32)
            self._metas = []
            return
        if matrix.shape[1] != self._dim:
            raise ValueError(f"matrix dim {matrix.shape[1]} != index dim {self._dim}")
        self._matrix = matrix
        self._metas = list(metas)

    def clear(self) -> None:
        self._matrix = np.zeros((0, self._dim), dtype=np.float32)
        self._metas = []


# ----------------------------------------------------------------------------
# KnowledgeBase facade
# ----------------------------------------------------------------------------


def _doc_id_for(filename: str) -> str:
    """Stable, filesystem-safe doc id derived from the filename."""
    stem = Path(filename).stem
    slug = "".join(c if c.isalnum() else "-" for c in stem.lower()).strip("-")
    slug = slug[:48] or "doc"
    suffix = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{suffix}"


class KnowledgeBase:
    """Facade: owns the embedder (lazy), vector index, doc registry, and worker.

    The background ingest worker is a single daemon thread (serialized
    single-writer). All index/persistence mutation happens under ``self._lock``.
    Like the watcher, the worker's top-level loop catches everything so it can
    never die.
    """

    def __init__(
        self,
        storage_path: str | Path,
        *,
        enabled: bool = config.KB_ENABLED_DEFAULT,
        docs_folder: str = "",
        on_progress: Callable[[dict], None] | None = None,
        embedder: Embedder | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._dir = Path(storage_path) / "knowledge"
        self._dir.mkdir(parents=True, exist_ok=True)
        self.enabled = enabled
        self.docs_folder = docs_folder
        self._on_progress = on_progress
        self._clock = clock  # wall-clock for ingested_at (injectable in tests)

        # Embedder: injected (tests) or lazily constructed real one.
        self._embedder = embedder
        self._embed_lock = threading.Lock()

        self._lock = threading.RLock()
        self._index: VectorIndex | None = None
        self._docs: dict[str, DocRecord] = {}
        self._embedder_name: str = ""  # embedder identity recorded in the manifest

        # Ingest worker: queue + daemon thread + wake/stop events.
        self._queue: deque[Path] = deque()
        self._wake = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._load()
        logger.info(
            "Knowledge base ready",
            path=str(self._dir),
            enabled=enabled,
            docs=len(self._docs),
            chunks=self._index.size if self._index else 0,
        )

    # ----- paths -----

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def _index_path(self) -> Path:
        return self._dir / "index.npy"

    @property
    def _chunks_path(self) -> Path:
        return self._dir / "chunks.jsonl"

    @property
    def _manifest_path(self) -> Path:
        return self._dir / "manifest.json"

    # ----- embedder -----

    def _get_embedder(self) -> Embedder:
        """Return the embedder, constructing the real one lazily under a lock."""
        with self._embed_lock:
            if self._embedder is None:
                self._embedder = SentenceTransformerEmbedder()
            return self._embedder

    def _current_embedder_name(self) -> str:
        emb = self._embedder
        if emb is None:
            # Real embedder not yet constructed — its identity is the config model.
            return config.KB_EMBED_MODEL
        return getattr(emb, "name", type(emb).__name__)

    def warmup(self) -> None:
        """Load the embedder once (fire-and-forget at startup). Fails soft."""
        try:
            emb = self._get_embedder()
            load = getattr(emb, "load", None)
            if callable(load):
                load()
            _ = emb.dim
        except Exception as e:  # noqa: BLE001 - warmup must never crash startup
            logger.warning("Knowledge base warmup failed: {}", e)

    # ----- state -----

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return self._index is None or self._index.is_empty

    @property
    def doc_count(self) -> int:
        with self._lock:
            return len(self._docs)

    @property
    def chunk_count(self) -> int:
        with self._lock:
            return self._index.size if self._index else 0

    # ----- persistence -----

    def _atomic_write_bytes(self, path: Path, write: Callable[[Path], None]) -> None:
        """Write via a .tmp sibling + os.replace. Caller holds the lock."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        write(tmp)
        os.replace(tmp, path)

    def _load(self) -> None:
        """Load index + chunks + manifest. Empty/mismatched -> fresh empty index."""
        with self._lock:
            manifest = self._read_manifest()
            self._docs = {d.doc_id: d for d in manifest.get("docs", [])}
            stored_embedder = manifest.get("embedder", "")
            dim = int(manifest.get("dim", 0))

            current_name = self._current_embedder_name()
            # Adopt the persisted identity when it is a valid identity for the
            # current config. The real embedder is loaded lazily, so at reload
            # time _current_embedder_name() optimistically reports the primary
            # model even when the primary is unloadable and the fallback was
            # what actually produced this index. Both KB_EMBED_MODEL and
            # KB_EMBED_MODEL_FALLBACK are legitimate identities for the current
            # config; treating the fallback as a "change" would wipe the corpus
            # on every restart while the primary stays unavailable.
            stale = stored_embedder != current_name
            if stale and self._embedder is None:
                stale = stored_embedder not in (
                    config.KB_EMBED_MODEL,
                    config.KB_EMBED_MODEL_FALLBACK,
                )
            if stored_embedder and not stale:
                current_name = stored_embedder
            self._embedder_name = current_name

            # Embedder-space mismatch (or first run / no manifest): do NOT mix
            # embedding spaces — start from an empty index flagged for reindex.
            if not manifest or stale or dim <= 0:
                if manifest and stored_embedder and stale:
                    logger.warning(
                        "KB embedder changed — index is stale, clearing for reindex",
                        stored=stored_embedder,
                        current=current_name,
                    )
                    self._docs = {}
                self._index = None
                return

            metas = self._read_chunks()
            matrix = self._read_index(dim)
            index = VectorIndex(dim)
            if matrix.shape[0] == len(metas) and len(metas) > 0:
                index.replace(matrix, metas)
            elif len(metas) != 0 or matrix.shape[0] != 0:
                logger.warning(
                    "KB index/chunks row mismatch — clearing",
                    matrix_rows=int(matrix.shape[0]),
                    chunk_rows=len(metas),
                )
                self._docs = {}
            self._index = index

    def _read_manifest(self) -> dict:
        if not self._manifest_path.exists():
            return {}
        try:
            raw = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("KB manifest unreadable, treating as empty", error=str(e))
            return {}
        raw["docs"] = [DocRecord.from_dict(d) for d in raw.get("docs", [])]
        return raw

    def _read_chunks(self) -> list[ChunkMeta]:
        if not self._chunks_path.exists():
            return []
        metas: list[ChunkMeta] = []
        try:
            for line in self._chunks_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    metas.append(ChunkMeta.from_dict(json.loads(line)))
        except (OSError, json.JSONDecodeError, KeyError) as e:
            logger.warning("KB chunks unreadable, treating as empty", error=str(e))
            return []
        return metas

    def _read_index(self, dim: int) -> np.ndarray:
        if not self._index_path.exists():
            return np.zeros((0, dim), dtype=np.float32)
        try:
            matrix = np.load(self._index_path)
        except (OSError, ValueError) as e:
            logger.warning("KB index unreadable, treating as empty", error=str(e))
            return np.zeros((0, dim), dtype=np.float32)
        return np.asarray(matrix, dtype=np.float32)

    def _persist(self) -> None:
        """Atomically write index + chunks + manifest. Caller holds the lock."""
        index = self._index
        dim = index.dim if index else 0
        matrix = index.matrix if index else np.zeros((0, dim), dtype=np.float32)
        metas = index.metas if index else []

        # np.save appends ".npy" unless the path already ends in it — write
        # through an explicit file handle so the ".tmp" sibling name is honored.
        def _write_index(p: Path) -> None:
            with p.open("wb") as fh:
                np.save(fh, matrix)

        self._atomic_write_bytes(self._index_path, _write_index)

        def _write_chunks(p: Path) -> None:
            with p.open("w", encoding="utf-8") as fh:
                for meta in metas:
                    fh.write(json.dumps(meta.to_dict(), ensure_ascii=False) + "\n")

        self._atomic_write_bytes(self._chunks_path, _write_chunks)

        manifest = {
            "embedder": self._embedder_name or self._current_embedder_name(),
            "dim": dim,
            "version": config.KB_INDEX_VERSION,
            "docs": [d.to_dict() for d in self._docs.values()],
        }

        def _write_manifest(p: Path) -> None:
            p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        self._atomic_write_bytes(self._manifest_path, _write_manifest)

    # ----- query -----

    def search(
        self,
        query: str,
        k: int = config.KB_TOP_K,
        min_score: float = config.KB_MIN_SIMILARITY,
    ) -> list[ChunkMeta]:
        """Retrieve up to ``k`` chunks above ``min_score``.

        Returns ``[]`` when disabled, empty, or every hit is below threshold —
        that empty result is what triggers the prompt's honesty guardrail.
        """
        if not self.enabled or self.is_empty or not query.strip():
            return []
        started = time.perf_counter()
        try:
            qvec = self._get_embedder().encode([query])
        except Exception as e:  # noqa: BLE001 - a search failure must never crash the lane
            logger.warning("KB search embed failed: {}", e)
            return []
        with self._lock:
            index = self._index
            if index is None or index.is_empty:
                return []
            scored = index.search(qvec[0], k)
        hits = [meta for score, meta in scored if score >= min_score]
        retrieval_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "KB retrieval",
            retrieval_ms=round(retrieval_ms, 2),
            hit_count=len(hits),
            query_chars=len(query),
        )
        return hits

    def format_for_prompt(self, hits: list[ChunkMeta]) -> str:
        """Render hits into a transcript block, trimmed to KB_CONTEXT_MAX_TOKENS."""
        if not hits:
            return ""
        header = "Relevant SAS documentation (cite the source doc + page):"
        lines = [header]
        budget = config.KB_CONTEXT_MAX_TOKENS
        used = estimate_tokens(header)
        for meta in hits:
            filename = self._docs[meta.doc_id].filename if meta.doc_id in self._docs else meta.doc_id
            entry = f"\n[{filename} p.{meta.page}] {meta.text}"
            cost = estimate_tokens(entry)
            if used + cost > budget and len(lines) > 1:
                break
            lines.append(entry)
            used += cost
        return "".join(lines)

    # ----- registry / summary -----

    def summary(self) -> dict:
        with self._lock:
            total_bytes = sum(d.size_bytes for d in self._docs.values())
            docs = [d.to_dict() for d in self._docs.values()]
            chunk_count = self._index.size if self._index else 0
        return {
            "enabled": self.enabled,
            "docs_folder": self.docs_folder,
            "doc_count": len(docs),
            "chunk_count": chunk_count,
            "total_bytes": total_bytes,
            "embed_model": self._embedder_name or self._current_embedder_name(),
            "docs": docs,
        }

    def preview(self, doc_id: str, limit: int = 5) -> list[dict]:
        """Return up to ``limit`` chunk previews for a doc."""
        with self._lock:
            if self._index is None:
                return []
            out: list[dict] = []
            for meta in self._index.metas:
                if meta.doc_id != doc_id:
                    continue
                out.append(
                    {
                        "chunk_id": meta.chunk_id,
                        "page": meta.page,
                        "section": meta.section,
                        "text": meta.text,
                    }
                )
                if len(out) >= limit:
                    break
            return out

    # ----- folder scan + ingest -----

    def set_folder_and_scan(self, folder: str) -> int:
        """Set the docs folder and enqueue new/changed PDFs. Returns queued count."""
        self.docs_folder = folder
        return self._scan(folder)

    def _scan(self, folder: str) -> int:
        """Diff folder PDFs against the manifest, enqueue the new ones."""
        base = Path(folder)
        if not base.is_dir():
            logger.warning("KB scan folder missing", folder=folder)
            return 0
        pdfs = sorted(p for p in base.glob("*.pdf") if p.is_file())
        queued = 0
        for pdf in pdfs:
            doc_id = _doc_id_for(pdf.name)
            with self._lock:
                existing = self._docs.get(doc_id)
                size = pdf.stat().st_size
                # Already ingested and unchanged -> skip.
                if existing and existing.status == "ready" and existing.size_bytes == size:
                    continue
                self._docs[doc_id] = DocRecord(
                    doc_id=doc_id,
                    filename=pdf.name,
                    pages=0,
                    chunk_count=0,
                    size_bytes=size,
                    ingested_at=self._clock(),
                    status="queued",
                )
            self.enqueue_ingest(pdf)
            queued += 1
        logger.info("KB folder scanned", folder=folder, found=len(pdfs), queued=queued)
        return queued

    def enqueue_ingest(self, path: str | Path) -> None:
        """Queue a PDF for background ingestion and ensure the worker runs."""
        self._queue.append(Path(path))
        self._ensure_worker()
        self._wake.set()

    def _ensure_worker(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="kb-ingest", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Serialized single-writer ingest loop. Must never die."""
        while not self._stop_event.is_set():
            self._wake.wait(timeout=1.0)
            if self._stop_event.is_set():
                return
            self._wake.clear()
            while self._queue and not self._stop_event.is_set():
                path = self._queue.popleft()
                try:
                    self._ingest_one(path)
                except Exception as e:  # noqa: BLE001 - a bad PDF must never kill the worker
                    logger.warning("KB ingest failed for {}: {}", path, e)
                    self._mark_failed(path)

    def _emit_progress(self, doc_id: str, status: str, pct: float) -> None:
        if self._on_progress is None:
            return
        try:
            self._on_progress({"doc_id": doc_id, "status": status, "pct": round(pct, 1)})
        except Exception as e:  # noqa: BLE001 - a bad consumer never kills the worker
            logger.warning("KB on_progress callback failed: {}", e)

    def _mark_failed(self, path: Path) -> None:
        doc_id = _doc_id_for(path.name)
        with self._lock:
            rec = self._docs.get(doc_id)
            if rec is not None:
                rec.status = "failed"
        self._emit_progress(doc_id, "failed", 0.0)

    def _ingest_one(self, path: Path) -> None:
        """Parse -> chunk -> embed -> append + persist atomically. One writer."""
        doc_id = _doc_id_for(path.name)
        self._set_status(doc_id, "parsing")
        self._emit_progress(doc_id, "parsing", 0.0)

        pages = parse_pdf(path)
        raw_chunks = chunk_pages(pages)
        if not raw_chunks:
            logger.warning("KB doc produced no chunks", doc_id=doc_id, file=path.name)
            self._finalize_doc(doc_id, path, pages=len(pages), metas=[], vectors=None)
            return

        self._set_status(doc_id, "embedding")
        self._emit_progress(doc_id, "embedding", 50.0)

        emb = self._get_embedder()
        vectors = emb.encode([c.text for c in raw_chunks])
        metas = [
            ChunkMeta(
                doc_id=doc_id,
                chunk_id=i,
                page=c.page,
                section=c.section,
                text=c.text,
                char_len=len(c.text),
            )
            for i, c in enumerate(raw_chunks)
        ]
        self._finalize_doc(doc_id, path, pages=len(pages), metas=metas, vectors=vectors)
        self._emit_progress(doc_id, "ready", 100.0)

    def _set_status(self, doc_id: str, status: str) -> None:
        with self._lock:
            rec = self._docs.get(doc_id)
            if rec is not None:
                rec.status = status

    def _finalize_doc(
        self,
        doc_id: str,
        path: Path,
        *,
        pages: int,
        metas: list[ChunkMeta],
        vectors: np.ndarray | None,
    ) -> None:
        """Append the doc's chunks to the index and persist. Single writer."""
        with self._lock:
            dim = int(vectors.shape[1]) if vectors is not None and vectors.size else None
            if self._index is None:
                self._index = VectorIndex(dim if dim is not None else self._get_embedder().dim)
                self._embedder_name = self._current_embedder_name()
            # Re-ingest: drop any prior rows for this doc first.
            self._index.remove_doc(doc_id)
            if metas and vectors is not None and vectors.size:
                self._index.add(vectors, metas)
            size = path.stat().st_size if path.exists() else 0
            self._docs[doc_id] = DocRecord(
                doc_id=doc_id,
                filename=path.name,
                pages=pages,
                chunk_count=len(metas),
                size_bytes=size,
                ingested_at=self._clock(),
                status="ready",
            )
            self._persist()

    def delete(self, doc_id: str) -> bool:
        """Remove a doc and re-persist the index/chunks/manifest atomically."""
        with self._lock:
            if doc_id not in self._docs:
                return False
            if self._index is not None:
                self._index.remove_doc(doc_id)
            del self._docs[doc_id]
            self._persist()
        logger.info("KB doc deleted", doc_id=doc_id)
        return True

    # ----- lifecycle -----

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._wake.set()
        self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("Knowledge base worker stopped")

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """Block until the ingest queue drains (test/utility helper)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._queue and not self._wake.is_set():
                return True
            time.sleep(0.02)
        return not self._queue
