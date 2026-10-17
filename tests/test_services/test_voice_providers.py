"""Verify outbound provider request shape without sending audio or credentials."""

import httpx
import pytest
from google.cloud import texttospeech

from src.services.voice import GoogleWaveNetSynthesizer, GroqWhisperTranscriber


@pytest.mark.asyncio
async def test_groq_request_uses_vietnamese_turbo_transcription(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "Em chào anh.", "duration": 2.3}

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = await GroqWhisperTranscriber("test-key").transcribe(b"audio", "audio/webm")
    assert result.text == "Em chào anh."
    assert result.duration_seconds == 2.3
    assert captured["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert captured["data"] == {
        "model": "whisper-large-v3-turbo",
        "language": "vi",
        "response_format": "verbose_json",
    }
    assert captured["files"]["file"] == ("recording.webm", b"audio", "audio/webm")


@pytest.mark.parametrize(
    ("gender", "voice_name"),
    [("female", "vi-VN-Wavenet-A"), ("male", "vi-VN-Wavenet-B")],
)
def test_google_request_selects_vietnamese_wavenet_voice(monkeypatch, gender, voice_name):
    captured = {}

    class FakeClient:
        def synthesize_speech(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"audio_content": b"mp3"})()

    monkeypatch.setattr(texttospeech, "TextToSpeechClient", FakeClient)
    audio = GoogleWaveNetSynthesizer("")._synthesize_sync("Xin chào anh.", gender)
    assert audio == b"mp3"
    assert captured["input"].text == "Xin chào anh."
    assert captured["voice"].language_code == "vi-VN"
    assert captured["voice"].name == voice_name
    assert captured["audio_config"].audio_encoding == texttospeech.AudioEncoding.MP3
    assert captured["timeout"] == 20
