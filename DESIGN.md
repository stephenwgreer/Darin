---
name: Darin
description: Civic Evidence Desk design system — one identity, two materials (Desk paper / After Hours dark), stamp-ink signals, docket typography
colors:
  record-paper: "#F4EADB"
  fresh-sheet: "#FBF6EC"
  blotter: "#EFE3CC"
  manila: "#DFCAA8"
  rule-line: "#D6C8AB"
  rule-strong: "#C4B491"
  sheet-white: "#FFFDF7"
  navy-ink: "#17213A"
  second-ink: "#34415F"
  faded-ink: "#566074"
  federal-blue: "#4F78A6"
  federal-blue-ink: "#33507A"
  ledger-teal: "#366B62"
  ochre-seal: "#8A6320"
  ochre-seal-ink: "#755416"
  approval-green: "#3F7249"
  approval-green-ink: "#335C3B"
  inspection-red: "#B83A2E"
  inspection-red-ink: "#9E2F24"
  notary-violet: "#6B4E8E"
  brass: "#C8AA6A"
  night-canvas: "#131926"
  night-sheet: "#1A2233"
  night-well: "#10151F"
  night-raised: "#232D42"
  night-input: "#161D2C"
  night-rule: "#2C3650"
  night-rule-strong: "#3A4763"
  lamplight-paper: "#EDE4D3"
  night-second-ink: "#C9CFDC"
  night-faded-ink: "#9AA3B5"
  night-federal-blue: "#7FA5CC"
  night-federal-blue-ink: "#8FB2D6"
  night-ledger-teal: "#72B4A5"
  night-ochre-seal: "#CE9E45"
  night-approval-green: "#7CBF8E"
  night-inspection-red: "#E08273"
  night-notary-violet: "#B195D2"
typography:
  display:
    fontFamily: "'Fraunces', Georgia, 'Times New Roman', serif"
    fontSize: "1.25rem"
    fontWeight: 600
    letterSpacing: "0.12em"
  title:
    fontFamily: "'Fraunces', Georgia, 'Times New Roman', serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.3
  say:
    fontFamily: "'Fraunces', Georgia, 'Times New Roman', serif"
    fontSize: "0.95rem"
    fontStyle: italic
    fontWeight: 500
    lineHeight: 1.45
  body:
    fontFamily: "'Libre Franklin', 'Segoe UI', system-ui, sans-serif"
    fontSize: "0.875rem"
    lineHeight: 1.55
  longform:
    fontFamily: "'Libre Franklin', 'Segoe UI', system-ui, sans-serif"
    fontSize: "1rem"
    lineHeight: 1.65
  label:
    fontFamily: "'IBM Plex Mono', 'Cascadia Mono', ui-monospace, monospace"
    fontSize: "0.7rem"
    fontWeight: 600
    letterSpacing: "0.08em"
  micro:
    fontFamily: "'IBM Plex Mono', 'Cascadia Mono', ui-monospace, monospace"
    fontSize: "0.65rem"
    fontWeight: 600
    letterSpacing: "0.06em"
  mono:
    fontFamily: "'IBM Plex Mono', 'Cascadia Mono', ui-monospace, monospace"
    fontSize: "0.78rem"
    lineHeight: 1.55
rounded:
  sm: "2px"
  md: "3px"
  none: "0"
spacing:
  xs: "0.3rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.5rem"
components:
  button-primary:
    backgroundColor: "{colors.navy-ink}"
    textColor: "{colors.fresh-sheet}"
    rounded: "{rounded.sm}"
    padding: "0.45rem 1rem"
  button-go:
    backgroundColor: "{colors.approval-green}"
    textColor: "{colors.fresh-sheet}"
    rounded: "{rounded.sm}"
    padding: "0.45rem 1rem"
  button-stop:
    backgroundColor: "{colors.inspection-red}"
    textColor: "{colors.fresh-sheet}"
    rounded: "{rounded.sm}"
    padding: "0.45rem 1rem"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.navy-ink}"
    rounded: "{rounded.sm}"
    padding: "0.45rem 1rem"
  button-action:
    backgroundColor: "#4F78A624"
    textColor: "{colors.federal-blue-ink}"
    rounded: "{rounded.sm}"
    padding: "0.42rem 0.9rem"
  card:
    backgroundColor: "{colors.fresh-sheet}"
    rounded: "{rounded.md}"
    padding: "0.75rem 0.9rem"
  input:
    backgroundColor: "{colors.sheet-white}"
    textColor: "{colors.navy-ink}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 0.9rem"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.faded-ink}"
    rounded: "{rounded.sm}"
    padding: "0.12rem 0.45rem"
---

# Design System: Darin — Civic Evidence Desk

## 1. Overview

**Creative North Star: "The Inspection Desk"**

Darin is a public-records inspection desk for a live conversation. The call is the case under review; every card the copilot produces is a stamped record slid across the desk — case-labeled, dated, sourced, and legible in a single glance. The operator's attention still belongs to the human on the call; Darin's job is to lay the one line worth saying on the desk and keep the desk quiet.

**One identity, two materials.** The system ships as a single design language rendered in two materials, toggled from the masthead (◐) and persisted per user: **Desk** — warm record paper, navy ink, daylight — and **After Hours** — the same records office at night: near-black navy surfaces, lamplight-paper text, the same inks brightened to stay legible in the dark. Typography, shapes, spacing, component anatomy, and the signal vocabulary are identical in both; only the material tokens change. The OS color-scheme preference picks the starting material.

Color arrives the way it does on real paperwork — as stamp ink. Each ink is a signal with exactly one meaning, never a decoration: federal blue is interactive, ledger teal is the other party, ochre is urgency, approval green is live, inspection red is recording and stopping, notary violet is post-meeting analysis. Brass is the one non-signal — pure furniture (the masthead rule, fittings), never a message.

Everything that made Darin a HUD survives the change of material: glance-first hierarchy, the three-second ceiling on live text, split-attention density, strict signal semantics. This system still explicitly rejects chatbot UI — no bubbles, no avatar personality, no conversational framing — and SaaS dashboard chrome — no KPI widgets, no hero metrics, no analytics grid. It also rejects the AI-default look: no gradients, no glassmorphism, no neon or glow, no pill-shaped everything.

**Key Characteristics:**
- Warm paper (or lamplit navy) surfaces structured by hairline rules — flat, printed, physical
- Stamp-ink color as a strict signal vocabulary (six inks, each with one meaning; brass is furniture)
- Motion reserved for live state; paper never animates while nothing is happening
- Three-voice typography: Fraunces speaks (headlines, say-this), Libre Franklin explains (body), IBM Plex Mono files (labels, meta, transcript)
- Glance-first hierarchy: headline → say-this line → everything else subordinate

## 2. Colors: The Record Room Palette

A warm paper ground with navy ink and a fixed drawer of stamp inks — and its after-hours negative. Accents are used the way a records clerk uses them: sparingly, deliberately, always meaning the same thing.

### Ground & Ink — Desk
- **Record Paper** (#F4EADB): the page canvas. **Fresh Sheet** (#FBF6EC): cards, panels, modals. **Blotter** (#EFE3CC): recessed wells (transcript, output). **Manila** (#DFCAA8): hover fills, active folder tabs. **Sheet White** (#FFFDF7): inputs.
- **Rule Line** (#D6C8AB): every hairline border, 1px always; **Rule Strong** (#C4B491) for emphasis.
- **Navy Ink** (#17213A): primary text (13.4:1 on paper). **Second Ink** (#34415F): bullets. **Faded Ink** (#566074): meta, hints, timestamps (5.9:1 on fresh sheet).

### Ground & Ink — After Hours
- **Night Canvas** (#131926), **Night Sheet** (#1A2233), **Night Well** (#10151F), **Night Raised** (#232D42), **Night Input** (#161D2C), rules #2C3650 / #3A4763.
- **Lamplight Paper** (#EDE4D3): primary text (12.6:1 on night sheet). **Night Second Ink** (#C9CFDC), **Night Faded Ink** (#9AA3B5).

### Stamp Inks (the signal vocabulary — Desk / After Hours)
- **Federal Blue** (#4F78A6 / #7FA5CC): the interactive channel — actions, focus rings, links, the reactive lane, ME. **Text uses the ink step** (#33507A / #8FB2D6) — the Desk base blue is 3.9:1 on paper and fails AA; marks and borders use the base.
- **Ledger Teal** (#366B62 / #72B4A5): the other side of the call — THEM tags — and the proactive lane. Text-safe as-is.
- **Ochre Seal** (#8A6320 / #CE9E45): urgency only. Desk text-on-tint uses **#755416**. Distinct from Brass, which carries no meaning.
- **Approval Green** (#3F7249 / #7CBF8E): session-live — start stamp, active badge, armed dot. Desk text-on-tint uses **#335C3B**.
- **Inspection Red** (#B83A2E / #E08273): recording, stop/end, destructive. Desk text on manila/blotter uses **#9E2F24**.
- **Notary Violet** (#6B4E8E / #B195D2): the post-meeting register. Text-safe as-is.

### Furniture
- **Brass** (#C8AA6A, both materials): the masthead rule and fittings. **Never text on paper** (1.9:1) and never a signal. Brass text is allowed only on the navy masthead (7.2:1).
- **The Masthead** (#17213A with #EDE4D3 text, both materials): the desk's navy nameplate — the one surface the toggle does not change.

### Named Rules
**The One Meaning Rule.** Each stamp ink has exactly one semantic meaning and is prohibited elsewhere. If an ink appears without its meaning attached, it is a bug, not a style choice. Brass is exempt because brass means nothing — and must never be pressed into meaning something.

**The Stamp Rule.** Inks touch paper as tints (10–26% via `color-mix`) with a matching 1px tinted border, or as small solid marks (dots, seals, chips). Full-saturation fills are reserved for the three command buttons. No gradients, ever — ink doesn't fade mid-impression.

**The Ink-Step Rule.** Any accent used as text must use its designated `-text` token, verified ≥4.5:1 on its actual surface (all pairs machine-checked in both materials). Base hues are for marks; ink steps are for words.

**The Two-Materials Rule.** Components reference only semantic tokens (`--ink-*`, `--bg-*`, `--text*`); the theme switch swaps token values and nothing else. A component that hard-codes a material color, or that changes shape/typography/meaning between materials, is a bug.

## 3. Typography

**Display:** Fraunces (Georgia fallback) · **Body:** Libre Franklin (Segoe UI fallback) · **Docket:** IBM Plex Mono (Cascadia Mono fallback)

All three families are self-hosted woff2 under `web/static/fonts/` — the CSP (`font-src 'self'`) stays untouched; no CDNs. Fraunces and Franklin ship as variable fonts.

**Character:** Three voices with strict jobs. Fraunces *speaks* — only lines meant for a human ear: card headlines, the say-this line (italic — it is literally a quotation), modal titles, the wordmark. Libre Franklin *explains* — bullets, hints, buttons, settings. IBM Plex Mono *files* — everything that is a record: chips, timestamps, speaker tags, meta lines, the live transcript, streaming output, paths. The pairing sits on a contrast axis (soft serif + grotesque sans + typewriter mono); no two families compete for a job.

### Hierarchy
- **Display** (Fraunces 600, 1.25rem, tracked): the wordmark on the masthead; modal titles at 1.1rem.
- **Title** (Fraunces 600, 1rem, 1.3): card headlines — the one line read mid-call.
- **Say** (Fraunces 500 italic, 0.95rem, 1.45): the say-this line only. The quotation voice.
- **Body** (Franklin 400, 0.875rem, 1.55): bullets, hints, rows, general UI.
- **Longform** (Franklin 400, 1rem, 1.65, ≤70ch): post-meeting outputs only — the one surface read like an article, so it gets editorial sizing and measure.
- **Label** (Plex Mono 600, 0.7rem, 0.08em, UPPERCASE): section titles, the SAY label, docket entries.
- **Micro** (Plex Mono 600, 0.65rem, 0.06em, UPPERCASE): speaker tags and card-type chips.
- **Mono** (Plex Mono 400, 0.78rem, 1.55): live transcript, streaming output, paths, prompt templates.

### Named Rules
**The Three-Second Rule.** Any text the operator meets mid-call must land in under three seconds of split attention: headlines ≤60 characters, ≤3 bullets, no paragraphs in cards. Editorial sizing belongs only where the operator is off the call.

**The Voice Rule.** Fraunces only for what could be said aloud; Plex Mono only for what belongs in the record; Libre Franklin for everything between. A serif label or a mono headline is a bug.

## 4. Elevation

The system is flat — paper is flat, by day or by lamplight. Depth is drawn, not cast: 1px rules define every surface, and each material's tonal ladder (paper → sheet → blotter/manila; canvas → sheet → well/raised) encodes recession and elevation. Box shadows as material depth do not exist, with one exception: the toast, which floats over everything on a soft shadow (`--shadow-toast`, navy-tinted by day, black at night).

There is no glow anywhere — glow is projected light, and this system is ink. Liveness is a fresh stamp.

### Mark Vocabulary
- **Live dot** (9px solid disc, bright approval green in both materials — it sits on the navy masthead): watcher armed. Thinking swaps to the ochre seal with a slow opacity pulse.
- **REC stamp** (solid inspection-red disc, opacity pulse): recording in progress — the only permanently moving element during a session.
- **Attention seal** (`box-shadow` ring in inspection red at ≤30%, pulsed exactly twice via `attention-seal` keyframes): urgent `now` card arrival, then never again.
- **Toast float**: the single floating surface.

### Named Rules
**The Ink-Means-Alive Rule.** Motion and fresh marks are reserved for things that are live, armed, or urgent right now. Static paper never pulses, never animates, never shines. If something moves while nothing is happening, the signal vocabulary is corrupted.

## 5. Components

Crisp and clerical: hard 1px edges, stamped corners (2–3px, never pills), compact padding, terse mono labels, every state coded to the stamp-ink vocabulary. Transitions are utilitarian — 150ms on background/color/border. Every control has a real hover state and a visible 2px federal-blue focus ring (`outline-offset: 2px`; paper-colored on the masthead); every animation has a `prefers-reduced-motion` alternative.

### Buttons
- **Shape:** 2px radius, Franklin 600, 0.85rem, no wrap.
- **Command buttons** (solid stamps): Start = approval green; Stop/End = inspection red; Save = navy ink. On Desk they carry fresh-sheet labels; **After Hours inverts them** — bright ink fills (green #7CBF8E, red #E08273, blue #7FA5CC for Save) with near-black labels, because a dark navy fill on a dark page is invisible. Hover shifts one step (darker by day, brighter by night) via the `--btn-*-hover` tokens.
- **Action buttons** (tinted): federal blue at 14% with ink-step text and 35% border — the five reactive prompts. Ledger teal tints for custom prompts; notary violet for post-meeting.
- **Outline buttons:** transparent, 1px rule border; hover fills toward manila/raised. On the masthead they use paper-on-navy.
- **Busy state:** in-button spinner (0.8em, currentColor); label stays, button disables at 50%.

### Chips & Tags (docket stamps)
- **Card-type chips:** stamped rectangles (2px radius) — Micro mono, uppercase, 12% tint fill, 45% tinted border, ink-step text: answer = federal blue, fact check = ochre, reframe/deep dive = violet, next step = green, question/heads-up = teal, status = faded ink.
- **Speaker tags:** ME = federal blue, THEM = ledger teal; same stamped shape, Micro mono.
- **Cue badges:** neutral by default (blotter fill, rule border, ink text); they take the ochre seal only on urgent cards (One Meaning Rule).
- **State badge** (masthead): stamped mono tag with bright After-Hours ink text in both materials — it lives on navy.

### Cards / Containers (case pockets)
- 3px radius, fresh-sheet fill on 1px rule hairlines; recessed wells drop to blotter. No shadows.
- Internal padding: 1rem panels; 0.75rem 0.9rem copilot cards.

### Inputs / Fields
- Sheet-white fill (night: #161D2C), 1px rule border, 2px radius, ink text, faded-ink placeholders (≥4.5:1).
- Focus: border shifts federal blue with an 18% ring. Mono contexts (paths, templates, transcript) use the docket face.

### Navigation (the docket strip)
- **Masthead:** navy in both materials, closed by a 2px brass rule. Wordmark in Fraunces lamplight-paper; state badge, watcher dot, persona tabs, icon buttons (38px, paper-on-navy outline style), and the material toggle (◐).
- **Persona toggle:** a folder-tab strip, not a pill; the active tab fills manila with navy ink — the front folder in the drawer — in both materials.
- **Editor/context/history tabs (`ptabs`):** folder tabs sharing a baseline rule; active tab lifts to manila/raised and breaks the rule.

### The Copilot Card (signature component — the case pocket)
Reads top-down in glance order: type stamp + lane tag + dismiss → headline (Title, Fraunces, ≤60 chars, balanced) → the **say-this callout** — the payload, directly under the headline: federal-blue tinted strip, mono SAY label, the line in Fraunces italic, copy button → up to 3 bullets (Franklin, 72ch, second ink) → cue badges → the docket line (mono meta: source · age). Lane is the card's full 1px tinted border (federal blue 45% = reactive, ledger teal 45% = proactive); urgency escalates it to the ochre seal (55% soon, 80% now) and `now` pulses the red attention seal exactly twice on arrival. No side stripes — ever. Expired proactive cards fade over 0.7s; aged cards dim to 60% on a plain rule border, collapse to headline + cues, re-expand on click.

## 6. Do's and Don'ts

### Do:
- **Do** keep every stamp ink on its one meaning: federal blue = interactive/ME, ledger teal = THEM/proactive, ochre = urgent, approval green = go/live, inspection red = record/stop, notary violet = post-meeting. Brass means nothing and must stay meaningless.
- **Do** route every component color through the semantic tokens so both materials stay correct; verify new pairs ≥4.5:1 (text) / 3:1 (marks) in **both** materials before shipping.
- **Do** use the `-text` ink steps whenever an accent becomes text; base hues are for borders, seals, and tints.
- **Do** keep the case pocket's glance order intact: stamp → headline → say-this → bullets → cues → docket line. The say-this line is the payload and alone earns the italic serif.
- **Do** hold WCAG AA in both materials: visible focus rings, real hover states, `prefers-reduced-motion` alternatives for every pulse and card-in animation.

### Don't:
- **Don't** build anything that reads as **chatbot UI** — no bubbles, no avatar personality, no conversational framing. Darin is a records desk, not an interlocutor.
- **Don't** build anything that reads as a **SaaS dashboard** — no KPI grids, no hero metrics, no analytics chrome. The feed is a docket of moments, not a report.
- **Don't** use gradients, glassmorphism, neon, or glow — ink doesn't glow. Depth is drawn with rules, never cast (toast excepted).
- **Don't** make anything pill-shaped (≤3px radius everywhere), decorate with emoji, fake a control, or let the two materials drift apart in shape, type, or meaning.
- **Don't** cross the voices (no serif labels, no mono headlines) or exceed the Three-Second Rule on live surfaces: headlines ≤60 characters, ≤3 bullets, no paragraphs in cards.
