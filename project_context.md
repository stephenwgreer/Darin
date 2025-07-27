# Project Context: Darin Audio Assistant

## 1. Project Summary

**MIGRATION IN PROGRESS: PyQt6 → Hybrid Local Web Architecture**

Darin Audio Assistant is transitioning from a PyQt6 desktop application to a modern hybrid architecture combining a lightweight Python FastAPI backend with a React web frontend. The application records audio conversations, transcribes them in real-time using Deepgram, and leverages Anthropic's Claude models to analyze transcripts and provide various insights. It serves as an intelligent assistant for meetings, interviews, or any scenario requiring audio capture and analysis.

### Architecture Evolution
- **Previous**: Monolithic PyQt6 desktop application
- **Current Target**: FastAPI backend + React frontend (served locally)
- **Deployment**: Single Python command serves web UI at localhost:8000

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

### Current (Legacy PyQt6)
```
audio_test/
├── api/                # API client implementations (Anthropic, Deepgram)
├── audio/             # Audio recording (ContinuousRecorder)
├── ui/                # PyQt6 UI components [TO BE DEPRECATED]
├── prompts/           # AI prompt templates and logic definitions
├── assets/            # Images (logos, icons), static resources
├── main.py           # PyQt6 entry point [TO BE REPLACED]
├── config.py         # Configuration
└── requirements.txt  # Python dependencies
```

### Target (Hybrid Web Architecture)
```
audio_test/
├── main.py                  # NEW: FastAPI server entry point
├── websocket_manager.py     # NEW: WebSocket message handling
├── audio_recorder.py        # NEW: Async audio capture with circular buffer
├── api_clients.py           # NEW: Unified API client (Deepgram + Anthropic)
├── prompt_processor.py      # NEW: Streaming prompt processing
├── config.py               # UPDATED: FastAPI configuration
├── requirements.txt        # UPDATED: FastAPI + WebSocket dependencies
├── frontend/               # NEW: React + TypeScript + Tailwind
│   ├── src/
│   │   ├── App.tsx         # EXISTING: Beautiful UI (keep current design)
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts    # NEW: WebSocket communication
│   │   │   └── useAudioStream.ts  # NEW: Audio state management
│   │   ├── types/
│   │   │   └── index.ts           # NEW: TypeScript definitions
│   │   └── components/     # NEW: Modular React components
│   ├── package.json        # EXISTING: React + Vite + Tailwind
│   └── dist/              # Built frontend assets
├── assets/                 # KEEP: Static resources
└── prompts/               # KEEP: Prompt templates (adapt for new API)
```

## 4. Key Components & Logic Flow

### Legacy Architecture (PyQt6)
[Previous implementation using PyQt6 - see version history for details]

### New Architecture (FastAPI + React)

#### Backend Components

1. **FastAPI Server (`main.py`):**
   * Serves the React frontend at localhost:8000
   * Provides WebSocket endpoint at `/ws` for real-time communication
   * Handles static file serving from `frontend/dist/`
   * Initializes core components (audio recorder, API clients, WebSocket manager)

2. **WebSocket Manager (`websocket_manager.py`):**
   * Handles bidirectional communication between frontend and backend
   * Message types: recording control, transcription requests, analysis commands
   * Manages client connections and message routing
   * Implements streaming callbacks for real-time AI responses

3. **Async Audio Recorder (`audio_recorder.py`):**
   * Uses `asyncio` and threading for non-blocking audio capture
   * Maintains circular buffer with configurable size (default: 3 minutes)
   * Supports pause/resume, full buffer, and time-based audio retrieval
   * Uses `soundcard` for audio device access

4. **Unified API Clients (`api_clients.py`):**
   * Combines Deepgram (transcription) and Anthropic (analysis) into single interface
   * Async methods for non-blocking API calls
   * Streaming support for real-time Claude responses
   * Error handling and retry logic

5. **Prompt Processor (`prompt_processor.py`):**
   * Manages prompt templates from existing `prompts/` directory
   * Handles streaming response parsing and formatting
   * Maps analysis types to appropriate prompt templates

#### Frontend Components

6. **React App (`frontend/src/App.tsx`):**
   * Modern web UI with Tailwind CSS styling
   * Real-time audio visualizer and recording controls
   * Live transcription display with timestamps
   * AI analysis panel with multiple analysis types

7. **WebSocket Hook (`frontend/src/hooks/useWebSocket.ts`):**
   * Manages WebSocket connection lifecycle
   * Auto-reconnection logic
   * Type-safe message handling
   * Connection status monitoring

8. **Audio Stream Hook (`frontend/src/hooks/useAudioStream.ts`):**
   * Manages audio recording state
   * Buffer time tracking
   * Recording duration display
   * Pause/resume functionality

#### Communication Flow
```
Frontend (React) ←→ WebSocket ←→ Backend (FastAPI) ←→ APIs (Deepgram/Anthropic)
```

#### Key Improvements Over PyQt6
* **Performance**: 60-70% memory reduction, 3-5x faster HTML rendering
* **Maintainability**: 80% code reduction through elimination of duplication
* **Real-time**: Native WebSocket streaming vs. Qt signal/slot complexity
* **Modern UI**: React components vs. Qt widgets, better responsive design
* **Development**: Hot reload, TypeScript safety, modern tooling

## 5. Dependencies

### Backend (Python)
**Core Framework:**
* `fastapi` - High-performance web framework
* `uvicorn[standard]` - ASGI server with WebSocket support
* `websockets` - WebSocket protocol implementation

**Audio Processing:**
* `numpy` - Numerical computing for audio data
* `soundcard` - Audio device access and recording
* `soundfile` - Audio file I/O

**AI/API Services:**
* `anthropic` - Claude AI integration
* `deepgram-sdk` - Speech-to-text transcription

**Configuration:**
* `python-dotenv` - Environment variable management

### Frontend (JavaScript/TypeScript)
**Core Framework:**
* `react` - Component-based UI framework
* `react-dom` - React DOM bindings
* `typescript` - Type safety and modern JavaScript

**Styling:**
* `tailwindcss` - Utility-first CSS framework
* `@tailwindcss/vite` - Vite integration

**Icons:**
* `lucide-react` - Beautiful icon library

**Build Tools:**
* `vite` - Fast build tool and dev server
* `@vitejs/plugin-react` - React plugin for Vite

**Development:**
* `eslint` - Code linting and formatting
* `typescript-eslint` - TypeScript-specific linting rules

## 6. Migration Status & Implementation Plan

### ✅ Completed
* **Frontend Foundation**: React app with Tailwind CSS and beautiful UI design
* **Project Structure**: Clear separation of concerns established
* **Requirements Analysis**: Performance bottlenecks identified in PyQt6 version

### 🚧 In Progress - Backend Implementation
**Priority 1: Core Backend Files**
1. `main.py` - FastAPI server with frontend serving
2. `websocket_manager.py` - Real-time communication handler  
3. `audio_recorder.py` - Async audio capture with circular buffer
4. `api_clients.py` - Unified Deepgram + Anthropic client

**Priority 2: Frontend Integration**
5. `frontend/src/hooks/useWebSocket.ts` - WebSocket communication hook
6. `frontend/src/types/index.ts` - TypeScript definitions
7. Update existing `App.tsx` to use real WebSocket data

**Priority 3: Prompt System Migration**
8. `prompt_processor.py` - Adapt existing prompt templates
9. Migrate prompt registry from `prompts/` directory
10. Update `config.py` for FastAPI environment

### 🎯 Success Metrics
* **Performance**: Sub-100ms WebSocket latency for real-time streaming
* **Memory**: <50MB backend memory usage (vs 200MB+ with PyQt6)  
* **User Experience**: Zero-setup deployment (single `python main.py` command)
* **Maintainability**: <300 lines total backend code (vs 1400+ lines PyQt6)

### 🔄 Deployment Strategy
1. **Phase 1**: Implement backend with mock data
2. **Phase 2**: Connect real audio recording and APIs
3. **Phase 3**: Full frontend integration with streaming
4. **Phase 4**: Production packaging and optimization

### 🛠 Development Environment
* **Backend**: Python 3.9+ with FastAPI development server
* **Frontend**: Node.js with Vite hot reload for development
* **Production**: Single Python command serves built React app

### 📋 Next Actions
1. Implement FastAPI backend components
2. Create WebSocket communication layer
3. Integrate with existing frontend React app
4. Test real-time audio streaming and analysis
5. Performance validation and optimization
