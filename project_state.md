## Current Project State

**Product Name**: Darin Audio Assistant
**Tech Stack**: Python 3.8+ / PyQt6 desktop app, Deepgram speech-to-text API, Anthropic Claude API, QWebEngineView for HTML rendering, sounddevice/numpy for audio capture
**Current Sprint**: No formal sprint tracking in place (solo developer, commit-driven workflow)
**Sprint Goals**: N/A — development follows an iterative daily-commit cadence

**In Progress**:
- Project documentation and state tracking (current branch: `claude/document-project-state-jgDow`)
- Prompt flow refinements (most recent code commits on Apr 25)

**Blocked**:
- Model inconsistency: `api/client.py` hardcodes `claude-3-opus-20240229` while `config.py` specifies `claude-3-7-sonnet-20250219` — unclear which is intended at runtime
- No API key validation on startup — missing keys cause cryptic errors downstream
- HTML streaming parser is fragile; malformed AI output can break rendering

**Completed Recently**:
- Rolled out HTML stream handlers into separate folder for better modularity (Apr 24)
- Added comprehensive `project_context.md` documentation (Apr 23)
- Prompt engineering pass across all analysis types: meeting summary, practitioner insights, brainstorming, SAS alignment, fact checking (Apr 1)
- Added 5 structured logic frameworks: SCQA, First Principles, Hypothesis-Driven, Issue Tree, Reframing (Apr 3)
- Added "Answer Question" feature that identifies the last question in a transcript and provides analysis (Apr 3)
- Animated title label and UI heading size refinements (Apr 3–4)
- Removed standalone transcript panel in favor of unified output view (Mar 24)
- Migrated output from plain markdown to rich HTML rendering via QWebEngineView (Mar 18–25)
- Implemented real-time streaming text from Claude API with chunked HTML parsing (Mar 18)
- Added sentiment analysis, fact checking, and follow-up question prompts (Mar 23–24)

**Next Up**:
- Resolve hardcoded model name inconsistency between `api/client.py` and `config.py`
- Add startup validation for required API keys (Deepgram, Anthropic) with user-facing error messages
- Add session persistence / export — analysis results are currently lost when the app closes
- Add retry logic and error handling for Deepgram and Anthropic API calls
- Evaluate thread safety around `current_transcript` shared state
- Reduce complexity in `main_window.py` (1,367 lines) by further extracting stream handler logic
- Consider adding the ability to save/export analysis results (HTML, markdown, or text)
