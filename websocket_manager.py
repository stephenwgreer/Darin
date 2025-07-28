"""
WebSocket Manager
Handles real-time communication between frontend and backend
Replaces Qt signals/slots with clean WebSocket message routing
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from enum import Enum

from fastapi import WebSocket, WebSocketDisconnect


class MessageType(str, Enum):
    """WebSocket message types for communication protocol"""
    
    # Audio Control Messages
    START_RECORDING = "start_recording"
    STOP_RECORDING = "stop_recording"
    PAUSE_RECORDING = "pause_recording"
    
    # Transcription Messages
    TRANSCRIBE_BUFFER = "transcribe_buffer"
    TRANSCRIBE_LAST_30 = "transcribe_last_30"
    GET_AUDIO_BUFFER = "get_audio_buffer"
    LOAD_TEST_AUDIO = "load_test_audio"
    
    # Analysis Messages
    ANALYZE_TRANSCRIPT = "analyze_transcript"
    
    # Status/Response Messages
    RECORDING_STATUS = "recording_status"
    TRANSCRIPTION_RESULT = "transcription_result"
    ANALYSIS_RESULT = "analysis_result"
    AUDIO_BUFFER_RESULT = "audio_buffer_result"
    STREAM_CHUNK = "stream_chunk"
    ERROR = "error"
    STATUS_UPDATE = "status_update"


class WebSocketManager:
    """
    Manages WebSocket connections and message routing.
    Provides clean interface replacing Qt signals/slots complexity.
    """
    
    def __init__(self, audio_recorder, api_clients):
        """
        Initialize WebSocket manager.
        
        Args:
            audio_recorder: AsyncAudioRecorder instance
            api_clients: APIClients instance
        """
        self.audio_recorder = audio_recorder
        self.api_clients = api_clients
        self.active_connections: List[WebSocket] = []
        
        # Import prompt processor here to avoid circular imports
        from prompt_processor import PromptProcessor
        self.prompt_processor = PromptProcessor()
        
        print("✅ WebSocket manager initialized")
    
    async def handle_connection(self, websocket: WebSocket):
        """
        Handle a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection to handle
        """
        await websocket.accept()
        self.active_connections.append(websocket)
        
        print(f"🔌 WebSocket connected (total: {len(self.active_connections)})")
        
        # Send initial status
        await self._send_status_update(websocket)
        
        try:
            await self._handle_messages(websocket)
        except WebSocketDisconnect:
            print("🔌 WebSocket disconnected normally")
        except Exception as e:
            print(f"❌ WebSocket error: {e}")
            await self._send_error(websocket, f"Connection error: {str(e)}")
        finally:
            await self._cleanup_connection(websocket)
    
    async def _cleanup_connection(self, websocket: WebSocket):
        """Clean up disconnected WebSocket"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"🔌 WebSocket cleaned up (remaining: {len(self.active_connections)})")
    
    async def _handle_messages(self, websocket: WebSocket):
        """
        Handle incoming WebSocket messages.
        
        Args:
            websocket: WebSocket connection
        """
        while True:
            try:
                # Receive and parse message
                data = await websocket.receive_text()
                message = json.loads(data)
                
                message_type = message.get("type")
                payload = message.get("data", {})
                
                print(f"📨 Received: {message_type}")
                
                # Route message to appropriate handler
                await self._route_message(websocket, message_type, payload)
                
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError as e:
                await self._send_error(websocket, f"Invalid JSON: {str(e)}")
            except Exception as e:
                await self._send_error(websocket, f"Message handling error: {str(e)}")
    
    async def _route_message(self, websocket: WebSocket, message_type: str, payload: Dict[str, Any]):
        """
        Route message to appropriate handler based on type.
        
        Args:
            websocket: WebSocket connection
            message_type: Type of message received
            payload: Message data
        """
        try:
            # Audio control messages
            if message_type == MessageType.START_RECORDING:
                await self._handle_start_recording(websocket)
            
            elif message_type == MessageType.STOP_RECORDING:
                await self._handle_stop_recording(websocket)
            
            elif message_type == MessageType.PAUSE_RECORDING:
                await self._handle_pause_recording(websocket)
            
            # Transcription messages
            elif message_type == MessageType.TRANSCRIBE_BUFFER:
                await self._handle_transcribe_buffer(websocket)
            
            elif message_type == MessageType.TRANSCRIBE_LAST_30:
                await self._handle_transcribe_last_30(websocket)
            
            elif message_type == MessageType.GET_AUDIO_BUFFER:
                await self._handle_get_audio_buffer(websocket)
            
            elif message_type == MessageType.LOAD_TEST_AUDIO:
                await self._handle_load_test_audio(websocket)
            
            # Analysis messages
            elif message_type == MessageType.ANALYZE_TRANSCRIPT:
                await self._handle_analyze_transcript(websocket, payload)
            
            else:
                await self._send_error(websocket, f"Unknown message type: {message_type}")
                
        except Exception as e:
            await self._send_error(websocket, f"Handler error: {str(e)}")
    
    # Audio Control Handlers
    
    async def _handle_start_recording(self, websocket: WebSocket):
        """Handle start recording request"""
        try:
            success = await self.audio_recorder.start_recording()
            await self._send_recording_status(websocket)
            
            if success:
                await self._send_status_update(websocket, "Recording started")
            else:
                await self._send_error(websocket, "Failed to start recording")
                
        except Exception as e:
            await self._send_error(websocket, f"Start recording error: {str(e)}")
    
    async def _handle_stop_recording(self, websocket: WebSocket):
        """Handle stop recording request"""
        try:
            success = await self.audio_recorder.stop_recording()
            await self._send_recording_status(websocket)
            
            if success:
                await self._send_status_update(websocket, "Recording stopped")
            else:
                await self._send_error(websocket, "Failed to stop recording")
                
        except Exception as e:
            await self._send_error(websocket, f"Stop recording error: {str(e)}")
    
    async def _handle_pause_recording(self, websocket: WebSocket):
        """Handle pause/resume recording request"""
        try:
            is_paused = await self.audio_recorder.toggle_pause()
            await self._send_recording_status(websocket)
            
            status = "Recording paused" if is_paused else "Recording resumed"
            await self._send_status_update(websocket, status)
            
        except Exception as e:
            await self._send_error(websocket, f"Pause recording error: {str(e)}")
    
    # Transcription Handlers
    
    async def _handle_transcribe_buffer(self, websocket: WebSocket):
        """Handle transcribe full buffer request"""
        try:
            await self._send_status_update(websocket, "Transcribing audio buffer...")
            
            # Get audio data
            audio_data = self.audio_recorder.get_full_buffer()
            if audio_data is None:
                await self._send_error(websocket, "No audio data in buffer")
                return
            
            # Transcribe
            transcript = await self.api_clients.transcribe_audio(
                audio_data, 
                self.audio_recorder.sample_rate
            )
            
            # Send result
            await self._send_message(websocket, MessageType.TRANSCRIPTION_RESULT, {
                "transcript": transcript,
                "duration_type": "full_buffer",
                "timestamp": asyncio.get_event_loop().time()
            })
            
            await self._send_status_update(websocket, "Transcription complete")
            
        except Exception as e:
            await self._send_error(websocket, f"Transcription error: {str(e)}")
    
    async def _handle_transcribe_last_30(self, websocket: WebSocket):
        """Handle transcribe last 30 seconds request"""
        try:
            await self._send_status_update(websocket, "Transcribing last 30 seconds...")
            
            # Get last 30 seconds of audio
            audio_data = self.audio_recorder.get_last_seconds(30)
            if audio_data is None:
                await self._send_error(websocket, "Not enough audio data (need 30 seconds)")
                return
            
            # Transcribe
            transcript = await self.api_clients.transcribe_audio(
                audio_data, 
                self.audio_recorder.sample_rate
            )
            
            # Send result
            await self._send_message(websocket, MessageType.TRANSCRIPTION_RESULT, {
                "transcript": transcript,
                "duration_type": "last_30_seconds",
                "timestamp": asyncio.get_event_loop().time()
            })
            
            await self._send_status_update(websocket, "Transcription complete")
            
        except Exception as e:
            await self._send_error(websocket, f"Transcription error: {str(e)}")
    
    async def _handle_get_audio_buffer(self, websocket: WebSocket):
        """Handle get audio buffer request"""
        try:
            await self._send_status_update(websocket, "Retrieving audio buffer...")
            
            # Get audio data from recorder
            audio_data = self.audio_recorder.get_full_buffer()
            if audio_data is None:
                await self._send_error(websocket, "No audio data in buffer")
                return
            
            # Convert numpy array to bytes (WAV format)
            import io
            import soundfile as sf
            
            # Create WAV file in memory
            buffer = io.BytesIO()
            sf.write(buffer, audio_data, self.audio_recorder.sample_rate, format='WAV')
            wav_bytes = buffer.getvalue()
            buffer.close()
            
            # Convert to base64 for transmission
            import base64
            audio_base64 = base64.b64encode(wav_bytes).decode('utf-8')
            
            # Send result
            await self._send_message(websocket, MessageType.AUDIO_BUFFER_RESULT, {
                "audio_data": audio_base64,
                "sample_rate": self.audio_recorder.sample_rate,
                "duration": len(audio_data) / self.audio_recorder.sample_rate,
                "timestamp": asyncio.get_event_loop().time()
            })
            
            await self._send_status_update(websocket, "Audio buffer ready")
            
        except Exception as e:
            await self._send_error(websocket, f"Audio buffer error: {str(e)}")
    
    async def _handle_load_test_audio(self, websocket: WebSocket):
        """Handle load test audio request"""
        try:
            await self._send_status_update(websocket, "Loading test audio...")
            
            # Load test audio file
            import soundfile as sf
            import os
            from pathlib import Path
            
            test_audio_path = Path("test_audio/out2.wav")
            if not test_audio_path.exists():
                await self._send_error(websocket, f"Test audio file not found: {test_audio_path}")
                return
            
            # Read audio file
            audio_data, sample_rate = sf.read(str(test_audio_path))
            
            # Ensure mono audio (take first channel if stereo)
            if len(audio_data.shape) > 1:
                audio_data = audio_data[:, 0]
            
            # Resample if needed to match recorder sample rate
            if sample_rate != self.audio_recorder.sample_rate:
                import scipy.signal
                # Calculate new length
                new_length = int(len(audio_data) * self.audio_recorder.sample_rate / sample_rate)
                audio_data = scipy.signal.resample(audio_data, new_length)
                print(f"🔄 Resampled audio from {sample_rate}Hz to {self.audio_recorder.sample_rate}Hz")
            
            # Load into audio recorder buffer
            success = await self.audio_recorder.load_test_audio(audio_data)
            
            if success:
                # Send recording status update
                await self._send_recording_status(websocket)
                await self._send_status_update(websocket, f"Test audio loaded ({len(audio_data)/self.audio_recorder.sample_rate:.1f}s)")
            else:
                await self._send_error(websocket, "Failed to load test audio into buffer")
            
        except Exception as e:
            await self._send_error(websocket, f"Test audio loading error: {str(e)}")
    
    # Analysis Handlers
    
    async def _handle_analyze_transcript(self, websocket: WebSocket, payload: Dict[str, Any]):
        """
        Handle transcript analysis request.
        
        Args:
            websocket: WebSocket connection
            payload: Analysis request data
        """
        try:
            transcript = payload.get("transcript")
            analysis_type = payload.get("analysis_type")
            prompt_id = payload.get("prompt_id")
            
            if not transcript:
                await self._send_error(websocket, "No transcript provided for analysis")
                return
            
            if not prompt_id:
                await self._send_error(websocket, "No prompt ID provided")
                return
            
            # Validate prompt request using prompt processor
            is_valid, error_msg = self.prompt_processor.validate_prompt_request(prompt_id, transcript)
            if not is_valid:
                await self._send_error(websocket, error_msg)
                return
            
            # Get prompt template
            prompt_template = self.prompt_processor.get_prompt_template(prompt_id)
            if not prompt_template:
                await self._send_error(websocket, f"Unknown prompt ID: {prompt_id}")
                return
            
            await self._send_status_update(websocket, f"Analyzing transcript ({analysis_type})...")
            
            # Create streaming callback
            async def stream_callback(chunk: str):
                await self._send_message(websocket, MessageType.STREAM_CHUNK, {
                    "chunk": chunk,
                    "analysis_type": analysis_type,
                    "prompt_id": prompt_id
                })
            
            # Perform analysis with streaming
            result = await self.api_clients.analyze_transcript(
                transcript,
                prompt_template,
                stream_callback
            )
            
            # Send final result
            await self._send_message(websocket, MessageType.ANALYSIS_RESULT, {
                "result": result,
                "analysis_type": analysis_type,
                "timestamp": asyncio.get_event_loop().time()
            })
            
            await self._send_status_update(websocket, "Analysis complete")
            
        except Exception as e:
            await self._send_error(websocket, f"Analysis error: {str(e)}")
    
    # Message Sending Helpers
    
    async def _send_message(self, websocket: WebSocket, message_type: MessageType, data: Any):
        """
        Send a message to the WebSocket client.
        
        Args:
            websocket: WebSocket connection
            message_type: Type of message
            data: Message data
        """
        try:
            message = {
                "type": message_type.value,
                "data": data
            }
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            print(f"❌ Failed to send message: {e}")
    
    async def _send_recording_status(self, websocket: WebSocket):
        """Send current recording status"""
        status_data = {
            "is_recording": self.audio_recorder.is_recording,
            "is_paused": getattr(self.audio_recorder, 'is_paused', False),
            "buffer_duration": self.audio_recorder.get_buffer_duration(),
            "buffer_max_duration": self.audio_recorder.buffer_minutes * 60
        }
        await self._send_message(websocket, MessageType.RECORDING_STATUS, status_data)
    
    async def _send_status_update(self, websocket: WebSocket, message: str = "Ready"):
        """Send status update message"""
        await self._send_message(websocket, MessageType.STATUS_UPDATE, {"message": message})
    
    async def _send_error(self, websocket: WebSocket, error_message: str):
        """Send error message to client"""
        print(f"❌ Sending error: {error_message}")
        await self._send_message(websocket, MessageType.ERROR, {"message": error_message})
    
    async def broadcast_message(self, message_type: MessageType, data: Any):
        """
        Broadcast message to all connected clients.
        
        Args:
            message_type: Type of message
            data: Message data
        """
        if not self.active_connections:
            return
        
        message = {
            "type": message_type.value,
            "data": data
        }
        message_text = json.dumps(message)
        
        # Send to all connections, removing failed ones
        failed_connections = []
        for websocket in self.active_connections[:]:  # Copy list to avoid modification during iteration
            try:
                await websocket.send_text(message_text)
            except Exception as e:
                print(f"❌ Failed to broadcast to connection: {e}")
                failed_connections.append(websocket)
        
        # Clean up failed connections
        for failed_ws in failed_connections:
            await self._cleanup_connection(failed_ws)
    
    def get_status(self) -> Dict[str, Any]:
        """Get WebSocket manager status"""
        return {
            "active_connections": len(self.active_connections),
            "audio_recorder_status": self.audio_recorder.get_status() if self.audio_recorder else None,
            "api_clients_status": self.api_clients.get_status() if self.api_clients else None
        }