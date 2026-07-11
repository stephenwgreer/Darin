"""Deepgram batch (prerecorded) transcription utilities.

Uploads audio from memory (WAV encoded in an ``io.BytesIO`` via soundfile)
to Deepgram's REST API using the v4 SDK with the nova-3 model. Failures
RAISE — an error string is never returned as a transcript.
"""

from __future__ import annotations

import io
import time

import numpy as np
import soundfile as sf
from deepgram import DeepgramClient, PrerecordedOptions
from loguru import logger

import config


def transcribe_with_deepgram(api_key: str, audio_data: np.ndarray, sample_rate: int) -> str:
    """Transcribe audio in memory using the Deepgram REST API (nova-3).

    Args:
        api_key: Deepgram API key.
        audio_data: Audio samples as a numpy array (mono int16 expected;
            any soundfile-encodable array works).
        sample_rate: Sample rate of the audio in Hz.

    Returns:
        The transcribed text (may be empty for silent audio).

    Raises:
        ValueError: If audio_data is empty.
        Exception: Any Deepgram SDK/API error is propagated to the caller —
            errors are never returned as transcript strings.
    """
    if audio_data is None or len(audio_data) == 0:
        raise ValueError("Audio data cannot be empty")

    # Encode WAV entirely in memory — no temp file side effects
    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, audio_data, samplerate=sample_rate, format="WAV", subtype="PCM_16")
    payload = wav_buffer.getvalue()

    logger.info(
        "Transcribing audio via Deepgram REST",
        model=config.DEEPGRAM_MODEL,
        samples=len(audio_data),
        sample_rate=sample_rate,
        wav_bytes=len(payload),
    )

    options = PrerecordedOptions(
        model=config.DEEPGRAM_MODEL,
        language=config.DEEPGRAM_LANGUAGE,
        smart_format=True,
    )

    start = time.perf_counter()
    client = DeepgramClient(api_key)
    response = client.listen.rest.v("1").transcribe_file({"buffer": payload}, options)

    try:
        transcript: str = response.results.channels[0].alternatives[0].transcript
    except (AttributeError, IndexError) as e:
        raise RuntimeError(f"Unexpected Deepgram response shape: {e}") from e

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "Deepgram batch transcription complete",
        transcript_length=len(transcript),
        duration_ms=f"{duration_ms:.2f}",
    )
    return transcript
