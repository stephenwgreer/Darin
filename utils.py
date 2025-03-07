import io
import requests
import audioop
import pyaudio
import wave
import numpy as np
from playsound import playsound
import speech_recognition as sr
from google.cloud import speech

def speech_to_text():
    # Create a Recognizer instance
    recognizer = sr.Recognizer()

    # Use the Microphone as the audio source
    with sr.Microphone() as source:
        # Adjust for ambient noise
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("Listening...")

        # Capture the audio
        audio_data = recognizer.listen(source)

        text= ""

        try:
            # Recognize speech using Google Web Speech API
            text = recognizer.recognize_google(audio_data)
            print("Transcription: ", text)
        except sr.UnknownValueError:
            print("Google Web Speech API could not understand the audio")
        except sr.RequestError as e:
            print(f"Could not request results from Google Web Speech API; {e}")
        
        return text