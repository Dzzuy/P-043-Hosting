"""Optional speech I/O around the existing recorded Practice session flow."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from src.config import Settings
from src.integrations.voice_usage import SQLVoiceUsageRepository, VoiceUsageSummary
from src.services.recorded_practice import RecordedPracticeService

logger = logging.getLogger(__name__)
MAX_AUDIO_BYTES = 4_000_000
MAX_AUDIO_SECONDS = 90
ALLOWED_AUDIO_TYPES = {
    "audio/webm": "webm",
    "audio/mp4": "mp4",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}
VoiceGender = Literal["female", "male"]


class VoiceInputError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: Literal["voice_invalid_audio", "voice_too_long", "session_finished"] = "voice_invalid_audio",
    ) -> None:
        super().__init__(message)
        self.code = code


class VoiceProviderUnavailableError(RuntimeError):
    pass


class VoiceProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Transcription:
    text: str
    duration_seconds: float | None


class Transcriber(Protocol):
    async def transcribe(self, audio: bytes, mime_type: str) -> Transcription: ...


class Synthesizer(Protocol):
    async def synthesize(self, text: str, gender: VoiceGender) -> bytes: ...


class GroqWhisperTranscriber:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def transcribe(self, audio: bytes, mime_type: str) -> Transcription:
        if not self.api_key:
            raise VoiceProviderUnavailableError("Groq speech recognition is not configured")
        extension = ALLOWED_AUDIO_TYPES[mime_type]
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={
                        "model": "whisper-large-v3-turbo",
                        "language": "vi",
                        "response_format": "verbose_json",
                    },
                    files={"file": (f"recording.{extension}", audio, mime_type)},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Groq transcription failed: %s", type(exc).__name__)
            raise VoiceProviderError("Speech recognition is unavailable; retry the recording") from exc
        if not isinstance(payload, dict):
            raise VoiceProviderError("Speech recognition returned an invalid response")
        duration = payload.get("duration")
        return Transcription(
            text=str(payload.get("text") or "").strip(),
            duration_seconds=float(duration)
            if isinstance(duration, (int, float)) and math.isfinite(duration)
            else None,
        )


class GoogleWaveNetSynthesizer:
    def __init__(self, service_account_json: str) -> None:
        self.service_account_json = service_account_json

    async def synthesize(self, text: str, gender: VoiceGender) -> bytes:
        return await asyncio.to_thread(self._synthesize_sync, text, gender)

    def _synthesize_sync(self, text: str, gender: VoiceGender) -> bytes:
        from google.cloud import texttospeech

        try:
            if self.service_account_json:
                from google.oauth2 import service_account

                info = json.loads(self.service_account_json)
                credentials = service_account.Credentials.from_service_account_info(info)
                client = texttospeech.TextToSpeechClient(credentials=credentials)
            else:
                client = texttospeech.TextToSpeechClient()
        except Exception as exc:
            logger.warning("Google TTS credentials unavailable: %s", type(exc).__name__)
            raise VoiceProviderUnavailableError("Google speech synthesis is not configured") from exc
        try:
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code="vi-VN",
                    name="vi-VN-Wavenet-B" if gender == "male" else "vi-VN-Wavenet-A",
                ),
                audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3),
                timeout=20,
            )
        except Exception as exc:
            logger.warning("Google TTS failed: %s", type(exc).__name__)
            raise VoiceProviderError("Customer speech is unavailable; retry playback") from exc
        if not response.audio_content:
            raise VoiceProviderError("Customer speech returned empty audio")
        return response.audio_content


class VoiceService:
    def __init__(
        self,
        practice: RecordedPracticeService,
        usage: SQLVoiceUsageRepository,
        settings: Settings,
        *,
        transcriber: Transcriber | None = None,
        synthesizer: Synthesizer | None = None,
    ) -> None:
        self.practice = practice
        self.usage = usage
        self.settings = settings
        self.transcriber = transcriber or GroqWhisperTranscriber(settings.groq_api_key)
        self.synthesizer = synthesizer or GoogleWaveNetSynthesizer(settings.google_tts_service_account_json)

    async def transcribe(
        self, session_id: str, advisor_id: str, audio: bytes, mime_type: str, reported_seconds: float
    ) -> str:
        session = await self.practice.advisor_session(session_id, advisor_id)
        if session.termination_status != "active":
            raise VoiceInputError("This practice session no longer accepts messages", code="session_finished")
        if mime_type not in ALLOWED_AUDIO_TYPES or not audio or len(audio) > MAX_AUDIO_BYTES:
            raise VoiceInputError("Unsupported or oversized recording")
        if not math.isfinite(reported_seconds) or not 0 < reported_seconds <= MAX_AUDIO_SECONDS:
            raise VoiceInputError(f"Recording must be at most {MAX_AUDIO_SECONDS} seconds", code="voice_too_long")
        result = await self.transcriber.transcribe(audio, mime_type)
        duration = (
            result.duration_seconds if result.duration_seconds and result.duration_seconds > 0 else reported_seconds
        )
        billed_seconds = max(10.0, duration)
        await asyncio.to_thread(
            self.usage.record,
            session_id,
            "groq",
            "stt",
            billed_seconds,
            billed_seconds * self.settings.voice_stt_usd_per_hour / 3600,
        )
        if not result.text:
            raise VoiceInputError("No speech was recognized; please record again")
        return result.text

    async def synthesize(self, session_id: str, advisor_id: str, message_id: str, gender: VoiceGender) -> bytes:
        session = await self.practice.advisor_session(session_id, advisor_id)
        message = next(
            (item for item in session.messages if item.message_id == message_id and item.role == "customer"), None
        )
        if message is None:
            raise VoiceInputError("Customer message was not found in this session")
        if len(message.content.encode("utf-8")) > 5000:
            raise VoiceInputError("Customer reply is too long to synthesize")
        audio = await self.synthesizer.synthesize(message.content, gender)
        characters = len(message.content)
        await asyncio.to_thread(
            self.usage.record,
            session_id,
            "google",
            "tts",
            characters,
            characters * self.settings.voice_tts_usd_per_million_characters / 1_000_000,
        )
        return audio

    async def manager_usage_summary(self, session_id: str) -> VoiceUsageSummary:
        await self.practice.manager_attempt(session_id)
        return await asyncio.to_thread(self.usage.summary, session_id)
