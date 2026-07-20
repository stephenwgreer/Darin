"""Tests for the Context Pack — round-trip, directory creation, token budget."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from services.context_pack import ContextPack, estimate_tokens


class TestContextPackRoundTrip:
    def test_directory_created_under_storage_path(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path)
        assert pack.directory == tmp_path / "context"
        assert pack.directory.is_dir()

    def test_empty_pack_loads_empty_docs(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path)
        assert pack.load() == {"profile": "", "products": "", "known_issues": ""}
        assert pack.as_text() == ""

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path)
        pack.save(
            profile="I am a solutions engineer.",
            products="Product A does X.",
            known_issues="Bug 123 is open.",
        )

        docs = pack.load()
        assert docs["profile"] == "I am a solutions engineer."
        assert docs["products"] == "Product A does X."
        assert docs["known_issues"] == "Bug 123 is open."

        # A fresh instance over the same dir sees the same content
        again = ContextPack(tmp_path)
        assert again.load() == docs

    def test_partial_save_leaves_other_docs_alone(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path)
        pack.save(profile="original profile", products="original products")
        pack.save(products="updated products")

        docs = pack.load()
        assert docs["profile"] == "original profile"
        assert docs["products"] == "updated products"

    def test_save_rejects_unknown_doc(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path)
        try:
            pack.save(secrets="nope")
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for unknown doc key")

    def test_files_are_the_contracted_names(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path)
        pack.save(profile="p", products="q", known_issues="r")
        names = sorted(f.name for f in pack.directory.iterdir())
        assert names == ["known_issues.md", "products.md", "profile.md"]


class TestContextPackAsText:
    def test_as_text_includes_headers_for_nonempty_docs(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path)
        pack.save(profile="profile body", known_issues="issues body")

        text = pack.as_text()
        assert "# User profile" in text
        assert "profile body" in text
        assert "# Known issues" in text
        assert "issues body" in text
        assert "# Products" not in text  # empty doc omitted

    def test_token_estimate_formula(self) -> None:
        assert estimate_tokens("one two three four") == int(4 * 1.3)

    def test_over_budget_logs_warning(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path, max_tokens=10)
        pack.save(profile="word " * 100)

        with patch("services.context_pack.logger") as mock_logger:
            text = pack.as_text()

        assert "word" in text  # content is warned about, never truncated
        assert mock_logger.warning.called

    def test_under_budget_no_warning(self, tmp_path: Path) -> None:
        pack = ContextPack(tmp_path)
        pack.save(profile="short")

        with patch("services.context_pack.logger") as mock_logger:
            pack.as_text()

        assert not mock_logger.warning.called
