"""Deepgram API utilities for audio transcription."""

import json
import time
from typing import Any

import requests  # type: ignore[import-untyped]
import soundfile as sf  # type: ignore[import-untyped]


_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 1.0
_BACKOFF_MULTIPLIER = 2.0
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def transcribe_with_deepgram(api_key: str, audio_data: Any, sample_rate: int) -> str:
    """
    Transcribe audio using Deepgram API.

    Args:
        api_key: Deepgram API key
        audio_data: Audio data as numpy array
        sample_rate: Sample rate of audio in Hz

    Returns:
        Transcribed text string
    """
    # Save audio to temporary file
    temp_file = "BSGPT_REC.wav"
    if audio_data is not None:
        sf.write(file=temp_file, data=audio_data, samplerate=sample_rate)

    print("Transcribing audio...")

    url = "https://api.deepgram.com/v1/listen"
    headers = {"Authorization": f"Token {api_key}"}
    params = {"punctuate": "true", "model": "general", "language": "en-US"}

    attempt = 0
    backoff = _INITIAL_BACKOFF_S

    while attempt <= _MAX_RETRIES:
        with open(temp_file, "rb") as audio:
            try:
                response = requests.post(url, headers=headers, params=params, data=audio)
            except requests.ConnectionError as e:
                if attempt < _MAX_RETRIES:
                    print(
                        f"Connection error, retrying in {backoff}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                    )
                    time.sleep(backoff)
                    backoff *= _BACKOFF_MULTIPLIER
                    attempt += 1
                    continue
                return f"Error: connection failed after {_MAX_RETRIES} retries: {e}"

        if response.status_code == 200:
            response_json = response.json()

            # Debug logging
            print("Full response structure:")
            print(json.dumps(response_json, indent=2))

            try:
                transcript: str = response_json["results"]["channels"][0]["alternatives"][0][
                    "transcript"
                ]
                print(f"Found transcript: {transcript}")
                return transcript
            except KeyError:
                print("Standard path not found, examining response structure...")
                return "Error: Could not locate transcript in response. Check console output for structure."

        elif response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
            print(
                f"Deepgram returned {response.status_code}, retrying in {backoff}s (attempt {attempt + 1}/{_MAX_RETRIES})"
            )
            time.sleep(backoff)
            backoff *= _BACKOFF_MULTIPLIER
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            return f"Error: {response.status_code} - {response.text}"

        attempt += 1

    return f"Error: Deepgram transcription failed after {_MAX_RETRIES} retries"
