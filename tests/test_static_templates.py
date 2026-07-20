# tests/test_static_templates.py
"""Tests for STATIC_TEMPLATES registry (DAR2-37)."""

from __future__ import annotations

from web.stream_handlers import STATIC_TEMPLATES, TEMPLATE_REGISTRY


class TestStaticTemplatesRegistry:
    """Verify every TEMPLATE_REGISTRY entry has a matching scaffold."""

    def test_all_registered_templates_have_scaffold(self) -> None:
        for template_type in TEMPLATE_REGISTRY:
            assert template_type in STATIC_TEMPLATES, (
                f"Missing STATIC_TEMPLATES entry for '{template_type}'"
            )

    def test_scaffold_contains_target_ids(self) -> None:
        """Each scaffold must contain the element IDs the router targets."""
        for template_type, config in TEMPLATE_REGISTRY.items():
            scaffold = STATIC_TEMPLATES[template_type]
            handler_type = config["type"]

            if handler_type == "single-list":
                target = config["target"]
                assert f'id="{target}"' in scaffold, (
                    f"{template_type}: missing id='{target}' in scaffold"
                )

            elif handler_type == "multi-list":
                for list_id in config.get("class_to_list", {}).values():
                    assert f'id="{list_id}"' in scaffold, (
                        f"{template_type}: missing id='{list_id}' in scaffold"
                    )
                for list_id in config.get("group_classes", {}):
                    assert f'id="{list_id}"' in scaffold, (
                        f"{template_type}: missing id='{list_id}' in scaffold"
                    )

            elif handler_type == "class-derived":
                # class-derived IDs are built at runtime; just check scaffold exists
                assert len(scaffold.strip()) > 0

    def test_generic_fallback_exists(self) -> None:
        assert "generic" in STATIC_TEMPLATES
        assert 'id="dynamic-content"' in STATIC_TEMPLATES["generic"]
