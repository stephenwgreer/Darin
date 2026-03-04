# NiceGUI Validation Spike

Tests 3 HoE conditions before committing to NiceGUI as Darin's UI framework.

## Conditions Tested

| Condition | What | Pass Criteria |
|---|---|---|
| 1 (DAR2-31) | COM threading: soundcard WASAPI + pywebview WebView2 | No crashes/dropouts in 10 min |
| 2 (DAR2-32) | Streaming latency at 50-100 chunks/sec | Avg < 100ms, no visible jank |
| 3 (DAR2-33) | PyInstaller packaging | Bundle < 120MB, runs on clean machine |

## Quick Start

```bash
cd spike/nicegui-validation
uv sync
uv run spike_app.py
```

## What the App Does

1. Opens a native desktop window (NiceGUI + pywebview using Edge WebView2)
2. Starts soundcard loopback capture in a background thread (WASAPI/COM)
3. Shows live audio level meter — proves both COM consumers coexist
4. Has a streaming benchmark button that pushes 50-100 text chunks/sec to the UI
5. Measures latency of each UI update
6. Runs a 10-minute stability timer
7. "Export Results" button writes a pass/fail report

## Testing Procedure

1. Start the app
2. Play some audio on your PC (YouTube, Spotify, etc.) to verify audio capture works
3. Click "Start Streaming Benchmark" to test streaming latency
4. Let it run for 10 minutes minimum
5. Click "Export Results" to get the pass/fail report
6. Check `spike_results.txt` for the full report

## Condition 3: Packaging

After Conditions 1-2 pass:

```bash
uv add --group dev pyinstaller
uv run pyinstaller --onefile spike_app.py
```

Check `dist/spike_app.exe` size and run on a clean machine.

## If It Fails

If COM threading conflicts → we stay on PyQt6 with custom QSS styling.
See DAR2-28 in Linear for fallback plan.
