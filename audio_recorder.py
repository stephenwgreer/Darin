"""
Async Audio Recorder
High-performance audio capture with circular buffer using soundcard library
Compatible with FastAPI's async architecture while maintaining soundcard integration
"""

import asyncio
import threading
import time
from collections import deque
from typing import Optional
import numpy as np
import soundcard as sc
import soundfile as sf


class AsyncAudioRecorder:
    """
    Async-compatible audio recorder using soundcard library.
    Maintains a circular buffer for continuous recording with configurable duration.
    """
    
    def __init__(self, buffer_minutes: int = 3, sample_rate: int = 48000, chunk_seconds: int = 1):
        """
        Initialize the async audio recorder.
        
        Args:
            buffer_minutes: How many minutes of audio to keep in memory
            sample_rate: Audio sample rate (Hz)
            chunk_seconds: Size of each audio chunk in seconds
        """
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.chunk_frames = chunk_seconds * sample_rate
        self.buffer_minutes = buffer_minutes
        self.max_chunks = buffer_minutes * 60 // chunk_seconds
        
        # State management
        self.is_recording = False
        self.is_paused = False
        
        # Thread-safe circular buffer using deque
        self.audio_buffer = deque(maxlen=self.max_chunks)
        self.buffer_lock = threading.Lock()
        
        # Threading components
        self._recording_thread = None
        self._stop_event = threading.Event()
        
        # Audio device (initialized when recording starts)
        self.mic = None
        
        print(f"Audio recorder initialized: {buffer_minutes}min buffer @ {sample_rate}Hz")
    
    async def start_recording(self) -> bool:
        """
        Start recording audio asynchronously.
        
        Returns:
            bool: True if recording started successfully, False otherwise
        """
        if self.is_recording:
            print("Recording already in progress")
            return False
        
        try:
            # Initialize microphone (same as original - using soundcard loopback)
            self.mic = sc.get_microphone(
                id=str(sc.default_speaker().name), 
                include_loopback=True
            )
            
            # Reset state
            self.is_recording = True
            self.is_paused = False
            self._stop_event.clear()
            
            # Start recording in background thread (soundcard requires blocking calls)
            loop = asyncio.get_event_loop()
            self._recording_thread = loop.run_in_executor(
                None, self._recording_loop
            )
            
            print("✅ Audio recording started")
            return True
            
        except Exception as e:
            print(f"❌ Failed to start recording: {e}")
            self.is_recording = False
            return False
    
    async def stop_recording(self) -> bool:
        """
        Stop recording audio asynchronously.
        
        Returns:
            bool: True if recording stopped successfully, False otherwise
        """
        if not self.is_recording:
            return False
        
        print("🔄 Stopping audio recording...")
        self.is_recording = False
        self.is_paused = False
        self._stop_event.set()
        
        # Wait for recording thread to finish
        if self._recording_thread:
            try:
                await asyncio.wait_for(self._recording_thread, timeout=3.0)
            except asyncio.TimeoutError:
                print("⚠️ Recording thread didn't stop gracefully")
        
        print("✅ Audio recording stopped")
        return True
    
    async def toggle_pause(self) -> bool:
        """
        Toggle pause state of recording.
        
        Returns:
            bool: Current paused state after toggle
        """
        if not self.is_recording:
            return False
        
        self.is_paused = not self.is_paused
        state = "paused" if self.is_paused else "resumed"
        print(f"🔄 Recording {state}")
        return self.is_paused
    
    def _recording_loop(self):
        """
        Main recording loop running in background thread.
        Uses soundcard's blocking API while being async-compatible.
        """
        try:
            with self.mic.recorder(samplerate=self.sample_rate) as recorder:
                print(f"🎙️ Recording loop started (chunks: {self.chunk_frames} frames)")
                
                while not self._stop_event.is_set() and self.is_recording:
                    if not self.is_paused:
                        # Record audio chunk (blocking call - why we need a thread)
                        try:
                            data = recorder.record(numframes=self.chunk_frames)
                            
                            if data is not None and data.size > 0:
                                # Add to circular buffer (thread-safe)
                                with self.buffer_lock:
                                    self.audio_buffer.append(data)
                                    
                                # Debug: occasionally print buffer status
                                if len(self.audio_buffer) % 60 == 0:  # Every 60 seconds
                                    duration = len(self.audio_buffer) * self.chunk_seconds
                                    print(f"📊 Buffer: {duration}s / {self.buffer_minutes * 60}s")
                            
                        except Exception as e:
                            print(f"❌ Recording chunk error: {e}")
                            break
                    else:
                        # Small sleep when paused to avoid tight loop
                        time.sleep(0.1)
                
        except Exception as e:
            print(f"❌ Recording loop error: {e}")
        finally:
            print("🔄 Recording loop ended")
    
    def get_full_buffer(self) -> Optional[np.ndarray]:
        """
        Get all audio data from the circular buffer.
        
        Returns:
            np.ndarray: Combined audio data as mono signal, or None if empty
        """
        with self.buffer_lock:
            if not self.audio_buffer:
                return None
            
            # Combine all chunks and convert to mono (same as original)
            combined_data = np.concatenate(list(self.audio_buffer), axis=0)
            
            # Extract mono audio (first channel)
            if combined_data.ndim > 1:
                mono_data = combined_data[:, 0]
            else:
                mono_data = combined_data
            
            return mono_data
    
    def get_last_seconds(self, seconds: int) -> Optional[np.ndarray]:
        """
        Get the last N seconds of audio from the buffer.
        
        Args:
            seconds: Number of seconds to retrieve
            
        Returns:
            np.ndarray: Audio data as mono signal, or None if not enough data
        """
        with self.buffer_lock:
            if not self.audio_buffer:
                return None
            
            # Calculate required chunks (same logic as original)
            chunks_needed = max(1, seconds // self.chunk_seconds)
            chunks_needed = min(chunks_needed, len(self.audio_buffer))
            
            # Get recent chunks
            recent_chunks = list(self.audio_buffer)[-chunks_needed:]
            
            if not recent_chunks:
                return None
            
            # Combine and convert to mono
            if len(recent_chunks) == 1:
                combined_data = recent_chunks[0]
            else:
                combined_data = np.concatenate(recent_chunks, axis=0)
            
            # Extract mono audio
            if combined_data.ndim > 1:
                mono_data = combined_data[:, 0]
            else:
                mono_data = combined_data
            
            return mono_data
    
    def get_buffer_duration(self) -> int:
        """
        Get current buffer duration in seconds.
        
        Returns:
            int: Buffer duration in seconds
        """
        with self.buffer_lock:
            return len(self.audio_buffer) * self.chunk_seconds
    
    def save_buffer_to_file(self, filename: Optional[str] = None) -> Optional[np.ndarray]:
        """
        Save current buffer to file and return the audio data.
        Maintains compatibility with original save_buffer method.
        
        Args:
            filename: Output filename, defaults to "BSGPT_REC.wav"
            
        Returns:
            np.ndarray: Mono audio data, or None if no data
        """
        audio_data = self.get_full_buffer()
        
        if audio_data is None:
            print("No audio data to save!")
            return None
        
        # Save to file (same as original)
        output_file = filename or "BSGPT_REC.wav"
        try:
            sf.write(file=output_file, data=audio_data, samplerate=self.sample_rate)
            print(f"💾 Audio saved to {output_file}")
        except Exception as e:
            print(f"❌ Failed to save audio: {e}")
        
        return audio_data
    
    def get_status(self) -> dict:
        """
        Get current recorder status for debugging/monitoring.
        
        Returns:
            dict: Status information
        """
        return {
            "is_recording": self.is_recording,
            "is_paused": self.is_paused,
            "buffer_duration_seconds": self.get_buffer_duration(),
            "buffer_max_seconds": self.buffer_minutes * 60,
            "sample_rate": self.sample_rate,
            "chunk_seconds": self.chunk_seconds,
            "buffer_chunks": len(self.audio_buffer),
            "max_chunks": self.max_chunks
        }
    
    async def load_test_audio(self, audio_data: np.ndarray) -> bool:
        """
        Load test audio data into the buffer for testing purposes.
        
        Args:
            audio_data: Audio data array
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Clear existing buffer
            with self.buffer_lock:
                self.audio_buffer.clear()
                
                # Convert to chunks and add to buffer
                chunk_size = self.sample_rate * self.chunk_seconds
                num_chunks = len(audio_data) // chunk_size
                
                for i in range(num_chunks):
                    start_idx = i * chunk_size
                    end_idx = start_idx + chunk_size
                    chunk = audio_data[start_idx:end_idx]
                    self.audio_buffer.append(chunk)
                
                # Add remaining data as final chunk if any
                remaining = len(audio_data) % chunk_size
                if remaining > 0:
                    final_chunk = audio_data[-remaining:]
                    # Pad to full chunk size
                    padded_chunk = np.zeros(chunk_size)
                    padded_chunk[:remaining] = final_chunk
                    self.audio_buffer.append(padded_chunk)
            
            print(f"✅ Test audio loaded: {len(self.audio_buffer)} chunks, {self.get_buffer_duration():.1f}s")
            return True
            
        except Exception as e:
            print(f"❌ Failed to load test audio: {e}")
            return False