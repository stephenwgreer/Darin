"""
Darin Audio Assistant - FastAPI Backend
High-performance audio recording and AI analysis with real-time streaming
"""

import asyncio
import webbrowser
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

from config import (
    ANTHROPIC_API_KEY, DEEPGRAM_API_KEY, BUFFER_MINUTES, SAMPLE_RATE,
    AUTO_OPEN_BROWSER, print_config_status
)
from audio_recorder import AsyncAudioRecorder
from api_clients import APIClients
from websocket_manager import WebSocketManager
from prompt_processor import PromptProcessor


# Global components - initialized during startup
audio_recorder = None
api_clients = None
websocket_manager = None
prompt_processor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown"""
    global audio_recorder, api_clients, websocket_manager, prompt_processor
    
    print("🚀 Starting Darin Audio Assistant...")
    
    # Print configuration status
    print_config_status()
    
    # Initialize core components
    audio_recorder = AsyncAudioRecorder(buffer_minutes=BUFFER_MINUTES, sample_rate=SAMPLE_RATE)
    api_clients = APIClients(
        anthropic_api_key=ANTHROPIC_API_KEY,
        deepgram_api_key=DEEPGRAM_API_KEY
    )
    prompt_processor = PromptProcessor()
    websocket_manager = WebSocketManager(audio_recorder, api_clients)
    
    print("✅ Audio recorder initialized")
    print("✅ API clients initialized") 
    print("✅ Prompt processor initialized")
    print("✅ WebSocket manager initialized")
    
    # Check if frontend is built
    frontend_path = Path("frontend/dist")
    if frontend_path.exists():
        print("✅ Frontend assets found")
    else:
        print("⚠️  Frontend not built. Run: cd frontend && npm run build")
    
    print(f"🌐 Server starting at: http://127.0.0.1:8000")
    if AUTO_OPEN_BROWSER:
        print("📱 Opening browser automatically...")
    
    yield
    
    # Cleanup on shutdown
    print("🔄 Shutting down...")
    if audio_recorder and audio_recorder.is_recording:
        await audio_recorder.stop_recording()
    print("✅ Cleanup complete")


# Initialize FastAPI app with lifespan management
app = FastAPI(
    title="Darin Audio Assistant",
    description="Real-time audio recording and AI analysis",
    version="2.0.0",
    lifespan=lifespan
)


# Serve frontend static files (if built)
frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    
    @app.get("/", response_class=HTMLResponse)
    async def serve_frontend():
        """Serve the main React application"""
        return FileResponse(str(frontend_dist / "index.html"))
        
    @app.get("/favicon.ico")
    async def favicon():
        """Serve favicon if it exists"""
        favicon_path = frontend_dist / "favicon.ico"
        if favicon_path.exists():
            return FileResponse(str(favicon_path))
        return HTMLResponse(status_code=404)
else:
    @app.get("/", response_class=HTMLResponse)
    async def development_page():
        """Development page when frontend isn't built"""
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Darin Audio Assistant - Development</title>
            <style>
                body { font-family: system-ui; max-width: 800px; margin: 50px auto; padding: 20px; }
                .status { padding: 20px; border-radius: 8px; margin: 20px 0; }
                .info { background: #e3f2fd; border-left: 4px solid #2196f3; }
                .warning { background: #fff3e0; border-left: 4px solid #ff9800; }
                .success { background: #e8f5e8; border-left: 4px solid #4caf50; }
                code { background: #f5f5f5; padding: 2px 6px; border-radius: 4px; }
            </style>
        </head>
        <body>
            <h1>🎙️ Darin Audio Assistant</h1>
            <p>FastAPI backend is running successfully!</p>
            
            <div class="status warning">
                <h3>⚠️ Frontend Not Built</h3>
                <p>To use the web interface, build the React frontend:</p>
                <code>cd frontend && npm run build</code>
            </div>
            
            <div class="status info">
                <h3>🔌 WebSocket Endpoint</h3>
                <p>WebSocket available at: <code>ws://127.0.0.1:8000/ws</code></p>
            </div>
            
            <div class="status success">
                <h3>🚀 Backend Status</h3>
                <ul>
                    <li>✅ FastAPI server running</li>
                    <li>✅ Audio recorder ready</li>
                    <li>✅ API clients initialized</li>
                    <li>✅ WebSocket manager ready</li>
                </ul>
            </div>
            
            <h3>📋 Next Steps</h3>
            <ol>
                <li>Build frontend: <code>cd frontend && npm run build</code></li>
                <li>Restart server: <code>python main.py</code></li>
                <li>Access at: <code>http://127.0.0.1:8000</code></li>
            </ol>
        </body>
        </html>
        """)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time communication"""
    if websocket_manager is None:
        await websocket.close(code=1011, reason="Server not initialized")
        return
        
    await websocket_manager.handle_connection(websocket)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "components": {
            "audio_recorder": audio_recorder is not None,
            "api_clients": api_clients is not None,
            "websocket_manager": websocket_manager is not None,
            "frontend_built": frontend_dist.exists() if 'frontend_dist' in locals() else False
        }
    }


@app.get("/api/status")
async def api_status():
    """API status endpoint for debugging"""
    if not audio_recorder:
        return {"error": "Components not initialized"}
        
    return {
        "audio": {
            "is_recording": audio_recorder.is_recording,
            "is_paused": getattr(audio_recorder, 'is_paused', False),
            "buffer_duration": audio_recorder.get_buffer_duration(),
            "sample_rate": audio_recorder.sample_rate
        },
        "apis": {
            "anthropic_configured": bool(ANTHROPIC_API_KEY),
            "deepgram_configured": bool(DEEPGRAM_API_KEY)
        },
        "websocket": websocket_manager.get_status() if websocket_manager else None,
        "prompts": prompt_processor.get_prompt_stats() if prompt_processor else None
    }


@app.get("/api/prompts")
async def get_prompts():
    """Get available prompts for frontend"""
    if not prompt_processor:
        return {"error": "Prompt processor not initialized"}
    
    return {
        "prompts": prompt_processor.get_all_prompts(),
        "categories": prompt_processor.get_prompts_by_category(),
        "stats": prompt_processor.get_prompt_stats()
    }


def open_browser():
    """Open browser after a short delay"""
    import threading
    import time
    
    def delayed_open():
        time.sleep(1.5)  # Wait for server to fully start
        try:
            webbrowser.open("http://127.0.0.1:8000")
        except Exception as e:
            print(f"Could not open browser automatically: {e}")
            print("Please open http://127.0.0.1:8000 manually")
    
    threading.Thread(target=delayed_open, daemon=True).start()


if __name__ == "__main__":
    # Open browser automatically if configured
    if AUTO_OPEN_BROWSER:
        open_browser()
    
    # Start the FastAPI server
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        access_log=False  # Reduce noise in development
    )