---
name: Darin
description: Civic Evidence Desk design system for a real-time meeting copilot — warm record paper, stamp-ink signals, docket typography
colors:
  record-paper: "#F4EADB"
  fresh-sheet: "#FBF6EC"
  blotter: "#EFE3CC"
  manila: "#DFCAA8"
  rule-line: "#D6C8AB"
  navy-ink: "#17213A"
  faded-ink: "#566074"
  federal-blue: "#4F78A6"
  federal-blue-ink: "#33507A"
  ledger-teal: "#366B62"
  ochre-seal: "#8A6320"
  approval-green: "#3F7249"
  inspection-red: "#B83A2E"
  inspection-red-ink: "#9E2F24"
  notary-violet: "#6B4E8E"
  brass: "#C8AA6A"
typography:
  display:
    fontFamily: "'Fraunces', Georgia, 'Times New Roman', serif"
    fontSize: "1.25rem"
    fontWeight: 600
    letterSpacing: "0.01em"
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
    fontSize: "1.36rem"
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
    fontSize: "0.8rem"
    lineHeight: 1.5
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
    backgroundColor: "#FFFDF7"
    textColor: "{colors.navy-ink}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 0.9rem"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.faded-ink}"
    rounded: "{rounded.sm}"
    padding: "0.1rem 0.45rem"
---

# Design System: Darin — Civic Evidence Desk

## 1. Overview

**Creative North Star: "The Inspection Desk"**

Darin is a public-records inspection desk for a live conversation. The call is the case under review; every card the copilot produces is a stamped record slid across warm paper — case-labeled, dated, sourced, and legible in a single glance. The operator's attention still belongs to the human on the call; Darin's job is to lay the one line worth saying on the desk and keep the desk quiet.

The aesthetic is a records office, not a cockpit: warm record paper instead of deep space, navy ink instead of signal white, hairline rules and manila tabs instead of glowing hull lines. Color arrives the way it does on real paperwork — as stamp ink. Each ink is a signal with exactly one meaning, never a decoration: federal blue is interactive, ledger teal is the other party, ochre is urgency, approval green is live, inspection red is recording and stopping, notary violet is post-meeting analysis. Brass is the one non-signal — pure furniture (tabs, rules, fittings), never a message.

Everything that made Darin a HUD survives the change of material. Glance-first hierarchy, the three-second ceiling on live text, split-attention density, and the strict signal vocabulary all carry over; only the world they render in changes — from projected light to stamped ink.

This system still explicitly rejects chatbot UI — no bubbles, no avatar personality, no conversational framing — and SaaS dashboard chrome — no KPI widgets, no hero metrics, no analytics grid. It also rejects the AI-default look: no gradients, no glassmorphism, no neon or glow, no pill-shaped everything.

**Key Characteristics:**
- Warm paper surfaces structured by hairline rules and manila tabs — flat, printed, physical
- Stamp-ink color as a strict signal vocabulary (six inks, each with one meaning; brass is furniture)
- Motion reserved for live state; paper never animates while nothing is happening
- Three-voice typography: Fraunces speaks (headlines, the say-this line), Libre Franklin explains (body), IBM Plex Mono files (labels, meta, transcript)
- Glance-first hierarchy: headline → say-this line → everything else subordinate

## 2. Colors: The Record Room Palette

A warm paper ground with navy ink and a fixed drawer of stamp inks. Accents are used the way a records clerk uses them: sparingly, deliberately, and always meaning the same thing.

### Ground & Ink
- **Record Paper** (#F4EADB): The page canvas — the desk itself.
- **Fresh Sheet** (#FBF6EC): The standard surface — cards, panels, modals. A clean document lying on the desk.
- **Blotter** (#EFE3CC): Recessed wells — transcript bodies, output panels, path inputs.
- **Manila** (#DFCAA8): The interaction layer — hover fills, active tabs, folder-tab accents.
- **Rule Line** (#D6C8AB): Every hairline border and divider. 1px, always. Strong dividers use Navy Ink at 25% alpha.
- **Navy Ink** (#17213A): Primary text and the inverted masthead surface. 13.4:1 on Record Paper.
- **Faded Ink** (#566074): Secondary text, hints, timestamps, dismissed states. 5.4:1 on Fresh Sheet.

### Stamp Inks (the signal vocabulary)
- **Federal Blue** (#4F78A6): The interactive channel — primary actions, focus rings, links, the reactive lane, ME speaker tags. **Text uses Federal Blue Ink** (#33507A) — the base blue is 3.9:1 on paper and fails AA; the ink step clears 4.5:1 on every surface up to Manila. The base hue is for borders, seals, and tints only.
- **Ledger Teal** (#366B62): The other side of the call — THEM speaker tags — and the proactive lane (watcher cards, custom actions). Text-safe on paper (5.1:1).
- **Ochre Seal** (#8A6320): Urgency. `urgency=soon/now` seals, cue badges on urgent cards, over-budget warnings, the watcher's thinking state. An aged rubber-stamp amber — distinct from Brass, which carries no meaning. Text-safe on paper (4.5:1).
- **Approval Green** (#3F7249): Session-live signals — the start stamp, active badge, watcher-armed dot, completion checks. Text-safe on paper (4.8:1).
- **Inspection Red** (#B83A2E): Recording, stop/end, destructive actions. The hottest ink on the desk. **Text on Manila or Blotter uses Inspection Red Ink** (#9E2F24); base red passes on paper (4.8:1) but not on darker warm surfaces.
- **Notary Violet** (#6B4E8E): The post-meeting register — analysis buttons and the post-meeting badge. Text-safe on paper (5.7:1).

### Furniture
- **Brass** (#C8AA6A): Folder tabs, decorative rules, the masthead fittings. **Never text on paper** (1.9:1) and never a signal. Brass text is allowed only on Navy Ink (7.2:1) — masthead docket labels.

### Named Rules
**The One Meaning Rule.** Each stamp ink has exactly one semantic meaning and is prohibited elsewhere. If an ink appears without its meaning attached, it is a bug, not a style choice. Brass is exempt because brass means nothing — and must never be pressed into meaning something.

**The Stamp Rule.** Inks touch paper the way stamps do: as tints (8–25% alpha) with a matching 1px tinted border, or as small solid marks (dots, seals, chips). Full-saturation fills are reserved for the three command buttons (start, stop, save). No gradients, ever — ink doesn't fade mid-impression.

**The Ink-Step Rule.** Any accent used as text must use its designated ink step (Federal Blue Ink, Inspection Red Ink) or be verified ≥4.5:1 on its actual surface. The palette's display hues are for marks; the ink steps are for words.

## 3. Typography

**Display Font:** Fraunces (Georgia, serif fallback) — headlines, the wordmark, and italic moments
**Body Font:** Libre Franklin (Segoe UI, system-ui fallback) — running text and UI copy
**Docket Font:** IBM Plex Mono (Cascadia Mono, ui-monospace fallback) — labels, meta, timestamps, speaker tags, transcript, streaming output, paths

All three families are self-hosted as woff2 under `web/static/fonts/` — the CSP (`default-src 'self'`) stays untouched; no font CDNs.

**Character:** Three voices with strict jobs. Fraunces *speaks* — it carries only the lines meant for a human ear: card headlines and the say-this line (which sets in italic, because it is literally a quotation). Libre Franklin *explains* — bullets, hints, settings, buttons. IBM Plex Mono *files* — everything that is a record: case labels, timestamps, speaker tags, confidence marks, the live transcript, streaming output. The pairing works on a contrast axis (soft serif + grotesque sans + typewriter mono); no two families compete for the same job.

### Hierarchy
- **Display** (Fraunces 600, 1.25rem): The wordmark and modal titles.
- **Title** (Fraunces 600, 1rem, 1.3): Card headlines — the one line the operator reads mid-call.
- **Say** (Fraunces 500 italic, 0.95rem, 1.45): The say-this line only. The quotation voice.
- **Body** (Libre Franklin 400, 0.875rem, 1.55): Card bullets, hints, list rows, general UI text.
- **Longform** (Libre Franklin 400, 1.36rem ≈ 19px, 1.65, ≤70ch): Post-meeting outputs only — summaries, action items, key decisions. The one surface where Darin is read like an article, so it obeys editorial rules: ≥19px, line-height ≥1.6, measured column.
- **Label** (Plex Mono 600, 0.7rem, 0.08em, UPPERCASE): Section titles, the SAY label, docket-strip entries.
- **Micro** (Plex Mono 600, 0.65rem, 0.06em, UPPERCASE): Speaker tags and card-type chips.
- **Mono** (Plex Mono 400, 0.8rem, 1.5): Live transcript, streaming LLM output, file paths, prompt templates.

### Named Rules
**The Three-Second Rule.** Any text element the operator meets mid-call must land in under three seconds of split attention. Card headlines stay ≤60 characters; bullets stay ≤3 lines; if it needs study, it must be restructured or demoted to post-meeting output. The 19px editorial floor applies only where the operator is off the call.

**The Voice Rule.** Fraunces only for what could be said aloud; Plex Mono only for what belongs in the record; Libre Franklin for everything between. A serif label or a mono headline is a bug.

## 4. Elevation

The system is flat — paper is flat. Depth is drawn, not cast: 1px Rule Line hairlines define every surface, and the warm ladder (Record Paper → Fresh Sheet → Blotter → Manila) encodes recession and elevation tonally. Folder-tab offsets (a surface breaking its parent's top rule) are the only allowed dimensional gesture. Box shadows as material depth do not exist, with one pragmatic exception: the toast, which floats over everything and carries a soft warm shadow (`0 6px 24px rgba(23,33,58,0.18)`) to separate from the page.

There is no glow anywhere — glow is projected light, and this system is ink. Liveness is shown the way a records office shows it: with a fresh stamp.

### Mark Vocabulary
- **Live dot** (9px solid Approval Green disc): watcher armed. Thinking swaps to Ochre Seal with a slow opacity pulse.
- **REC stamp** (solid Inspection Red disc, opacity pulse 1→0.45): recording in progress. The only permanently moving element during a session.
- **Attention seal** (`box-shadow: 0 0 0 3px rgba(184,58,46,0.22)`, pulsed exactly twice): urgent card arrival, then never again.
- **Toast float** (`0 6px 24px rgba(23,33,58,0.18)`): the single floating surface.

### Named Rules
**The Ink-Means-Alive Rule.** Motion and fresh marks are reserved for things that are live, armed, or urgent right now. Static paper never pulses, never animates, never shines. If something moves while nothing is happening, the signal vocabulary is corrupted.

## 5. Components

Crisp and clerical: hard 1px edges, near-square corners (2–3px — stamped, not lozenged), compact padding, terse mono labels, every state coded to the stamp-ink vocabulary. Transitions are utilitarian — 150ms on background, color, and border, nothing choreographed. Every interactive element has a real hover state and a visible 2px Federal Blue focus ring (`outline-offset: 2px`); every animation has a `prefers-reduced-motion` alternative.

### Buttons
- **Shape:** 2px radius, Libre Franklin 600, 0.85rem, no text wrap.
- **Command buttons** (solid stamps): Start = Approval Green; Stop/End = Inspection Red; Save = Navy Ink — all with Fresh Sheet text. Hover darkens one step. These are the only full-saturation surfaces in the UI.
- **Action buttons** (tinted): Federal Blue at 14% alpha, Federal Blue Ink text, 1px 35%-alpha border — the five reactive prompts. Ledger Teal tints for custom prompts; Notary Violet tints for post-meeting prompts. Hover deepens the tint.
- **Outline buttons:** Transparent, 1px Rule Line border, Navy Ink text; hover fills Manila at 40%.
- **Busy state:** In-button spinner (0.8em, currentColor ring); label stays, button disables at 50% opacity. No global lock.

### Chips & Tags (docket stamps)
- **Style:** 2px radius — **not pills** — Micro mono type, uppercase, 1px solid border in the type's ink with an 10–14% tint fill: answer = Federal Blue, fact check = Ochre Seal, reframe = Notary Violet, next step = Approval Green, heads-up = Ledger Teal, status = Faded Ink. They read as small rubber stamps on the record.
- **Speaker tags:** ME = Federal Blue Ink on blue tint; THEM = Ledger Teal on teal tint. Same stamped-tag shape, Micro mono.
- **Cue badges:** Neutral by default (Blotter fill, Rule Line border, Navy Ink text). They turn Ochre Seal only on urgent cards, keeping ochre's one meaning intact.

### Cards / Containers (case pockets)
- **Corner Style:** 3px radius.
- **Background:** Fresh Sheet on 1px Rule Line hairlines; recessed wells (output, transcript bodies) drop to Blotter.
- **Shadow Strategy:** None — flat per the Ink-Means-Alive Rule.
- **Internal Padding:** 1rem panels; 0.75rem 0.9rem copilot cards.

### Inputs / Fields
- **Style:** Near-white warm fill (#FFFDF7), 1px Rule Line border, 2px radius, Navy Ink text, Faded Ink placeholders (verified ≥4.5:1).
- **Focus:** Border shifts to Federal Blue with a 2px ring at 15% alpha.
- **Disabled:** 50% opacity, not-allowed cursor.
- **Mono contexts:** Paths, prompt templates, and transcript render in Plex Mono.

### Navigation (the docket strip)
- **Style:** A single sticky masthead inverted to Navy Ink: the wordmark in Fraunces (Fresh Sheet), docket entries in Brass Plex Mono uppercase, the state badge as a stamped tag (idle = Faded Ink / active = Approval Green / post-meeting = Notary Violet), the watcher dot, and outline icon buttons. The masthead is the one dark surface — the desk's brass-and-navy nameplate above the paper.
- **Persona toggle:** A folder-tab strip, not a pill: three square-cornered tabs sharing a baseline rule; the active tab fills Manila and breaks the rule, like the front folder in a drawer.

### The Copilot Card (signature component — the case pocket)
The core element. Reads top-down in glance order: type stamp + lane tag + dismiss → headline (Title, Fraunces, ≤60 chars, balanced wrap) → the **say-this callout** — the payload, directly under the headline: a Federal Blue-tinted strip with the mono SAY label, the suggested line in Fraunces italic (the quotation voice), and a copy button — → up to 3 supporting bullets (Libre Franklin, 72ch measure, one step toward Faded Ink) → cue badges → the docket line (Plex Mono meta: source · age — the card's filing record). Lane is encoded in the card's full 1px tinted border (Federal Blue = reactive, Ledger Teal = proactive); urgency escalates the border to Ochre Seal (35% alpha for soon, 55% for now). No side stripes — ever. Urgent NOW cards pulse the red attention seal exactly twice on arrival. Expired proactive cards fade over 0.7s; aged cards dim to 60% on a Rule Line border, collapse to headline + cue badges, and re-expand on click.

## 6. Do's and Don'ts

### Do:
- **Do** keep every stamp ink on its one meaning: federal blue = interactive/ME, ledger teal = THEM/proactive, ochre = urgent, approval green = go/live, inspection red = record/stop, notary violet = post-meeting. Brass means nothing and must stay meaningless.
- **Do** apply inks as tints (8–25% alpha) with matching tinted borders or as small solid marks; save solid fills for start/stop/save commands.
- **Do** use the ink steps (Federal Blue Ink #33507A, Inspection Red Ink #9E2F24) whenever an accent becomes text; verify ≥4.5:1 on the actual surface.
- **Do** keep the copilot card's glance order intact: stamp → headline → say-this → bullets → cues → docket line. The say-this line is the payload; it must survive any redesign — and it alone earns the italic serif.
- **Do** hold WCAG AA: 4.5:1 for body text, 3:1 for large text, visible Federal Blue focus rings, real hover states on every control, and `prefers-reduced-motion` alternatives for every pulse and card-in animation.

### Don't:
- **Don't** build anything that reads as **chatbot UI** — no message bubbles, no avatar personality, no conversational framing. Darin is a records desk, not an interlocutor.
- **Don't** build anything that reads as a **SaaS dashboard** — no KPI-widget grids, no hero metrics, no analytics chrome. The feed is a docket of moments, not a report.
- **Don't** use gradients, glassmorphism, translucent blurs, neon, or glow — ink doesn't glow. Depth is drawn with rules and tabs, never cast (toast excepted).
- **Don't** make anything pill-shaped. Chips, tags, badges, and toggles are stamped rectangles (≤3px radius). No emoji as decoration, no fake controls, no imagery containing readable fake text.
- **Don't** cross the voices: no serif labels, no mono headlines, no sans say-this. And don't exceed the Three-Second Rule on any live-surface text: headlines ≤60 characters, ≤3 bullets, no paragraphs in cards — the 19px editorial floor belongs to post-meeting output only.
