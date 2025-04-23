# Project Context: Darin Audio Assistant

## 1. Project Summary

Darin Audio Assistant is a desktop application built with Python and PyQt6. Its primary function is to record audio conversations, transcribe them in real-time (or near real-time), and leverage AI (specifically Anthropic's Claude models via their API) to analyze the transcript and provide various insights. It acts as an intelligent assistant for meetings, interviews, or any scenario requiring audio capture and analysis.

## 2. Objectives

*   Record audio continuously with a configurable rolling buffer (currently 3 minutes).
*   Transcribe audio using Deepgram's speech-to-text service.
*   Analyze transcripts using Claude AI for tasks like:
    *   Generating meeting summaries.
    *   Identifying key topics.
    *   Extracting practitioner insights (e.g., for banking).
    *   Suggesting follow-up questions.
    *   Performing sentiment analysis.
    *   Fact-checking claims.
    *   Identifying gaps in reasoning.
    *   Brainstorming related ideas.
    *   Assessing alignment with specific contexts (e.g., SAS Viya).
    *   Answering user questions based on the transcript.
    *   Applying structured thinking frameworks (Issue Tree, SCQA, Hypothesis-Driven, First Principles, Reframing).
*   Provide a user-friendly desktop interface using PyQt6.
*   Display analysis results in a formatted, readable way using HTML/CSS within a QWebEngineView.
*   Support streaming output from the AI for a more interactive experience.

## 3. Project Structure

The project follows a modular structure:

```
audio_test/
├── api/                # API client implementations (Anthropic, Deepgram)
│   └── client.py
├── audio/             # Audio recording (ContinuousRecorder)
│   └── recorder.py
├── assets/            # Images (logos, icons), static resources
├── prompts/           # AI prompt templates and logic definitions
│   ├── templates.py
│   └── logic_templates.py
├── ui/                # PyQt6 UI components
│   ├── main_window.py      # Main application window, orchestrates UI and logic
│   ├── controls_panel.py   # Left panel with buttons (Record, Transcribe, Prompts)
│   ├── output_panel.py     # Right panel displaying transcripts and AI results (HTML)
│   ├── animated_label.py   # Simple animation for the title
│   └── font_manager.py     # Utility for loading custom fonts
├── main.py           # Application entry point (initializes QApplication, MainWindow)
├── config.py         # Configuration (API keys from .env, audio settings, model params)
├── utils.py          # Utility functions (e.g., formatting)
├── requirements.txt  # Python dependencies
├── readme.md         # Project overview, setup, usage
├── project_context.md # This file - summary for LLM context
└── .env              # (Not committed) Stores API keys
```

## 4. Key Components & Logic Flow

1.  **Entry Point (`main.py`):**
    *   Initializes the PyQt6 `QApplication`.
    *   Creates and shows the `MainWindow` from `ui.main_window.py`.
    *   Starts the application event loop.

2.  **Configuration (`config.py`):**
    *   Loads API keys (Anthropic, Deepgram) from a `.env` file using `python-dotenv`.
    *   Defines constants for audio settings (buffer length, sample rate), AI model parameters (model name, max tokens, temperature), and temporary file names.

3.  **Main UI (`ui/main_window.py`):**
    *   The core class `MainWindow` orchestrates the application.
    *   Sets up the main layout using `QVBoxLayout`, `QHBoxLayout`, and a `QSplitter`.
    *   Includes a header with a logo and animated title (`AnimatedLabel`).
    *   Uses a `QSplitter` to divide the main area into `ControlsPanel` (left) and `OutputPanel` (right).
    *   Initializes `ContinuousRecorder` (`audio.recorder`) and `ApiClient` (`api.client`).
    *   Manages application state (e.g., `is_processing`, `current_transcript`).
    *   **Connections:** Connects button clicks from `ControlsPanel` to methods within `MainWindow` (e.g., `toggle_recording`, `transcribe_buffer`, `run_prompt_with_auto_transcribe`).
    *   **Threading:** Uses Python's `threading` module to run potentially long operations (transcription, AI analysis) in the background to avoid blocking the UI.
    *   **Signals/Slots:** Uses PyQt signals (`pyqtSignal`) and slots (`pyqtSlot`) for safe communication between background threads and the main UI thread (e.g., `transcription_complete`, `processing_complete`, `stream_update`).
    *   **Prompt Handling:** The `run_prompt_with_auto_transcribe` method handles most AI analysis requests. It first ensures there's a transcript (transcribing if necessary using `_transcribe_and_process_thread`) and then calls `_run_specific_prompt`.
    *   **AI Interaction (`_run_specific_prompt`):** Uses the `ApiClient` to call the Anthropic API (likely the streaming endpoint based on `handle_stream` usage). It passes the selected prompt template and the current transcript.
    *   **Streaming Output:** The `on_stream_update` slot receives chunks of text from the AI stream. The `_process_html_chunk` method attempts to parse and buffer these chunks to build valid HTML, which is then appended to the `OutputPanel`. It handles basic HTML tags like headings, paragraphs, and lists.
    *   **Static Templates:** Uses `_setup_static_template` to prepare the HTML structure in the `OutputPanel` before streaming begins, especially for complex layouts like sentiment analysis.

4.  **Controls Panel (`ui/controls_panel.py`):**
    *   A `QWidget` containing buttons for recording control, transcription, clearing output, and triggering various AI analysis prompts.
    *   Emits signals (e.g., `record_clicked`, `summary_clicked`) when buttons are pressed, which are connected in `MainWindow`.

5.  **Output Panel (`ui/output_panel.py`):**
    *   A `QWidget` that uses `QWebEngineView` to render HTML content.
    *   Provides methods (`set_output`, `append_output`, `set_error`, `set_status`, `append_to_list_by_id`) to update the displayed HTML.
    *   Receives HTML updates via the `html_update` signal, ensuring updates happen on the main thread.
    *   Contains JavaScript functions embedded via `runJavaScript` to manipulate the DOM (e.g., update sentiment value, append items to lists).

6.  **Audio Recorder (`audio/recorder.py`):**
    *   The `ContinuousRecorder` class uses `sounddevice` (or potentially fallback libraries like `pyaudio`, `soundcard`) to capture audio.
    *   Maintains a rolling buffer in memory using a `deque` of NumPy arrays.
    *   Provides methods to start/stop recording and retrieve the buffer contents (`save_buffer`).

7.  **API Client (`api/client.py`):**
    *   Handles communication with external APIs.
    *   Likely contains methods for:
        *   Deepgram transcription (e.g., `transcribe_with_deepgram`).
        *   Anthropic Claude AI interaction (e.g., `stream_claude_response`).
    *   Uses API keys loaded from `config.py`.

8.  **Prompts (`prompts/templates.py`, `prompts/logic_templates.py`):**
    *   Store the text templates used to instruct the Claude AI for different analysis tasks.

## 5. Dependencies

Key external libraries used (from `requirements.txt`):

*   **GUI:** `PyQt6`, `PyQt6-WebEngine`
*   **Audio:** `sounddevice`, `numpy`, `pyaudio`, `soundcard`, `soundfile`, `scipy`
*   **AI/API:** `anthropic`, `deepgram-sdk`
*   **Configuration:** `python-dotenv`
*   **Utilities:** `markdown2` (likely for formatting output), `keyboard` (purpose unclear from context, potentially global hotkeys?)
*   **Development/Debugging:** `ipykernel`, `jupyter` (may not be runtime dependencies)

## 6. Current Status & Notes

*   The application uses a rolling buffer for audio recording.
*   Transcription is handled by Deepgram.
*   AI analysis uses Anthropic's Claude models.
*   The UI is built with PyQt6, featuring separate control and output panels.
*   Output is rendered as HTML using QWebEngineView.
*   Streaming output from the AI is implemented, allowing for real-time updates in the output panel.
*   HTML parsing for streaming output is basic and might be fragile depending on the AI's output structure.
*   Threading is used for background tasks.
*   Configuration relies on environment variables loaded via a `.env` file.
