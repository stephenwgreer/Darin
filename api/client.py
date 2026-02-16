"""API client for Anthropic and Deepgram services.

Provides high-level interface for transcription and AI processing.
"""

from collections.abc import Callable

from anthropic import Anthropic, APIConnectionError, APIError, RateLimitError
from loguru import logger

import config
from api.deepgram_utils import transcribe_with_deepgram


class ApiClient:
    """Client for interacting with Anthropic and Deepgram APIs."""

    def __init__(
        self, anthropic_api_key: str | None = None, deepgram_api_key: str | None = None
    ) -> None:
        """
        Initialize API client with validated API keys.

        Args:
            anthropic_api_key: Optional override for Anthropic API key (uses config default)
            deepgram_api_key: Optional override for Deepgram API key (uses config default)

        Raises:
            ValueError: If API keys are invalid (empty or whitespace-only)

        Note:
            If keys are not provided, uses validated keys from config module.
            Keys are validated at application startup in main.py.
        """
        # Use provided keys or fall back to validated config module keys
        self.anthropic_api_key = anthropic_api_key or config.ANTHROPIC_API_KEY
        self.deepgram_api_key = deepgram_api_key or config.DEEPGRAM_API_KEY

        # Validate keys are present and non-empty
        if not self.anthropic_api_key or not self.anthropic_api_key.strip():
            raise ValueError("Anthropic API key must be provided and non-empty")
        if not self.deepgram_api_key or not self.deepgram_api_key.strip():
            raise ValueError("Deepgram API key must be provided and non-empty")

        self._anthropic_client: Anthropic | None = None

    @property
    def anthropic_client(self) -> Anthropic:
        """Lazy-load the Anthropic client when needed."""
        if self._anthropic_client is None:
            self._anthropic_client = Anthropic(api_key=self.anthropic_api_key)
        return self._anthropic_client

    def process_with_anthropic(
        self,
        text: str,
        prompt_template: str | None = None,
        stream: bool = True,
        callback: Callable[[str], None] | None = None,
    ) -> str:
        """
        Process text with Anthropic's Claude API with streaming support.

        Args:
            text: Input text to process
            prompt_template: Optional template string with {transcript} placeholder
            stream: Whether to stream the response
            callback: Optional callback function for streaming chunks

        Returns:
            Complete response text from Claude

        Raises:
            ValueError: If Anthropic API key is not set
            APIError: If Anthropic API returns an error
            APIConnectionError: If network connection fails
            RateLimitError: If rate limit is exceeded
        """
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key not set")

        client = self.anthropic_client

        # Prepare the message content
        if prompt_template:
            content = prompt_template.format(transcript=text)
        else:
            content = text

        logger.info("Sending prompt to Claude API")
        logger.debug(f"Content length: {len(content)} characters")

        try:
            if stream:
                # Stream the response using list comprehension for efficiency
                response_chunks: list[str] = []
                with client.messages.stream(
                    model=config.CLAUDE_MODEL,
                    max_tokens=config.MAX_TOKENS,
                    messages=[{"role": "user", "content": content}],
                ) as stream_context:
                    for chunk_text in stream_context.text_stream:
                        logger.debug(f"Received chunk: {len(chunk_text)} chars")
                        response_chunks.append(chunk_text)
                        if callback:
                            callback(chunk_text)

                response_text = "".join(response_chunks)
                logger.info(f"Completed streaming response: {len(response_text)} chars")
                return response_text
            else:
                # Get complete response
                response = client.messages.create(
                    model=config.CLAUDE_MODEL,
                    max_tokens=config.MAX_TOKENS,
                    messages=[{"role": "user", "content": content}],
                )
                # Extract text from first content block
                first_block = response.content[0]
                if hasattr(first_block, "text"):
                    response_text = first_block.text
                    logger.info(f"Received complete response: {len(response_text)} chars")
                    return response_text
                else:
                    error_msg = f"Unexpected content block type: {type(first_block)}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

        except RateLimitError as e:
            logger.error(f"Rate limit exceeded: {e}")
            raise RuntimeError("Claude API rate limit exceeded. Please try again later.") from e
        except APIConnectionError as e:
            logger.error(f"API connection failed: {e}")
            raise RuntimeError(
                "Failed to connect to Claude API. Check your network connection."
            ) from e
        except APIError as e:
            logger.error(f"Claude API error: {e}")
            raise RuntimeError(f"Error processing with Claude: {e}") from e

    def transcribe_with_deepgram(self, audio_data: bytes, sample_rate: int) -> str:
        """
        Transcribe audio using Deepgram API.

        Args:
            audio_data: Raw audio bytes to transcribe
            sample_rate: Sample rate of the audio in Hz

        Returns:
            Transcribed text

        Raises:
            ValueError: If Deepgram API key is not set or audio data is invalid
            RuntimeError: If transcription fails
        """
        if not self.deepgram_api_key:
            raise ValueError("Deepgram API key not set")

        if audio_data is None or len(audio_data) == 0:
            raise ValueError("Audio data cannot be empty")

        logger.info(f"Transcribing audio: {len(audio_data)} bytes at {sample_rate} Hz")

        try:
            result = transcribe_with_deepgram(self.deepgram_api_key, audio_data, sample_rate)
            logger.info(f"Transcription complete: {len(result)} characters")
            return result
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise RuntimeError(f"Transcription error: {e}") from e
