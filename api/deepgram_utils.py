import json
import requests
import soundfile as sf

def transcribe_with_deepgram(api_key, audio_data, sample_rate):
    """
    Transcribe audio using Deepgram API
    
    Args:
        api_key: Deepgram API key
        audio_data: Audio data as numpy array
        sample_rate: Sample rate of audio
        
    Returns:
        Transcribed text
    """
    # Save audio to temporary file
    temp_file = "BSGPT_REC.wav"
    if audio_data is not None:
        sf.write(file=temp_file, data=audio_data, samplerate=sample_rate)
    
    print("Transcribing audio...")

    # Deepgram API endpoint
    url = "https://api.deepgram.com/v1/listen"

    # Request headers
    headers = {
        "Authorization": f"Token {api_key}"
    }
    
    # Parameters for the transcription
    params = {
        "punctuate": "true",
        "model": "general",
        "language": "en-US"
    }
    
    with open(temp_file, "rb") as audio:
        # Send the request to Deepgram
        response = requests.post(
            url,
            headers=headers,
            params=params,
            data=audio
        )
    
    if response.status_code == 200:
        response_json = response.json()
        
        # Debug logging
        print("Full response structure:")
        print(json.dumps(response_json, indent=2))
        
        # Extract transcript from response
        try:
            transcript = response_json["results"]["channels"][0]["alternatives"][0]["transcript"]
            print(f"Found transcript: {transcript}")
            return transcript
        except KeyError:
            print("Standard path not found, examining response structure...")
            return "Error: Could not locate transcript in response. Check console output for structure."
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return f"Error: {response.status_code} - {response.text}"