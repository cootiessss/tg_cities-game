"""Распознавание голосовых сообщений (Speech-to-Text)."""

import io
import os
import tempfile
from typing import Optional

import speech_recognition as sr
from pydub import AudioSegment


async def convert_voice_to_text(voice_file) -> Optional[str]:
    """Скачивает голосовое сообщение, конвертирует в WAV и распознаёт текст."""
    recognizer = sr.Recognizer()
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio:
            await voice_file.download_to_drive(temp_audio.name)
            audio = AudioSegment.from_ogg(temp_audio.name)

            wav_io = io.BytesIO()
            audio.export(wav_io, format="wav")
            wav_io.seek(0)

            with sr.AudioFile(wav_io) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)

            return recognizer.recognize_google(audio_data, language="ru-RU")
    except Exception as e:
        print(f"Ошибка распознавания: {e}")
        return None
    finally:
        if "temp_audio" in locals():
            os.unlink(temp_audio.name)
