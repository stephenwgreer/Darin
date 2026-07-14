"""Speculative-question detection policy — pure, code-enforced, injectable clock.

Tier-1 (deterministic, no LLM) detector that watches THEM's ASR interim/final
text and decides whether to speculatively fire a fast answer, bypassing the
watcher's slow gates. Mutated concurrently from the Deepgram listener thread,
reactive worker threads, and the utterance-end path — every public method
acquires an internal lock (unlike auto_answer.py's atomic set ops, this policy
holds compound float+dict state that must be updated together).
"""
from __future__ import annotations

import enum
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import config


SPECULATIVE_TRIGGER = "speculative_answer"


class Decision(enum.Enum):
    HOLD = "hold"
    FIRE = "fire"
    SUPERSEDE = "supersede"


@dataclass(frozen=True)
class DetectHit:
    rule: str
    matched_text: str
    question_key: str


@dataclass
class SpeculativeRules:
    same_question_cooldown_s: float = 8.0
    global_cooldown_s: float = 4.0
    name_final_pause_s: float = 0.7
    recently_answered_s: float = 45.0


# --- Detection primitives -----------------------------------------------

_SECOND_PERSON = r"(?:you're|you\s+are|your|you)"

_INTERROGATIVE_STEMS: tuple[str, ...] = (
    "can you",
    "does your",
    "how do you",
    "what's your",
    "could you",
    "would you",
    "do you",
)

_HANDOFF_PHRASES: tuple[str, ...] = (
    "thoughts?",
    "over to you",
    "what do you think",
    "your take",
)

# A challenge form: "don't you think", "isn't that right" style pushback
# aimed squarely at the second person.
_CHALLENGE_RE = re.compile(
    r"\b(?:don't|doesn't|isn't|aren't|wouldn't|shouldn't)\s+you\b", re.IGNORECASE
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "do", "does", "did", "have", "has", "had", "i", "you", "your",
        "you're", "he", "she", "it", "we", "they", "them", "this", "that",
        "these", "those", "to", "of", "in", "on", "at", "for", "with",
        "and", "or", "but", "so", "what", "what's", "how", "can", "could",
        "would", "will", "about", "as", "over",
    }
)

_PUNCT_RE = re.compile(r"[^\w\s']")
_WHITESPACE_RE = re.compile(r"\s+")


def _build_name_alternation(aliases: tuple[str, ...]) -> str:
    escaped = sorted((re.escape(a) for a in aliases), key=len, reverse=True)
    return "|".join(escaped)


def _third_person_guard(text: str, name_alt: str) -> re.Pattern[str]:
    return re.compile(
        rf"\b(?:as|when|like)\b[^.!?]{{0,40}}\b(?:{name_alt})\b[^.!?]{{0,40}}"
        rf"\b(?:said|mentioned|thinks|noted|says|mentioned that|pointed out)\b",
        re.IGNORECASE,
    )


def _name_second_person_re(name_alt: str) -> re.Pattern[str]:
    # "<Name> ... can/do/does/could/would you ..." or "<Name>, your ..."
    return re.compile(
        rf"\b(?:{name_alt})\b[^.!?]{{0,30}}\b{_SECOND_PERSON}\b",
        re.IGNORECASE,
    )


def _name_utterance_final_re(name_alt: str) -> re.Pattern[str]:
    return re.compile(rf"\b(?:{name_alt})\b\W*$", re.IGNORECASE)


def _detect(
    text: str,
    *,
    name_final_pause_ok: bool,
    aliases: tuple[str, ...] = config.USER_NAME_ALIASES,
) -> DetectHit | None:
    """Apply detection rules, in order, rejecting third-person narration first."""
    stripped = text.strip()
    if not stripped:
        return None

    name_alt = _build_name_alternation(aliases)
    if name_alt and _third_person_guard(stripped, name_alt).search(stripped):
        return None

    lowered = stripped.lower()

    if name_alt:
        name_second_person = _name_second_person_re(name_alt)
        match = name_second_person.search(stripped)
        if match:
            return DetectHit(
                rule="name_second_person",
                matched_text=match.group(0),
                question_key=question_key(stripped, aliases=aliases),
            )

    for stem in _INTERROGATIVE_STEMS:
        idx = lowered.find(stem)
        if idx != -1:
            return DetectHit(
                rule="interrogative_stem",
                matched_text=stripped[idx : idx + len(stem)],
                question_key=question_key(stripped, aliases=aliases),
            )

    challenge = _CHALLENGE_RE.search(stripped)
    if challenge:
        return DetectHit(
            rule="challenge_form",
            matched_text=challenge.group(0),
            question_key=question_key(stripped, aliases=aliases),
        )

    for phrase in _HANDOFF_PHRASES:
        idx = lowered.find(phrase)
        if idx != -1:
            return DetectHit(
                rule="handoff_phrase",
                matched_text=stripped[idx : idx + len(phrase)],
                question_key=question_key(stripped, aliases=aliases),
            )

    if name_alt and name_final_pause_ok:
        name_final = _name_utterance_final_re(name_alt)
        match = name_final.search(stripped)
        if match:
            return DetectHit(
                rule="name_utterance_final",
                matched_text=match.group(0).strip(),
                question_key=question_key(stripped, aliases=aliases),
            )

    return None


def question_key(
    text: str, *, aliases: tuple[str, ...] = config.USER_NAME_ALIASES
) -> str:
    """Order-independent fingerprint of a question's content tokens.

    Lowercase, strip punctuation, drop stopwords and name aliases, sort the
    remaining content tokens, join the first 12. The name never appears in
    the key so "Stephen, can you..." and "can you..." fingerprint the same.
    """
    lowered = text.lower()
    no_punct = _PUNCT_RE.sub(" ", lowered)
    tokens = _WHITESPACE_RE.split(no_punct.strip())

    drop = _STOPWORDS | {a.lower() for a in aliases}
    content_tokens = [t for t in tokens if t and t not in drop]
    content_tokens.sort()
    return " ".join(content_tokens[:12])


def _last_them_span(full_transcript: str) -> str:
    """Extract the last THEM span from a full transcript.

    Supports a simple "SPEAKER: text" line format; falls back to the whole
    transcript when no speaker-tagged lines are present.
    """
    lines = [line.strip() for line in full_transcript.splitlines() if line.strip()]
    them_lines = [line for line in lines if line.upper().startswith("THEM:")]
    if not them_lines:
        return full_transcript
    last = them_lines[-1]
    return last.split(":", 1)[1].strip() if ":" in last else last


class SpeculativeQuestionPolicy:
    """Decide whether THEM's live speech warrants a speculative answer.

    No I/O, injectable clock. Thread-safe: mutated from the Deepgram listener
    thread, reactive worker threads, and the utterance-end path concurrently,
    so every public method acquires `self._lock`.
    """

    def __init__(
        self,
        rules: SpeculativeRules | None = None,
        *,
        aliases: tuple[str, ...] = config.USER_NAME_ALIASES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rules = rules or SpeculativeRules()
        self.aliases = aliases
        self._clock = clock
        self._lock = threading.Lock()

        self._last_fire_at: float | None = None
        self._fired_key_at: dict[str, float] = {}
        self._answered_at: dict[str, float] = {}
        self._pending_key: str | None = None
        self._last_them_interim_at: float | None = None

    def on_interim(
        self, text: str, speaker: str, *, now: float | None = None
    ) -> tuple[Decision, DetectHit | None]:
        if speaker != "THEM":
            return Decision.HOLD, None

        with self._lock:
            current = now if now is not None else self._clock()

            gap = (
                current - self._last_them_interim_at
                if self._last_them_interim_at is not None
                else None
            )
            self._last_them_interim_at = current

            name_final_pause_ok = (
                gap is not None and gap >= self.rules.name_final_pause_s
            )

            hit = _detect(
                text, name_final_pause_ok=name_final_pause_ok, aliases=self.aliases
            )
            if hit is None:
                return Decision.HOLD, None

            if not self._is_clear_to_fire(hit.question_key, current):
                return Decision.HOLD, hit

            return Decision.FIRE, hit

    def on_utterance_final(
        self, full_transcript: str, *, now: float | None = None
    ) -> tuple[Decision, DetectHit | None]:
        with self._lock:
            current = now if now is not None else self._clock()
            span = _last_them_span(full_transcript)
            hit = _detect(span, name_final_pause_ok=True, aliases=self.aliases)
            if hit is None:
                return Decision.HOLD, None

            if self._pending_key is None:
                if not self._is_clear_to_fire(hit.question_key, current):
                    return Decision.HOLD, hit
                return Decision.FIRE, hit

            if hit.question_key == self._pending_key:
                return Decision.HOLD, hit

            return Decision.SUPERSEDE, hit

    def note_fired(self, key: str, *, now: float | None = None) -> None:
        with self._lock:
            current = now if now is not None else self._clock()
            self._last_fire_at = current
            self._fired_key_at[key] = current
            self._pending_key = key

    def note_accepted(self, *, now: float | None = None) -> None:
        """No-op placeholder kept for parity with AutoAnswerPolicy's concept.

        Speculative fires arm their cooldowns immediately on `note_fired`
        (unlike auto_answer, which waits for reactive-lane acceptance),
        because a speculative fire has no interactive lane to lose a race
        against. Kept as an explicit call site so callers mirror the
        auto_answer lifecycle and the concept has one obvious home if that
        changes.
        """

    def note_rejected(self) -> None:
        with self._lock:
            if self._pending_key is not None:
                self._fired_key_at.pop(self._pending_key, None)
            self._last_fire_at = None
            self._pending_key = None

    def note_answered(self, key: str, *, now: float | None = None) -> None:
        with self._lock:
            current = now if now is not None else self._clock()
            self._answered_at[key] = current
            if self._pending_key == key:
                self._pending_key = None

    def was_recently_answered(self, key: str, *, now: float | None = None) -> bool:
        with self._lock:
            current = now if now is not None else self._clock()
            return self._was_recently_answered_locked(key, current)

    def fired_within(self, window: float, *, now: float | None = None) -> bool:
        with self._lock:
            current = now if now is not None else self._clock()
            if self._last_fire_at is None:
                return False
            return current - self._last_fire_at < window

    def clear(self) -> None:
        with self._lock:
            self._last_fire_at = None
            self._fired_key_at.clear()
            self._answered_at.clear()
            self._pending_key = None
            self._last_them_interim_at = None

    # --- internal helpers (must be called with self._lock held) --------

    def _is_clear_to_fire(self, key: str, current: float) -> bool:
        if (
            self._last_fire_at is not None
            and current - self._last_fire_at < self.rules.global_cooldown_s
        ):
            return False

        fired_at = self._fired_key_at.get(key)
        if (
            fired_at is not None
            and current - fired_at < self.rules.same_question_cooldown_s
        ):
            return False

        return not self._was_recently_answered_locked(key, current)

    def _was_recently_answered_locked(self, key: str, current: float) -> bool:
        answered_at = self._answered_at.get(key)
        if answered_at is None:
            return False
        return current - answered_at < self.rules.recently_answered_s
