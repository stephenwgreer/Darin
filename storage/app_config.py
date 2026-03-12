"""User-level configuration and custom prompt persistence.

Stored at ~/.darin-audio-assistant/config.json.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from loguru import logger

_DEFAULT_CONFIG_PATH = Path.home() / ".darin-audio-assistant" / "config.json"
_DEFAULT_STORAGE_PATH = str(Path.home() / ".darin-audio-assistant" / "meetings")


@dataclass
class CustomPromptConfig:
    id: str
    button_text: str
    output_title: str
    template: str


@dataclass
class AppConfig:
    storage_path: str = _DEFAULT_STORAGE_PATH
    custom_prompts: list[CustomPromptConfig] = field(default_factory=list)
    deleted_prompt_ids: list[str] = field(default_factory=list)
    # Overrides for built-in prompts: {prompt_id: {field: new_value}}
    prompt_overrides: dict[str, dict] = field(default_factory=dict)


class AppConfigStore:
    """Load and save AppConfig to/from a JSON file."""

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or _DEFAULT_CONFIG_PATH

    def load(self) -> AppConfig:
        if not self._path.exists():
            return AppConfig()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            custom_prompts = [
                CustomPromptConfig(**p) for p in data.get("custom_prompts", [])
            ]
            return AppConfig(
                storage_path=data.get("storage_path", _DEFAULT_STORAGE_PATH),
                custom_prompts=custom_prompts,
                deleted_prompt_ids=data.get("deleted_prompt_ids", []),
                prompt_overrides=data.get("prompt_overrides", {}),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to load config, using defaults: {}", e)
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "storage_path": config.storage_path,
            "custom_prompts": [asdict(p) for p in config.custom_prompts],
            "deleted_prompt_ids": config.deleted_prompt_ids,
            "prompt_overrides": config.prompt_overrides,
        }
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Config saved to {}", self._path)
