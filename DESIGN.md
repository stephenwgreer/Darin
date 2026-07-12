---
name: Darin
description: Dark HUD design system for a real-time meeting copilot
colors:
  deep-space: "#0f1117"
  console-panel: "#1a1d27"
  console-raised: "#22253a"
  hull-line: "#2e3347"
  signal-white: "#e2e8f0"
  dim-signal: "#8892a4"
  radar-blue: "#3b82f6"
  radar-blue-deep: "#2563eb"
  radar-blue-text: "#60a5fa"
  analysis-purple-text: "#c084fc"
  go-green: "#22c55e"
  alert-red: "#ef4444"
  caution-amber: "#f59e0b"
  analysis-purple: "#a855f7"
  contact-teal: "#14b8a6"
  standby-grey: "#6b7280"
typography:
  headline:
    fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    letterSpacing: "0.15em"
  title:
    fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 650
    lineHeight: 1.35
  body:
    fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif"
    fontSize: "0.85rem"
    lineHeight: 1.5
  label:
    fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif"
    fontSize: "0.7rem"
    fontWeight: 700
    letterSpacing: "0.08em"
  micro:
    fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif"
    fontSize: "0.62rem"
    fontWeight: 700
    letterSpacing: "0.06em"
  mono:
    fontFamily: "'Cascadia Mono', ui-monospace, monospace"
    fontSize: "0.8rem"
rounded:
  sm: "0.35rem"
  md: "0.5rem"
  pill: "999px"
spacing:
  xs: "0.3rem"
  sm: "0.5rem"
  md: "0.75rem"
  lg: "1rem"
  xl: "1.5rem"
components:
  button-primary:
    backgroundColor: "{colors.radar-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "0.45rem 1rem"
  button-primary-hover:
    backgroundColor: "{colors.radar-blue-deep}"
  button-go:
    backgroundColor: "{colors.go-green}"
    textColor: "#000000"
    rounded: "{rounded.sm}"
    padding: "0.45rem 1rem"
  button-stop:
    backgroundColor: "{colors.alert-red}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    padding: "0.45rem 1rem"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.signal-white}"
    rounded: "{rounded.sm}"
    padding: "0.45rem 1rem"
  button-action:
    backgroundColor: "#3b82f626"
    textColor: "{colors.radar-blue}"
    rounded: "{rounded.sm}"
    padding: "0.42rem 0.9rem"
  card:
    backgroundColor: "{colors.console-panel}"
    rounded: "{rounded.md}"
    padding: "0.75rem 0.9rem"
  input:
    backgroundColor: "{colors.console-raised}"
    textColor: "{colors.signal-white}"
    rounded: "{rounded.sm}"
    padding: "0.55rem 0.9rem"
  chip:
    backgroundColor: "#6b728033"
    textColor: "{colors.dim-signal}"
    rounded: "{rounded.pill}"
    padding: "0.12rem 0.5rem"
---

# Design System: Darin

## 1. Overview

**Creative North Star: "The Heads-Up Display"**

Darin is a fighter-pilot HUD for a live conversation: information overlaid on reality, glanceable in under a second, never the mission itself. The operator's attention belongs to the human on the call; Darin's job is to project the one line worth saying onto the glass and then get out of the way. Everything in the system serves split attention — short line lengths, loud state coding, quiet chrome.

The aesthetic is a dark console: a Deep Space canvas, flat panels drawn with hairline borders, and a strict semantic color vocabulary where every hue is a signal, never a decoration. Blue means interactive or reactive, teal means the other party or proactive insight, amber means urgency, green means go, red means recording or stop, purple means post-meeting analysis. Light itself is a status: things glow only when they are live.

This system explicitly rejects chatbot UI — no bubbles, no avatar personality, no conversational framing — and SaaS dashboard chrome — no KPI widgets, no hero metrics, no analytics grid. It is an instrument, and it reads like one.

**Key Characteristics:**
- Dark, flat, border-structured console surfaces
- Semantic color as a strict signal vocabulary (six accents, each with one meaning)
- Glow and pulse reserved for live state; static UI never glows
- Dense, crisp, instrument-panel typography in a single family
- Glance-first hierarchy: headline → say-this line → everything else subordinate

## 2. Colors: The Deep Space Palette

A near-black blue-violet canvas with one interactive accent and a six-signal semantic set, all applied as translucent tints over the dark hull.

### Primary
- **Radar Blue** (#3b82f6): The interactive channel. Primary buttons, focus rings, reactive-lane accents, and the wordmark. Hover deepens to **Radar Blue Deep** (#2563eb). At 8–35% alpha it tints action buttons, chips, and the say-this callout. **Text sitting ON a tint uses Radar Blue Text** (#60a5fa) — the base blue lands under 4.5:1 on tinted fills; the ramp step clears it. Same pattern for purple chip text (**#c084fc**).

### Secondary
- **Contact Teal** (#14b8a6): The other side of the call — THEM speaker tags — and the proactive lane (watcher cards, custom actions).
- **Caution Amber** (#f59e0b): Urgency. `urgency=now` cards, cue badges, over-budget warnings, the watcher's "thinking" state.
- **Go Green** (#22c55e): Session-live signals. Start button, active badge, watcher-armed dot, completion checks.
- **Alert Red** (#ef4444): Recording indicator, stop/end actions, destructive buttons.
- **Analysis Purple** (#a855f7): The post-meeting register — analysis buttons and the post-meeting badge.

### Neutral
- **Deep Space** (#0f1117): The page canvas and recessed wells (output panels, path inputs).
- **Console Panel** (#1a1d27): The standard surface — header, cards, modals.
- **Console Raised** (#22253a): The interaction layer — inputs, hover fills, active tabs.
- **Hull Line** (#2e3347): Every border and divider. 1px, always.
- **Signal White** (#e2e8f0): Primary text.
- **Dim Signal** (#8892a4): Secondary text, labels, hints, timestamps.
- **Standby Grey** (#6b7280): Idle/neutral states — stopped watcher, aged cards, neutral chips.

### Named Rules
**The One Meaning Rule.** Each accent has exactly one semantic meaning and is prohibited elsewhere. If a color appears without its meaning attached, it is a bug, not a style choice.

**The Tint Rule.** Accents touch the dark hull as translucent tints (8–35% alpha) with a matching tinted 1px border; full-saturation fills are reserved for the few solid command buttons (start, stop, save).

## 3. Typography

**UI Font:** Segoe UI (with system-ui, -apple-system, sans-serif fallbacks)
**Mono Font:** Cascadia Mono (with ui-monospace fallback) — streaming output, paths, prompt templates

**Character:** One instrument face at high density. A single familiar sans carries everything; hierarchy comes from weight, size, case, and letterspacing — never from a second family. The root is 14px, and most UI text sits between 0.7rem and 0.95rem: compact, crisp, readable at a glance.

### Hierarchy
- **Headline** (700, 1.25rem, 0.15em tracking): The wordmark only.
- **Title** (650, 0.95rem, 1.35): Card headlines — the one line the operator reads mid-call.
- **Body** (400, 0.85rem, 1.5): Card bullets, hints, list rows, general UI text.
- **Label** (700, 0.7rem, 0.08em tracking, UPPERCASE): Section titles, output titles, the SAY label.
- **Micro** (700, 0.62rem, 0.06em tracking, UPPERCASE): Speaker tags and card-type chips.
- **Mono** (400, 0.8rem): Streaming LLM output, file paths, prompt template editors.

### Named Rules
**The Three-Second Rule.** Any text element the operator meets mid-call must land in under three seconds of split attention. Card headlines stay ≤60 characters; bullets stay ≤3 lines; if it needs study, it must be restructured or demoted to post-meeting output.

## 4. Elevation

The system is flat. Depth is drawn, not cast: 1px Hull Line borders define every surface, and the three-step neutral ladder (Deep Space → Console Panel → Console Raised) encodes recession and elevation tonally. Box shadows as material depth do not exist — with one pragmatic exception (the toast, which floats over everything and carries a soft dark shadow to separate from the page).

Glow is the only other light in the system, and it is a status signal, not decoration: the watcher dot glows green when armed and pulses amber when thinking; `urgency=now` cards pulse a brief amber ring twice on arrival; the REC dot pulses red while capturing.

### Shadow Vocabulary
- **Live glow** (`box-shadow: 0 0 6px rgba(34,197,94,0.7)` green / `rgba(245,158,11,0.7)` amber): 9px status dots only — armed and thinking states.
- **Attention ring** (`box-shadow: 0 0 0 3px rgba(245,158,11,0.25)`, pulsed twice): urgent card arrival, then never again.
- **Toast float** (`box-shadow: 0 6px 24px rgba(0,0,0,0.45)`): the single floating surface.

### Named Rules
**The Glow-Means-Alive Rule.** Light is reserved for things that are live, armed, or urgent right now. Static UI never glows, never pulses, never casts. If an element shines while nothing is happening, the signal vocabulary is corrupted.

## 5. Components

Crisp and instrumental: hard 1px edges, compact padding, terse labels, every state color-coded to the signal vocabulary. Transitions are utilitarian — 150ms on background and color, nothing choreographed.

### Buttons
- **Shape:** Tight corners (0.35rem radius), 600 weight, 0.85rem text, no text wrap.
- **Command buttons** (solid fills): Start = Go Green with black text; Stop = Alert Red; Save = Radar Blue. Hover shifts one step darker. These are the only full-saturation surfaces in the UI.
- **Action buttons** (tinted): Radar Blue at 15% alpha with a 35%-alpha border for the five reactive prompts; Contact Teal tints for custom prompts; Analysis Purple tints for post-meeting prompts. Hover doubles the tint.
- **Outline buttons:** Transparent with a Hull Line border; hover fills Console Raised.
- **Busy state:** An in-button spinner (0.8em, currentColor ring) replaces nothing — the label stays, the button disables at 45% opacity. No global lock.

### Chips
- **Style:** Pill-shaped (999px), Micro type, translucent tint + matching text color per card type: answer = blue, fact check = amber, reframe = purple, next step = green, heads-up = teal, status = grey.
- **Speaker tags:** ME = Radar Blue tint, THEM = Contact Teal tint; pill, 0.62rem, bold.
- **Cue badges:** Neutral by default (Console Raised fill, Hull Line border) — instant-glance keywords without stealing the urgency channel. They turn Caution Amber only on urgent cards, keeping amber's one meaning intact.

### Cards / Containers
- **Corner Style:** 0.5rem radius.
- **Background:** Console Panel on 1px Hull Line borders; recessed wells (output, transcript bodies) drop to Deep Space.
- **Shadow Strategy:** None — flat per the Glow-Means-Alive Rule.
- **Internal Padding:** 1rem panels; 0.75rem 0.9rem copilot cards.

### Inputs / Fields
- **Style:** Console Raised fill (forms drop to Deep Space in modals), 1px Hull Line border, 0.35rem radius, Signal White text.
- **Focus:** Border shifts to Radar Blue with a 2px blue ring at 15% alpha.
- **Disabled:** 45% opacity, not-allowed cursor.
- **Mono contexts:** Paths and prompt templates render in the mono face.

### Navigation
- **Style:** A single sticky header on Console Panel: round logo, tracked wordmark in Radar Blue, state badge (pill, tinted per state: idle grey / active green / post-meeting purple), watcher dot, persona segmented pill, icon buttons (38px square, outline style).
- **Persona toggle:** A segmented pill; the active segment fills with a Radar Blue tint.

### The Copilot Card (signature component)
The core HUD element. Reads top-down in glance order: type chip + lane tag + dismiss → headline (Title, ≤60 chars, balanced wrap) → the **say-this callout** — the payload, directly under the headline: a blue-tinted strip with the SAY label, the suggested line in italics, and a copy button — → up to 3 supporting bullets (72ch measure, one step muted) → cue badges → meta line. Lane is encoded in the card's full 1px tinted border (blue = reactive, teal = proactive); urgency escalates the border to amber (35% alpha for soon, 55% for now). No side stripes — ever. Urgent NOW cards pulse the amber attention ring twice on arrival. Expired proactive cards fade over 0.7s; aged cards dim to 60% on a neutral border, collapse to headline + cue badges, and re-expand on click.

## 6. Do's and Don'ts

### Do:
- **Do** keep every accent on its one meaning: blue = interactive/ME, teal = THEM/proactive, amber = urgent, green = go/live, red = record/stop, purple = post-meeting. Cite the One Meaning Rule.
- **Do** apply accents as translucent tints (8–35% alpha) with matching tinted borders; save solid fills for start/stop/save commands.
- **Do** reserve glow and pulse for live state — armed watcher, active recording, urgent arrival — and let it end (the attention ring pulses exactly twice).
- **Do** keep the copilot card's glance order intact: chip → headline → bullets → say-this → meta. The say-this line is the payload; it must survive any redesign.
- **Do** hold WCAG AA: 4.5:1 for body text, 3:1 for large text, visible Radar Blue focus rings, and `prefers-reduced-motion` alternatives for pulse and card-in animations.

### Don't:
- **Don't** build anything that reads as **chatbot UI** — no message bubbles, no avatar with personality, no conversational back-and-forth framing. Darin is an instrument, not an interlocutor.
- **Don't** build anything that reads as a **SaaS dashboard** — no KPI-widget grids, no hero metrics, no analytics chrome. The feed is a stream of moments, not a report.
- **Don't** let static elements glow, pulse, or animate while nothing is happening; ambient motion competes with the call.
- **Don't** introduce a second font family, cast material shadows on panels, or use an accent color outside its assigned meaning.
- **Don't** exceed the Three-Second Rule on any live-surface text: headlines ≤60 characters, ≤3 bullets, no paragraphs in cards.
