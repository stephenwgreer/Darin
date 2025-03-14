import os
import json
import anthropic
import requests
from api.anthropic_utils import process_with_anthropic
from api.deepgram_utils import transcribe_with_deepgram

class ApiClient:
    def __init__(self, anthropic_api_key=None, deepgram_api_key=None):
        self.anthropic_api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.deepgram_api_key = deepgram_api_key or os.environ.get("DEEPGRAM_API_KEY")
        self._anthropic_client = None
    
    @property
    def anthropic_client(self):
        """Lazy-load the Anthropic client when needed"""
        if not self._anthropic_client and self.anthropic_api_key:
            self._anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        return self._anthropic_client
    
    def process_with_anthropic(self, transcript_text, prompt_template=None):
        """Process transcript with Anthropic API and return JSON response"""
        if not self.anthropic_api_key:
            return {"error": "Anthropic API key not set"}
        
        try:
            return process_with_anthropic(
                self.anthropic_client, 
                transcript_text, 
                prompt_template
            )
        except Exception as e:
            return {"error": str(e)}
    
    def transcribe_with_deepgram(self, audio_data, sample_rate):
        """Transcribe audio using Deepgram API"""
        if not self.deepgram_api_key:
            return "Error: Deepgram API key not set"
        
        try:
            return transcribe_with_deepgram(
                self.deepgram_api_key,
                audio_data,
                sample_rate
            )
        except Exception as e:
            return f"Transcription error: {str(e)}"