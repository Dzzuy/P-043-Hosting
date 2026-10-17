"""Voice boundaries reuse the existing saved Practice turn, ownership and history."""

import httpx
import pytest
from fastapi import FastAPI, Header, HTTPException

from src.agents.roleplay.state import RoleplayMessage
from src.api.practice_errors import PracticeAPIError, practice_exception_handler
from src.api.recorded_practice import create_recorded_practice_routers
from src.config import Settings
from src.integrations.practice_records import SQLPracticeRecordsRepository
from src.integrations.voice_usage import SQLVoiceUsageRepository
from src.models.auth import AuthenticatedUser
from src.services.practice import PracticeSessionView
from src.services.recorded_practice import RecordedPracticeService
from src.services.voice import Transcription, VoiceProviderError, VoiceProviderUnavailableError, VoiceService

MANAGER_VOICE_USAGE_PATH = "/api/v1/manager/reviews/voice-session/voice/usage"


class PracticeStub:
    def __init__(self):
        self.session = PracticeSessionView(
            session_id="voice-session",
            scenario_id="scenario-1",
            difficulty="easy",
            conversation_stage="opening",
            turn_count=0,
            max_turns=5,
            visible_context="Khách hỏi xe.",
            termination_status="active",
            messages=[RoleplayMessage(message_id="customer-1", role="customer", content="Chào em.")],
        )

    async def start_session(self, scenario_id, max_turns=None):
        return self.session

    async def get_session(self, session_id):
        return self.session

    async def send_message(self, session_id, message):
        self.session.messages.append(RoleplayMessage(message_id="advisor-1", role="advisor", content=message))
        self.session.messages.append(
            RoleplayMessage(message_id="customer-2", role="customer", content="Anh cần xem VF 5.")
        )
        self.session.turn_count += 1
        return self.session


class TranscriberStub:
    def __init__(self, text="Em chào anh.", error=None):
        self.text = text
        self.error = error

    async def transcribe(self, audio, mime_type):
        if self.error:
            raise self.error
        assert audio == b"recorded-audio"
        assert mime_type == "audio/webm"
        return Transcription(self.text, 2.0)


class SynthesizerStub:
    async def synthesize(self, text, gender):
        assert text == "Anh cần xem VF 5."
        assert gender == "male"
        return b"mp3-data"


async def fake_identity(x_test_identity: str = Header(default="advisor-a:advisor")):
    user_id, role = x_test_identity.split(":")
    if role not in {"advisor", "manager"}:
        raise HTTPException(status_code=401)
    return AuthenticatedUser(user_id=user_id, username=user_id, display_name=user_id, role=role)


async def make_client(tmp_path, transcriber=None):
    practice = PracticeStub()
    database_url = f"sqlite:///{tmp_path / 'voice.db'}"
    records = SQLPracticeRecordsRepository(database_url)
    service = RecordedPracticeService(practice, records)
    voice = VoiceService(
        service,
        SQLVoiceUsageRepository(database_url),
        Settings(
            _env_file=None,
            vector_store_type="memory",
            voice_stt_usd_per_hour=0.04,
            voice_tts_usd_per_million_characters=16,
        ),
        transcriber=transcriber or TranscriberStub(),
        synthesizer=SynthesizerStub(),
    )
    router, manager_router = create_recorded_practice_routers(service, fake_identity, voice)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(router, prefix="/api/v1")
    app.include_router(manager_router, prefix="/api/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as bootstrap:
        await bootstrap.post("/api/v1/practice/sessions", json={"scenario_id": "scenario-1"})
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test"), practice


@pytest.mark.asyncio
async def test_voice_transcript_is_reviewed_then_uses_normal_message_flow(tmp_path):
    client, practice = await make_client(tmp_path)
    async with client:
        transcript = await client.post(
            "/api/v1/practice/voice-session/voice/transcribe?duration_seconds=2",
            headers={"Content-Type": "audio/webm"},
            content=b"recorded-audio",
        )
        assert transcript.status_code == 200
        assert transcript.json() == {"transcript": "Em chào anh."}
        assert len(practice.session.messages) == 1  # STT never advances the role-play.

        sent = await client.post("/api/v1/practice/voice-session/message", json={"message": "Em chào anh."})
        assert sent.status_code == 200
        assert [message["content"] for message in sent.json()["messages"]][-2:] == [
            "Em chào anh.",
            "Anh cần xem VF 5.",
        ]
        speech = await client.post(
            "/api/v1/practice/voice-session/voice/speech",
            json={"message_id": "customer-2", "gender": "male"},
        )
        assert speech.status_code == 200
        assert speech.headers["content-type"] == "audio/mpeg"
        assert speech.content == b"mp3-data"
        usage_response = await client.get(MANAGER_VOICE_USAGE_PATH, headers={"X-Test-Identity": "manager-a:manager"})
        assert usage_response.status_code == 200
        usage = usage_response.json()
        assert usage["stt_requests"] == 1
        assert usage["stt_billed_seconds"] == 10
        assert usage["tts_requests"] == 1
        assert usage["tts_characters"] == len("Anh cần xem VF 5.")
        assert usage["estimated_usd"] == pytest.approx(10 * 0.04 / 3600 + len("Anh cần xem VF 5.") * 16 / 1_000_000)


@pytest.mark.asyncio
async def test_voice_enforces_ownership_and_validates_audio_and_customer_message(tmp_path):
    client, _ = await make_client(tmp_path)
    async with client:
        path = "/api/v1/practice/voice-session/voice/transcribe?duration_seconds=2"
        assert (
            await client.post(path, headers={"X-Test-Identity": "manager-a:manager"}, content=b"x")
        ).status_code == 403
        assert (
            await client.post(
                path,
                headers={"X-Test-Identity": "advisor-b:advisor", "Content-Type": "audio/webm"},
                content=b"recorded-audio",
            )
        ).status_code == 404
        assert (await client.post(path, headers={"Content-Type": "text/plain"}, content=b"x")).status_code == 422
        assert (
            await client.post(path, headers={"Content-Type": "audio/webm"}, content=b"x" * 4_000_001)
        ).status_code == 413
        assert (
            await client.post(
                "/api/v1/practice/voice-session/voice/speech",
                json={"message_id": "not-a-customer", "gender": "female"},
            )
        ).status_code == 422
        assert (await client.get(MANAGER_VOICE_USAGE_PATH)).status_code == 403
        assert (await client.get("/api/v1/practice/voice-session/voice/usage")).status_code == 404
        assert (
            await client.get(
                "/api/v1/manager/reviews/missing-session/voice/usage",
                headers={"X-Test-Identity": "manager-a:manager"},
            )
        ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("transcriber", "expected_status", "expected_usage"),
    [
        (TranscriberStub(text=""), 422, 1),
        (TranscriberStub(error=VoiceProviderError("failed")), 502, 0),
        (TranscriberStub(error=VoiceProviderUnavailableError("not configured")), 503, 0),
    ],
)
async def test_voice_failure_is_retryable_and_only_billable_calls_are_counted(
    tmp_path, transcriber, expected_status, expected_usage
):
    client, practice = await make_client(tmp_path, transcriber)
    async with client:
        response = await client.post(
            "/api/v1/practice/voice-session/voice/transcribe?duration_seconds=2",
            headers={"Content-Type": "audio/webm"},
            content=b"recorded-audio",
        )
        assert response.status_code == expected_status
        assert len(practice.session.messages) == 1
        usage = (await client.get(MANAGER_VOICE_USAGE_PATH, headers={"X-Test-Identity": "manager-a:manager"})).json()
        assert usage["stt_requests"] == expected_usage


@pytest.mark.asyncio
async def test_voice_accepts_recordings_up_to_ninety_seconds(tmp_path):
    client, _ = await make_client(tmp_path)
    async with client:
        base = "/api/v1/practice/voice-session/voice/transcribe?duration_seconds="
        headers = {"Content-Type": "audio/webm"}
        assert (await client.post(base + "90", headers=headers, content=b"recorded-audio")).status_code == 200
        assert (await client.post(base + "91", headers=headers, content=b"recorded-audio")).status_code == 422


@pytest.mark.asyncio
async def test_voice_errors_have_stable_localized_codes(tmp_path):
    client, _ = await make_client(tmp_path, TranscriberStub(error=VoiceProviderUnavailableError("secret config")))
    async with client:
        path = "/api/v1/practice/voice-session/voice/transcribe?duration_seconds="
        headers = {"Content-Type": "audio/webm"}
        too_long = await client.post(path + "91", headers=headers, content=b"recorded-audio")
        assert too_long.status_code == 422
        assert too_long.json() == {
            "code": "voice_too_long",
            "detail": "Bản ghi dài hơn 90 giây. Vui lòng ghi ngắn hơn.",
        }
        unavailable = await client.post(path + "2", headers=headers, content=b"recorded-audio")
        assert unavailable.status_code == 503
        assert unavailable.json() == {
            "code": "voice_not_configured",
            "detail": "Tính năng giọng nói chưa được cấu hình. Vui lòng nhập bằng bàn phím.",
        }
        assert "secret" not in unavailable.text


@pytest.mark.asyncio
async def test_voice_finished_session_uses_session_finished_code(tmp_path):
    client, practice = await make_client(tmp_path)
    practice.session.termination_status = "completed"
    async with client:
        response = await client.post(
            "/api/v1/practice/voice-session/voice/transcribe?duration_seconds=2",
            headers={"Content-Type": "audio/webm"},
            content=b"recorded-audio",
        )
        assert response.status_code == 409
        assert response.json() == {
            "code": "session_finished",
            "detail": "Phiên luyện tập đã kết thúc và không nhận thêm tin nhắn.",
        }
