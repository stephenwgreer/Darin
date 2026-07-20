"""User-editable Context Pack — the domain grounding for both LLM lanes.

Three markdown documents (profile.md, products.md, known_issues.md) stored
under ``<storage_path>/context/``. Their concatenation is loaded into the
CACHED system block of every live-lane request, so the copilot can ground
answers in the user's own products and known issues.

Empty files are fine: an empty pack simply yields a generic copilot.
Total size is capped at ~20k estimated tokens (len(text.split()) * 1.3) —
exceeding the cap logs a warning but does not truncate (the user owns the
content; we only warn about cost/latency).
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

import config


# Maps API/document keys to on-disk filenames and section headers.
CONTEXT_DOCS: dict[str, tuple[str, str]] = {
    "profile": ("profile.md", "User profile"),
    "products": ("products.md", "Products"),
    "known_issues": ("known_issues.md", "Known issues"),
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate: words * 1.3 (matches the map-reduce heuristic)."""
    return int(len(text.split()) * 1.3)


class ContextPack:
    """Loads and saves the three context-pack markdown documents."""

    def __init__(
        self,
        storage_path: str | Path,
        *,
        max_tokens: int = config.CONTEXT_PACK_MAX_TOKENS,
    ) -> None:
        self._dir = Path(storage_path) / "context"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_tokens = max_tokens
        logger.info("Context pack directory ready", path=str(self._dir))

    @property
    def directory(self) -> Path:
        return self._dir

    def load(self) -> dict[str, str]:
        """Return {profile, products, known_issues} — missing files are ""."""
        docs: dict[str, str] = {}
        for key, (filename, _header) in CONTEXT_DOCS.items():
            path = self._dir / filename
            try:
                docs[key] = path.read_text(encoding="utf-8") if path.exists() else ""
            except OSError as e:
                logger.warning("Failed to read context doc", file=str(path), error=str(e))
                docs[key] = ""
        return docs

    def save(self, **docs: str) -> None:
        """Write any subset of {profile, products, known_issues}."""
        for key, text in docs.items():
            if key not in CONTEXT_DOCS:
                raise ValueError(f"Unknown context document: {key!r}")
            filename, _header = CONTEXT_DOCS[key]
            (self._dir / filename).write_text(text or "", encoding="utf-8")
            logger.info("Context doc saved", doc=key, chars=len(text or ""))

    def as_text(self) -> str:
        """Concatenated pack for the cached system block ("" if all empty)."""
        docs = self.load()
        sections: list[str] = []
        for key, (_filename, header) in CONTEXT_DOCS.items():
            body = docs[key].strip()
            if body:
                sections.append(f"# {header}\n\n{body}")
        text = "\n\n".join(sections)

        tokens = estimate_tokens(text)
        if tokens > self._max_tokens:
            logger.warning(
                "Context pack exceeds token budget",
                estimated_tokens=tokens,
                max_tokens=self._max_tokens,
            )
        return text

    def estimated_tokens(self) -> int:
        return estimate_tokens(self.as_text())
