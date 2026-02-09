import os
import json
import anthropic
import requests
from api.anthropic_utils import process_with_anthropic
from api.deepgram_utils import transcribe_with_deepgram
from anthropic import Anthropic
import config

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
    
    def process_with_anthropic(self, text, prompt_template=None, stream=True, callback=None):
        """Process text with Anthropic's Claude API with streaming support"""
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key not set")

        client = self.anthropic_client
        
        # Prepare the message content
        if prompt_template:
            content = prompt_template.format(transcript=text)
        else:
            content = text
            
        print("\n=== Sending prompt to Claude ===")
        print(f"Content:\n{content}\n")
            
        try:
            if stream:
                # Stream the response
                with client.messages.stream(
                    model=config.CLAUDE_MODEL,
                    max_tokens=config.MAX_TOKENS,
                    messages=[{"role": "user", "content": content}]
                ) as stream:
                    response_text = ""
                    for text in stream.text_stream:
                        print(f"Streaming chunk: {text}")  # Debug print
                        response_text += text
                        if callback:
                            callback(text)
                    print("\n=== Complete response ===")
                    print(response_text)
                    print("========================\n")
                    return response_text
            else:
                # Get complete response
                response = client.messages.create(
                    model=config.CLAUDE_MODEL,
                    max_tokens=config.MAX_TOKENS,
                    messages=[{"role": "user", "content": content}]
                )
                return response.content[0].text
                
        except Exception as e:
            raise Exception(f"Error processing with Claude: {str(e)}")
    
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