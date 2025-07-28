"""
Unified API Clients
Async-compatible client for Deepgram (transcription) and Anthropic (analysis)
Consolidates all API functionality into a single, performant interface
"""

import asyncio
import aiohttp
import tempfile
import os
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import numpy as np
import soundfile as sf
import anthropic

from config import CLAUDE_MODEL, MAX_TOKENS, TEMPERATURE


class APIClients:
    """
    Unified async API client for all external services.
    Combines Deepgram transcription and Anthropic analysis.
    """
    
    def __init__(self, anthropic_api_key: str, deepgram_api_key: str):
        """
        Initialize API clients.
        
        Args:
            anthropic_api_key: API key for Claude/Anthropic
            deepgram_api_key: API key for Deepgram transcription
        """
        self.anthropic_api_key = anthropic_api_key
        self.deepgram_api_key = deepgram_api_key
        
        # Lazy-loaded clients
        self._anthropic_client = None
        self._aiohttp_session = None
        
        print("✅ API clients initialized")
    
    @property
    def anthropic_client(self) -> anthropic.Anthropic:
        """Lazy-load Anthropic client when needed"""
        if not self._anthropic_client and self.anthropic_api_key:
            self._anthropic_client = anthropic.Anthropic(
                api_key=self.anthropic_api_key,
                timeout=60.0  # 60 second timeout
            )
        return self._anthropic_client
    
    async def get_aiohttp_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session for API calls"""
        if not self._aiohttp_session or self._aiohttp_session.closed:
            self._aiohttp_session = aiohttp.ClientSession()
        return self._aiohttp_session
    
    async def close(self):
        """Close all connections and cleanup"""
        if self._aiohttp_session and not self._aiohttp_session.closed:
            await self._aiohttp_session.close()
    
    async def transcribe_audio(self, audio_data: np.ndarray, sample_rate: int) -> str:
        """
        Transcribe audio using Deepgram API.
        
        Args:
            audio_data: Audio data as numpy array (mono)
            sample_rate: Sample rate of the audio
            
        Returns:
            str: Transcribed text or error message
        """
        if not self.deepgram_api_key:
            return "Error: Deepgram API key not configured"
        
        if audio_data is None or audio_data.size == 0:
            return "Error: No audio data provided"
        
        try:
            # Ensure audio is in correct format for Deepgram
            # Convert to float32 and normalize if needed
            if audio_data.dtype != np.float32:
                if audio_data.dtype == np.int16:
                    # Convert int16 to float32 (normalize)
                    audio_data = audio_data.astype(np.float32) / 32768.0
                else:
                    audio_data = audio_data.astype(np.float32)
            
            # Ensure audio is mono
            if audio_data.ndim > 1:
                audio_data = audio_data[:, 0]
            
            # Create WAV data in memory
            import io
            audio_buffer = io.BytesIO()
            sf.write(audio_buffer, audio_data, sample_rate, format='WAV', subtype='PCM_16')
            wav_data = audio_buffer.getvalue()
            audio_buffer.close()
            
            print(f"🎵 Audio prepared: {len(audio_data)/sample_rate:.1f}s, {sample_rate}Hz, {len(wav_data)} bytes")
            
            # Transcribe using Deepgram API with in-memory data
            transcript = await self._call_deepgram_api_direct(wav_data)
            
            return transcript
                
        except Exception as e:
            return f"Transcription error: {str(e)}"
    
    async def _call_deepgram_api_direct(self, wav_data: bytes) -> str:
        """
        Call Deepgram API with in-memory audio data.
        
        Args:
            wav_data: WAV audio data as bytes
            
        Returns:
            str: Transcribed text
        """
        url = "https://api.deepgram.com/v1/listen"
        headers = {
            "Authorization": f"Token {self.deepgram_api_key}",
            "Content-Type": "audio/wav"
        }
        params = {
            "punctuate": "true",
            "model": "general", 
            "language": "en-US",
            "smart_format": "true"
        }
        
        session = await self.get_aiohttp_session()
        
        try:
            # Send WAV data directly as request body
            async with session.post(url, headers=headers, params=params, data=wav_data) as response:
                    if response.status == 200:
                        response_json = await response.json()
                        
                        # Extract transcript
                        try:
                            transcript = response_json["results"]["channels"][0]["alternatives"][0]["transcript"]
                            
                            if not transcript.strip():
                                return "No speech detected in audio"
                            
                            print(f"📝 Transcription complete: {len(transcript)} characters")
                            return transcript
                            
                        except KeyError as e:
                            print(f"❌ Unexpected Deepgram response structure: {e}")
                            return "Error: Could not extract transcript from Deepgram response"
                    else:
                        error_text = await response.text()
                        print(f"❌ Deepgram API error: {response.status} - {error_text}")
                        return f"Deepgram API error: {response.status}"
                        
        except Exception as e:
            print(f"❌ Deepgram request failed: {e}")
            return f"Network error calling Deepgram: {str(e)}"
    
    async def analyze_transcript(
        self, 
        transcript: str, 
        prompt_template: str, 
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Analyze transcript using Claude with optional streaming.
        
        Args:
            transcript: Text to analyze
            prompt_template: Prompt template with {transcript} placeholder
            stream_callback: Optional callback for streaming chunks
            
        Returns:
            str: Complete analysis result
        """
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")
        
        if not transcript.strip():
            return "Error: No transcript provided for analysis"
        
        try:
            # Format prompt with transcript
            content = prompt_template.format(transcript=transcript)
            
            print(f"🧠 Starting Claude analysis ({len(content)} chars)")
            
            # Use streaming if callback provided
            if stream_callback:
                return await self._stream_claude_analysis(content, stream_callback)
            else:
                return await self._complete_claude_analysis(content)
                
        except Exception as e:
            error_msg = f"Claude analysis error: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg
    
    async def _stream_claude_analysis(self, content: str, stream_callback: Callable[[str], None]) -> str:
        """
        Stream Claude analysis with real-time callbacks.
        
        Args:
            content: Formatted prompt content
            stream_callback: Callback function for each chunk
            
        Returns:
            str: Complete response text
        """
        client = self.anthropic_client
        
        try:
            response_text = ""
            
            # Use direct streaming without thread executor since the callback needs to be async
            with client.messages.stream(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                messages=[{"role": "user", "content": content}]
            ) as stream:
                for text in stream.text_stream:
                    response_text += text
                    # Call async callback directly
                    if stream_callback:
                        # Since stream_callback is actually async (from websocket_manager), 
                        # we need to await it
                        if asyncio.iscoroutinefunction(stream_callback):
                            await stream_callback(text)
                        else:
                            stream_callback(text)
            
            print(f"✅ Claude streaming complete: {len(response_text)} characters")
            return response_text
            
        except Exception as e:
            error_msg = f"Claude streaming error: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg
    
    async def _complete_claude_analysis(self, content: str) -> str:
        """
        Get complete Claude analysis without streaming.
        
        Args:
            content: Formatted prompt content
            
        Returns:
            str: Complete response text
        """
        client = self.anthropic_client
        
        try:
            # Run Claude request in executor to avoid blocking
            loop = asyncio.get_event_loop()
            
            def analyze_sync():
                """Sync function to handle Claude request"""
                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                    messages=[{"role": "user", "content": content}]
                )
                return response.content[0].text
            
            # Run analysis in thread pool
            result = await loop.run_in_executor(None, analyze_sync)
            
            print(f"✅ Claude analysis complete: {len(result)} characters")
            return result
            
        except Exception as e:
            error_msg = f"Claude analysis error: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get API client status for debugging.
        
        Returns:
            dict: Status information
        """
        return {
            "anthropic_configured": bool(self.anthropic_api_key),
            "deepgram_configured": bool(self.deepgram_api_key),
            "anthropic_client_loaded": self._anthropic_client is not None,
            "aiohttp_session_active": (
                self._aiohttp_session is not None and 
                not self._aiohttp_session.closed
            ),
            "model_settings": {
                "claude_model": CLAUDE_MODEL,
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE
            }
        }