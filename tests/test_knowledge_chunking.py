"""Pure chunking tests — header path, sizing, overlap, budget. No PDF, no torch."""

from __future__ import annotations

import config
from services.context_pack import estimate_tokens
from services.knowledge_base import ParsedPage, RawChunk, chunk_pages


def _words(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


class TestHeaderPath:
    def test_header_path_prepended(self) -> None:
        pages = [ParsedPage(page=3, text=_words(20), headers=["Deployment", "Kubernetes"])]
        chunks = chunk_pages(pages)
        assert chunks[0].section == "# Deployment > Kubernetes"
        assert chunks[0].text.startswith("# Deployment > Kubernetes\n\n")

    def test_single_header(self) -> None:
        chunks = chunk_pages([ParsedPage(page=1, text=_words(10), headers=["Overview"])])
        assert chunks[0].section == "# Overview"
        assert chunks[0].text.startswith("# Overview\n\n")

    def test_no_headers_no_prefix(self) -> None:
        chunks = chunk_pages([ParsedPage(page=1, text=_words(10), headers=[])])
        assert chunks[0].section == ""
        assert not chunks[0].text.startswith("#")

    def test_blank_headers_ignored(self) -> None:
        chunks = chunk_pages([ParsedPage(page=1, text=_words(5), headers=["  ", ""])])
        assert chunks[0].section == ""

    def test_accepts_plain_dicts(self) -> None:
        chunks = chunk_pages([{"page": 2, "text": _words(5), "headers": ["H1"]}])
        assert isinstance(chunks[0], RawChunk)
        assert chunks[0].page == 2
        assert chunks[0].section == "# H1"


class TestSizingAndOverlap:
    def test_chunk_near_target_tokens(self) -> None:
        # A page with ~2.5 windows worth of words -> multiple chunks.
        words_per_chunk = int(round(config.KB_CHUNK_TOKENS / 1.3))
        pages = [ParsedPage(page=1, text=_words(words_per_chunk * 2 + 5), headers=[])]
        chunks = chunk_pages(pages)
        assert len(chunks) >= 2
        # Each chunk body is at or under the target token budget.
        for c in chunks:
            assert estimate_tokens(c.text) <= config.KB_CHUNK_TOKENS + 5

    def test_overlap_between_consecutive_chunks(self) -> None:
        words_per_chunk = int(round(config.KB_CHUNK_TOKENS / 1.3))
        overlap = int(round(words_per_chunk * config.KB_CHUNK_OVERLAP_FRAC))
        pages = [ParsedPage(page=1, text=_words(words_per_chunk * 2), headers=[])]
        chunks = chunk_pages(pages)
        assert len(chunks) >= 2
        first = chunks[0].text.split()
        second = chunks[1].text.split()
        # Tail of chunk 0 reappears at the head of chunk 1 (word overlap).
        tail = first[-overlap:]
        assert tail == second[: len(tail)]

    def test_short_page_single_chunk(self) -> None:
        chunks = chunk_pages([ParsedPage(page=1, text=_words(5), headers=[])])
        assert len(chunks) == 1

    def test_empty_page_skipped(self) -> None:
        chunks = chunk_pages(
            [
                ParsedPage(page=1, text="", headers=["H"]),
                ParsedPage(page=2, text=_words(3), headers=[]),
            ]
        )
        assert len(chunks) == 1
        assert chunks[0].page == 2

    def test_chunk_never_straddles_pages(self) -> None:
        pages = [
            ParsedPage(page=1, text=_words(10), headers=["A"]),
            ParsedPage(page=2, text=_words(10), headers=["B"]),
        ]
        chunks = chunk_pages(pages)
        pages_seen = {c.page for c in chunks}
        assert pages_seen == {1, 2}
        for c in chunks:
            if c.page == 1:
                assert c.section == "# A"
            else:
                assert c.section == "# B"


class TestBudgetProgress:
    def test_always_advances_no_infinite_loop(self) -> None:
        # A very long page must terminate and produce a bounded number of chunks.
        pages = [ParsedPage(page=1, text=_words(5000), headers=[])]
        chunks = chunk_pages(pages)
        assert 0 < len(chunks) < 5000

    def test_empty_input(self) -> None:
        assert chunk_pages([]) == []
