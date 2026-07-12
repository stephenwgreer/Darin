"""User-level configuration and custom prompt persistence.

Stored at ~/.darin-audio-assistant/config.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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
    # Per-prompt model choice + web search (F2/F3). Empty model = fall back to
    # config.REACTIVE_MODEL at registry-effective time.
    model: str = ""
    web_search: bool = False
    # Opt-in local RAG grounding for this custom prompt. Default off for custom
    # prompts (built-in reactive prompts default on); see PromptConfig.use_rag.
    use_rag: bool = False


@dataclass
class CustomEndpointConfig:
    """A user-defined OpenAI-compatible endpoint (Groq / Gemini-OpenAI-compat /
    Cerebras / local Ollama / a ChatJimmy-style proxy).

    The code knows nothing provider-specific — it is just ``base_url`` +
    ``/chat/completions``. ``api_key`` may be empty (some proxies need none);
    the adapter substitutes ``"dummy"`` when talking to the OpenAI SDK.
    """

    id: str  # unique slug, referenced as a model id
    label: str
    base_url: str
    model_name: str
    api_key: str = ""


@dataclass
class AppConfig:
    storage_path: str = _DEFAULT_STORAGE_PATH
    background_style: str = "default"  # "default" | "darin"
    persona: str = "general"  # "general" | "sales" | "technical"
    custom_prompts: list[CustomPromptConfig] = field(default_factory=list)
    deleted_prompt_ids: list[str] = field(default_factory=list)
    # Overrides for built-in prompts: {prompt_id: {field: new_value}}
    prompt_overrides: dict[str, dict] = field(default_factory=dict)
    # User-defined OpenAI-compatible endpoints (F2).
    custom_endpoints: list[CustomEndpointConfig] = field(default_factory=list)
    # Per-prompt model override for the proactive watcher lane (F2). None =
    # fall back to config.WATCHER_MODEL.
    watcher_model: str | None = None
    # F4 retention: when False (default) expired proactive cards transition to a
    # dimmed "aged" state and are kept in the feed; when True the old
    # fade-and-remove behavior is restored.
    auto_hide_expired: bool = False
    # Auto-Answer: when True (default) a watcher "question_at_user" card
    # automatically triggers the reactive answer_this pipeline.
    auto_answer_enabled: bool = True
    # Knowledge base (local RAG). Enable flag + the folder of PDFs to ingest.
    knowledge_base_enabled: bool = True
    knowledge_docs_folder: str = ""


class AppConfigStore:
    """Load and save AppConfig to/from a JSON file."""

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = config_path or _DEFAULT_CONFIG_PATH

    def load(self) -> AppConfig:
        """Load the config, failing LOUD on corruption instead of silently.

        A corrupt config file is backed up to ``config.json.bak`` before a
        fresh default config is returned, so the next ``save()`` cannot
        permanently destroy the user's custom prompts. Individual malformed
        custom-prompt entries (unknown/missing fields) are skipped with a
        warning and never take the rest of the config down with them.
        """
        if not self._path.exists():
            return AppConfig()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"config root must be a JSON object, got {type(data).__name__}")
        except Exception as e:  # noqa: BLE001
            backup_path = self._backup_corrupt_config()
            logger.error(
                "Config file is CORRUPT and has been backed up — starting fresh",
                path=str(self._path),
                backup=str(backup_path) if backup_path else "backup failed",
                error=str(e),
            )
            return AppConfig()

        watcher_model = data.get("watcher_model")
        return AppConfig(
            storage_path=data.get("storage_path", _DEFAULT_STORAGE_PATH),
            background_style=data.get("background_style", "default"),
            persona=data.get("persona", "general"),
            custom_prompts=self._parse_custom_prompts(data.get("custom_prompts", [])),
            deleted_prompt_ids=data.get("deleted_prompt_ids", []),
            prompt_overrides=data.get("prompt_overrides", {}),
            custom_endpoints=self._parse_custom_endpoints(data.get("custom_endpoints", [])),
            watcher_model=watcher_model if isinstance(watcher_model, str) else None,
            auto_hide_expired=bool(data.get("auto_hide_expired", False)),
            auto_answer_enabled=bool(data.get("auto_answer_enabled", True)),
            knowledge_base_enabled=bool(data.get("knowledge_base_enabled", True)),
            knowledge_docs_folder=str(data.get("knowledge_docs_folder", "") or ""),
        )

    def _backup_corrupt_config(self) -> Path | None:
        """Move the corrupt config file aside to ``<name>.bak``."""
        backup_path = self._path.with_name(self._path.name + ".bak")
        try:
            self._path.replace(backup_path)
        except OSError as e:
            logger.error(
                "Could not back up corrupt config file",
                path=str(self._path),
                error=str(e),
            )
            return None
        return backup_path

    @staticmethod
    def _parse_custom_prompts(raw_prompts: object) -> list[CustomPromptConfig]:
        """Parse custom prompt entries, skipping malformed ones individually."""
        if not isinstance(raw_prompts, list):
            logger.warning(
                "custom_prompts is not a list — ignoring",
                got=type(raw_prompts).__name__,
            )
            return []

        known_fields = {
            "id",
            "button_text",
            "output_title",
            "template",
            "model",
            "web_search",
            "use_rag",
        }
        prompts: list[CustomPromptConfig] = []
        for entry in raw_prompts:
            if not isinstance(entry, dict):
                logger.warning("Skipping non-object custom prompt entry", entry=repr(entry)[:200])
                continue
            unknown = set(entry) - known_fields
            if unknown:
                logger.warning(
                    "Ignoring unknown fields on custom prompt",
                    prompt_id=entry.get("id", "<missing>"),
                    unknown_fields=sorted(unknown),
                )
            try:
                prompts.append(
                    CustomPromptConfig(**{k: entry[k] for k in known_fields & set(entry)})
                )
            except TypeError as e:
                logger.warning(
                    "Skipping malformed custom prompt (missing required fields)",
                    prompt_id=entry.get("id", "<missing>"),
                    error=str(e),
                )
        return prompts

    @staticmethod
    def _parse_custom_endpoints(raw_endpoints: object) -> list[CustomEndpointConfig]:
        """Parse custom OpenAI-compatible endpoint entries, skipping malformed ones."""
        if not isinstance(raw_endpoints, list):
            logger.warning(
                "custom_endpoints is not a list — ignoring",
                got=type(raw_endpoints).__name__,
            )
            return []

        known_fields = {"id", "label", "base_url", "model_name", "api_key"}
        endpoints: list[CustomEndpointConfig] = []
        for entry in raw_endpoints:
            if not isinstance(entry, dict):
                logger.warning("Skipping non-object custom endpoint entry", entry=repr(entry)[:200])
                continue
            try:
                endpoints.append(
                    CustomEndpointConfig(**{k: entry[k] for k in known_fields & set(entry)})
                )
            except TypeError as e:
                logger.warning(
                    "Skipping malformed custom endpoint (missing required fields)",
                    endpoint_id=entry.get("id", "<missing>"),
                    error=str(e),
                )
        return endpoints

    def save(self, config: AppConfig) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "storage_path": config.storage_path,
            "background_style": config.background_style,
            "persona": config.persona,
            "custom_prompts": [asdict(p) for p in config.custom_prompts],
            "deleted_prompt_ids": config.deleted_prompt_ids,
            "prompt_overrides": config.prompt_overrides,
            "custom_endpoints": [asdict(e) for e in config.custom_endpoints],
            "watcher_model": config.watcher_model,
            "auto_hide_expired": config.auto_hide_expired,
            "auto_answer_enabled": config.auto_answer_enabled,
            "knowledge_base_enabled": config.knowledge_base_enabled,
            "knowledge_docs_folder": config.knowledge_docs_folder,
        }
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Config saved to {}", self._path)
