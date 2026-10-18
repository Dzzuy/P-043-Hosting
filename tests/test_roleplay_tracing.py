"""Verify isolated Practice traces using recording clients and offline models."""

import json
import logging
from copy import deepcopy

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context
from pydantic import SecretStr, ValidationError

from src import roleplay_tracing as tracing
from src.observability import TelemetryService, redact
from src.services.practice import PracticeEvaluationUnavailableError
from tests.test_roleplay.test_practice_service import build_lifecycle_service, build_service


class RecordingClient:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.creates, self.updates = [], []
        self.flushed = False

    def create_run(self, name, inputs, run_type, **kwargs):
        self.creates.append(deepcopy({"name": name, "inputs": inputs, "run_type": run_type, **kwargs}))

    def update_run(self, run_id, **kwargs):
        self.updates.append(deepcopy({"id": run_id, **kwargs}))

    def flush(self):
        self.flushed = True


def settings(**kwargs):
    return tracing.Settings(
        _env_file=None,
        embedding_provider="openrouter" if kwargs.get("app_env") == "production" else "hash",
        langsmith_tracing=False,
        langsmith_capture_content=False,
        roleplay_langsmith_tracing=False,
        roleplay_langsmith_api_key="",
        **kwargs,
    )


@pytest.fixture
def recorder(monkeypatch):
    client = RecordingClient()

    def factory(**kwargs):
        client.options = kwargs
        return client

    monkeypatch.setattr(tracing, "Client", factory)
    return client


def enabled_tracing():
    config = settings()
    config.roleplay_langsmith_tracing = True
    config.roleplay_langsmith_api_key = SecretStr("test-key")
    config.roleplay_langsmith_project = "separate-roleplay-project"
    return tracing.RoleplayTracing(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("injected", [False, True])
async def test_disabled_practice_still_works_without_client(monkeypatch, injected):
    def forbidden(**kwargs):
        pytest.fail("disabled tracing must not create a client")

    monkeypatch.setattr(tracing, "Client", forbidden)
    service, graph = build_service()
    if injected:
        service._tracing = tracing.RoleplayTracing(settings())
    with tracing_context(enabled=True):
        await service.start_session("SCENARIO_01_VF5_TAXI")
        await service.send_message("session-1", "private-message")
    assert graph.continue_calls == [("session-1", "private-message")]


@pytest.mark.parametrize("key", ["", "your-roleplay-langsmith-key-here", "  your-placeholder  "])
def test_missing_or_placeholder_key_disables_with_warning(recorder, caplog, key):
    config = settings()
    config.roleplay_langsmith_tracing = True
    config.roleplay_langsmith_api_key = SecretStr(key)
    with caplog.at_level(logging.WARNING, logger="src.roleplay_tracing"):
        service = tracing.RoleplayTracing(config)
    assert service.client is None
    assert "missing or placeholder" in caplog.text
    if key.strip():
        assert key.strip() not in caplog.text
    assert not recorder.options


@pytest.mark.parametrize("capture", [False, True])
def test_client_has_separate_credentials_and_capture_policy(recorder, capture):
    config = settings(roleplay_langsmith_capture_content=capture)
    config.roleplay_langsmith_tracing = True
    config.roleplay_langsmith_api_key = SecretStr("roleplay-test-key")
    config.roleplay_langsmith_endpoint = "https://roleplay.example.test"
    service = tracing.RoleplayTracing(config)
    assert service.client is recorder
    assert recorder.options == {
        "api_url": "https://roleplay.example.test",
        "api_key": "roleplay-test-key",
        "auto_batch_tracing": True,
        "timeout_ms": 2000,
        "hide_inputs": redact if capture else True,
        "hide_outputs": redact if capture else True,
    }


def test_production_rejects_content_capture(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ROLEPLAY_LANGSMITH_CAPTURE_CONTENT", "true")
    with pytest.raises(ValidationError, match="Roleplay LangSmith content capture"):
        settings()


@pytest.mark.parametrize(
    "environment,project",
    [("development", "p043-roleplay-dev"), ("test", "p043-roleplay-dev"), ("production", "p043-roleplay-prod")],
)
def test_default_project(environment, project):
    extra = {}
    if environment == "production":
        extra = {
            "auth_cookie_secure": True,
            "database_url": "postgresql://test:test@localhost/test",
            "vector_store_type": "pgvector",
            "openrouter_api_key": "test-key",
        }
    config = settings(app_env=environment, **extra)
    assert config.roleplay_langsmith_project == project


@pytest.mark.asyncio
async def test_turn_is_one_roleplay_root_with_nested_graph_and_model(recorder, monkeypatch):
    copilot_client = RecordingClient()
    copilot = TelemetryService(settings(), client=copilot_client)
    service, graph = build_service()
    service._tracing = enabled_tracing()
    model = FakeMessagesListChatModel(responses=[AIMessage(content="offline response")])

    def customer(state):
        model.invoke([HumanMessage(content="offline input")])
        return {}

    builder = StateGraph(dict)
    builder.add_node("customer", customer)
    builder.add_edge(START, "customer")
    builder.add_edge("customer", END)
    compiled = builder.compile()
    original = graph.continue_session

    async def continue_session(session_id, advisor_message):
        compiled.invoke({})
        return await original(session_id, advisor_message)

    monkeypatch.setattr(graph, "continue_session", continue_session)
    with tracing_context(enabled=False, client=copilot.client, project_name="copilot-project"):
        await service.send_message("session-1", "private advisor text")
        assert get_tracing_context()["enabled"] is False
    roots = [run for run in recorder.creates if run["name"] == "practice.turn"]
    assert len(roots) == 1
    root = roots[0]
    assert root.get("parent_run_id") is None
    assert root["session_name"] == "separate-roleplay-project"
    assert root["extra"]["metadata"] == {"session_id": "session-1", "kind": "send"}
    assert root["inputs"] == {}
    assert any(run["name"] == "LangGraph" and run["parent_run_id"] == root["id"] for run in recorder.creates)
    assert any(run["run_type"] == "llm" for run in recorder.creates)
    assert all(run["trace_id"] == root["trace_id"] for run in recorder.creates)
    assert not copilot_client.creates and not copilot_client.updates
    assert "private advisor text" not in json.dumps([recorder.creates, recorder.updates], default=str)


@pytest.mark.asyncio
async def test_start_retry_and_evaluation_scopes(recorder, monkeypatch):
    service, _, evaluator = build_lifecycle_service()
    service._tracing = enabled_tracing()
    await service.start_session("SCENARIO_01_VF5_TAXI")

    async def retry(session_id):
        assert get_tracing_context()["parent"].name == "practice.turn"
        return (await service.get_session(session_id)).model_dump()

    monkeypatch.setattr(service._graph, "retry_customer_reply", retry)
    await service.retry_customer_reply("session-1")
    await service.finish_session("session-1")
    await service.finish_session("session-1")
    assert evaluator.calls == 1
    assert [run["name"] for run in recorder.creates] == ["practice.start", "practice.turn", "practice.evaluate"]
    assert recorder.creates[1]["extra"]["metadata"]["kind"] == "retry"
    assert recorder.creates[2]["extra"]["metadata"] == {
        "session_id": "session-1",
        "scenario_id": "SCENARIO_01_VF5_TAXI",
    }


@pytest.mark.asyncio
async def test_evaluation_failure_marks_root_and_preserves_retry(recorder):
    service, _, evaluator = build_lifecycle_service()
    service._tracing = enabled_tracing()
    await service.start_session("SCENARIO_01_VF5_TAXI")
    evaluator.fail_next = True
    with pytest.raises(PracticeEvaluationUnavailableError):
        await service.finish_session("session-1")
    assert recorder.updates[-1]["error"] == "TimeoutError"
    await service.finish_session("session-1")
    assert recorder.updates[-1]["error"] is None


def test_root_errors_and_metadata_do_not_export_private_text(recorder):
    service = enabled_tracing()
    with pytest.raises(ValueError, match="private error text"):
        with service.trace("practice.turn", session_id="session-1", message="private-message", phone="0901234567"):
            raise ValueError("private error text")
    assert recorder.updates[-1]["error"] == "ValueError"
    assert recorder.creates[0]["extra"]["metadata"] == {"session_id": "session-1"}
    assert "private" not in json.dumps([recorder.creates, recorder.updates], default=str)


def test_client_construction_failure_is_nonfatal(monkeypatch, caplog):
    def fail(**kwargs):
        raise RuntimeError("private credentials")

    monkeypatch.setattr(tracing, "Client", fail)
    service = enabled_tracing()
    with service.trace("practice.turn"):
        assert get_tracing_context()["enabled"] is False
    assert service.client is None
    assert "RuntimeError" in caplog.text
    assert "private credentials" not in caplog.text


@pytest.mark.parametrize("operation", ["create_run", "update_run", "flush"])
def test_export_failure_is_nonfatal(recorder, monkeypatch, caplog, operation):
    def fail(*args, **kwargs):
        raise RuntimeError("private export error")

    service = enabled_tracing()
    monkeypatch.setattr(recorder, operation, fail)
    with service.trace("practice.turn"):
        pass
    service.close()
    assert "RuntimeError" in caplog.text
    assert "private export error" not in caplog.text


def test_close_flushes_client(recorder):
    service = enabled_tracing()
    service.close()
    assert recorder.flushed
    tracing.RoleplayTracing(settings()).close()
