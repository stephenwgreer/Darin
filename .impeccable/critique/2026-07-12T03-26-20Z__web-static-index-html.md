---
target: card feed
total_score: 25
p0_count: 2
p1_count: 3
timestamp: 2026-07-12T03-26-20Z
slug: web-static-index-html
---
Method: dual-agent (A: design-review subagent · B: detector-evidence subagent)

# Critique: Darin card feed (`web/static`)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | SSE loss mid-call is console-only; feed dies silently |
| 2 | Match System / Real World | 3 | "watcher", "medium confidence · transcript" — internal jargon on cards |
| 3 | User Control and Freedom | 2 | Dismiss = permanent topic suppression, no undo; Esc closes nothing |
| 4 | Consistency and Standards | 3 | Chip palette breaks the One Meaning Rule (green/purple/amber reused off-meaning) |
| 5 | Error Prevention | 2 | End Session has no confirm; dismiss semantics tooltip-only |
| 6 | Recognition Rather Than Recall | 3 | Icon-only header buttons depend on title tooltips |
| 7 | Flexibility and Efficiency | 2 | Zero keyboard shortcuts despite PRODUCT.md promising them |
| 8 | Aesthetic and Minimalist Design | 3 | Chrome disciplined; card body carries ~12 elements |
| 9 | Error Recovery | 2 | Toasts name failure, not fix |
| 10 | Help and Documentation | 2 | Good hints in settings; nothing on the live surface |
| **Total** | | **25/40** | **Acceptable — significant improvements needed** |

## Anti-Patterns Verdict

LLM assessment: mostly trustworthy at the product-register bar. Real token discipline (one accent one meaning, tints with matching borders, single family). Hard tells: the 3px side-stripe lane border on cards (an absolute ban, and DESIGN.md §5 codifies it); emoji-as-icons in the header breaking the instrument aesthetic.

Deterministic scan: 21 findings, all styles.css — 1 warning (side-tab, line 462, confirming the LLM ban hit), 11 off-ramp font sizes, 7 undocumented colors (5 judged false positives: solid-button #000/#fff contrast text, shadow/scrim black-alpha), 2 off-ramp radii. Detector and review agree on the side-stripe and the type-ramp drift; the detector missed nothing the review found (urgency-soon no-op, buried say-this are logic/hierarchy issues outside its rule set).

False positive corrected in synthesis: Assessment A flagged a "leftover" localhost:8400 live.js script tag in index.html — that is the active Impeccable live-mode session injection (removed automatically at session exit), not shipped code.

Browser overlay: skipped — no browser automation tool; app runs on an ephemeral token-authenticated port.

## Overall Impression

The shell is a genuinely designed instrument; the payload betrays it. Token vocabulary, state machinery, and retention model are craft — but the copilot card, the one element the product exists for, reads ~589 characters with the say-this line last, mid-tier urgency (`urgency-soon`) silently renders as nothing, and a dropped SSE connection kills the copilot without a sound. The biggest opportunity: make the card as disciplined as the chrome around it.

## What's Working

1. Token discipline that reads intentional, not template: one accent per meaning, hairline borders, 8–35% tints, single family with weight/case hierarchy.
2. State machinery: per-button spinners with 90s self-healing timeouts, optimistic persona toggle with rollback, the aged-card dim→collapse→re-expand retention model (an original pattern).
3. Performance/safety serving the brand: rAF-batched SSE writes, textContent-only insertion, scroll-yield on user scroll-up. "Speed reads as competence" is implemented, not aspirational.

## Priority Issues

1. **[P0] Say-this is buried; the card defeats the product thesis.** PRODUCT.md: "hierarchy puts what to say above why." Rendered card: say_this 4th, below ~400 chars of bullets + a redundant cue row. Fix: SAY strip directly under (or above) the headline; bullets collapsed behind a disclosure or capped one line; drop cues that duplicate bullet tokens. → /impeccable layout
2. **[P0] `urgency-soon` is a silent no-op; urgency is not durable.** app.js emits `urgency-${card.urgency}` but only `.urgency-now` exists in CSS — the real sample card's urgency evaporated. NOW cards lose all signal after two pulses while new cards prepend above them. Fix: define `.urgency-soon`; pin unacknowledged NOW cards to feed top. → /impeccable polish
3. **[P1] Stated accessibility standards unimplemented.** Zero prefers-reduced-motion vs three infinite animations; measured contrast: say-this-label 4.16:1 at 8.4px, btn-action text 3.79:1 (both < 4.5). No aria-live on the feed; aged-card expand mouse-only. → /impeccable polish (a11y batch from the audit)
4. **[P1] Mid-call connection loss is invisible.** es.onerror retries silently every 3s; the operator mid-call will discover by absence. Fix: badge flips to RECONNECTING + one toast; clear on reopen. → /impeccable harden
5. **[P1] Dismiss is quietly destructive.** One click suppresses the topic for the whole meeting, disclosed only in a title tooltip, no undo. Fix: 5s undo toast; state the muting in card meta. → /impeccable clarify

## Persona Red Flags

**Alex (power user):** no shortcut reaches the 5 action buttons, Ask box, or dismiss; Esc closes no modal; no cancel for in-flight prompts. PRODUCT.md promises shortcuts; none exist.

**Sam (accessibility):** no aria-live — the proactive lane is inaudible to screen readers; aged-card re-expand unreachable by keyboard; lane meaning carried by border color alone; default UA focus ring instead of the promised Radar Blue ring; 8.7–9.8px micro text.

**Stephen (project persona, mid-call):** the 3-second glance fails on the real sample (~589 chars, payload last, ~135ch bullet lines); the always-streaming transcript sidebar competes with card arrival; urgency-soon gave him nothing; SSE drop kills the copilot silently.

## Minor Observations

- Amber cue badges on every card corrupt the amber = urgency vocabulary; the contradiction is inside DESIGN.md (§Chips vs §Colors).
- Chip palette reuses green/purple/amber off-meaning; amend the One Meaning Rule or re-tint chips neutral.
- card-meta "medium confidence · transcript" is opaque; "from live transcript" or drop.
- Enter-to-ask lacks an IME composition guard (e.isComposing).
- .card-feed max-height calc(100vh - 16rem) breaks if the action bar wraps.
- 11 off-ramp font sizes + 2 radii (detector) = type-scale drift; consolidate on the six-step ramp.
- Empty-state copy is genuinely good teaching copy.

## Questions to Consider

1. What if the card WERE the say-this line — headline + SAY visible, everything else behind one tap?
2. Is the enforcement point CSS or the schema? Should services/cards.py cap proactive bullets (~70 chars, 2 max) so no prompt regression can re-bloat the card?
3. Does the live transcript earn its constantly-animating pixels next to the thing the operator must glance at? What breaks as a one-line last-utterance ticker?
