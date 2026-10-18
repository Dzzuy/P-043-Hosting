"""Verify exported payloads/topology and failure isolation without network access."""

import asyncio
import json
import logging
import threading
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import PrivateAttr, ValidationError
from starlette.responses import StreamingResponse

from src import observability as obs
from src.agents.copilot.runtime import bounded_io
from src.config import Settings


class SchemaFakeChatModel(FakeMessagesListChatModel, ChatOpenAI):
    """Use the real schema binding interface with in-memory fake responses."""

    _cursor: list[int] = PrivateAttr(default_factory=lambda: [0])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        # Schema binding makes a shallow model copy; calls still share one script.
        self.i = self._cursor[0]
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        self._cursor[0] = self.i
        return result


def schema_model(**kwargs):
    return SchemaFakeChatModel(api_key="test", base_url="https://openrouter.ai/api/v1", **kwargs)


class RecordingClient:
    def __init__(self):
        self.creates, self.updates = [], []

    def create_run(self, name, inputs, run_type, **kwargs):
        self.creates.append(deepcopy({"name": name, "inputs": inputs, "run_type": run_type, **kwargs}))

    def update_run(self, run_id, **kwargs):
        self.updates.append(deepcopy({"id": run_id, **kwargs}))

    def close(self, timeout=None):
        self.timeout = timeout


def settings(**kwargs):
    if kwargs.get("app_env") == "production":
        kwargs = {"auth_cookie_secure": True, "database_url": "postgresql://test:test@localhost/test",
                  "vector_store_type": "pgvector", "openrouter_api_key": "test-key", **kwargs}
    return Settings(
        _env_file=None, embedding_provider="openrouter" if kwargs.get("app_env") == "production" else "hash", **kwargs
    )


def make_app(client=None, **kwargs):
    service = obs.TelemetryService(settings(LANGSMITH_TRACING=client is not None, **kwargs), client=client)
    app = FastAPI()
    app.add_middleware(obs.CopilotTelemetryMiddleware, service=service)
    return app, service


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("POST", "/api/v1/copilot/query/stream"),
    ("POST", "/api/v1/copilot/knowledge"),
    ("POST", "/api/v1/copilot/knowledge/stream"),
    ("GET", "/api/v1/copilot/knowledge"),
])
async def test_shared_knowledge_and_stream_routes_are_correlated(method, path, caplog):
    caplog.set_level(logging.INFO, logger="src.telemetry")
    recorder = RecordingClient()
    app, _ = make_app(recorder)

    async def endpoint():
        return {"request_id": obs._request.get().request_id}

    app.add_api_route(path, endpoint, methods=[method])
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.request(method, path)
    assert response.status_code == 200
    assert response.json()["request_id"] == response.headers["x-request-id"]
    completed = next(record.telemetry for record in caplog.records
                     if getattr(record, "telemetry", {}).get("event") == "request_end")
    assert completed["route"] == path
    assert completed["duration_ms"] >= 0
    assert len(recorder.creates) == 1


@pytest.mark.asyncio
async def test_sse_dependency_failure_is_traced_even_with_http_200():
    recorder = RecordingClient()
    app, _ = make_app(recorder)

    @app.post("/api/v1/copilot/knowledge/stream")
    async def endpoint():
        async def events():
            # Match the real service: the worker inherits the request context.
            async def worker():
                obs.annotate(error_type="TimeoutError")
            await asyncio.create_task(worker())
            yield 'event: error\ndata: {"status":"error"}\n\n'
        return StreamingResponse(events(), media_type="text/event-stream")

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/v1/copilot/knowledge/stream")
    assert response.status_code == 200
    root = next(run for run in recorder.creates if run["name"] == "copilot.query")
    completed = [run for run in recorder.updates if run["id"] == root["id"]][-1]
    assert completed["error"] == "TimeoutError"
    assert completed["extra"]["metadata"]["http_status"] == 200
    assert completed["extra"]["metadata"]["error_type"] == "TimeoutError"


@pytest.mark.parametrize("status", [200, 401, 404, 409, 429, 503])
@pytest.mark.asyncio
async def test_header_and_root_trace_for_success_and_errors(status):
    recorder = RecordingClient()
    app, _ = make_app(recorder)

    @app.post("/api/v1/copilot/query")
    async def query():
        with obs.span("authentication"):
            if status != 200:
                raise HTTPException(status, "private detail")
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        result = await client.post("/api/v1/copilot/query", headers={"X-Request-ID": "untrusted"})
    assert result.status_code == status
    request_id = result.headers["x-request-id"]
    assert len(request_id) == 32 and request_id != "untrusted"
    roots = [r for r in recorder.creates if r["name"] == "copilot.query"]
    assert len(roots) == 1 and str(roots[0]["id"]).replace("-", "") == request_id
    completed = [r for r in recorder.updates if r["id"] == roots[0]["id"]][-1]
    assert completed["extra"]["metadata"]["http_status"] == status


@pytest.mark.asyncio
async def test_validation_and_unhandled_errors_have_id_and_safe_error():
    recorder = RecordingClient()
    app, _ = make_app(recorder)

    @app.post("/api/v1/copilot/query")
    async def query(required: int):
        raise ValueError("postgresql://user:password@db secret-prompt")

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        invalid = await client.post("/api/v1/copilot/query")
        broken = await client.post("/api/v1/copilot/query?required=1")
    assert invalid.status_code == 422 and invalid.headers["x-request-id"]
    assert broken.status_code == 500 and broken.headers["x-request-id"]
    assert "password" not in json.dumps(recorder.updates, default=str)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capture,allow,app_env",
    [
        (False, True, "development"),
        (True, False, "development"),
        (True, True, "development"),
        (False, True, "production"),
    ],
)
async def test_native_graph_payloads_guard_content_and_usage(capture, allow, app_env):
    recorder = RecordingClient()
    app, _ = make_app(recorder, langsmith_capture_content=capture, app_env=app_env)
    model = schema_model(
        responses=[
            AIMessage(
                content="approved-answer sk-secret123 user@example.com",
                usage_metadata={"input_tokens": 8, "output_tokens": 3, "total_tokens": 11},
            )
        ]
    )

    async def node(state):
        if allow:
            obs.allow_content()
        await model.ainvoke([HumanMessage(content="approved-query Authorization: Bearer token123")])
        return {"private": "corpus-snapshot-secret"}

    graph = StateGraph(dict)
    graph.add_node("answer", node)
    graph.add_edge(START, "answer")
    graph.add_edge("answer", END)
    graph = graph.compile()

    @app.post("/api/v1/copilot/query")
    async def query():
        await graph.ainvoke({"private": "private-history"}, config=obs.graph_config())
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        assert (await client.post("/api/v1/copilot/query")).status_code == 200
    payload = json.dumps([recorder.creates, recorder.updates], default=str)
    assert "private-history" not in payload and "corpus-snapshot-secret" not in payload
    assert "token123" not in payload and "sk-secret123" not in payload and "user@example.com" not in payload
    assert ("approved-query" in payload) == (capture and allow)
    assert ("approved-answer" in payload) == (capture and allow)
    native = [r for r in recorder.creates if r["run_type"] == "llm"]
    assert len(native) == 1
    assert any(
        r.get("extra", {}).get("metadata", {}).get("usage_metadata", {}).get("total_tokens") == 11
        for r in recorder.updates
    )
    root = next(r for r in recorder.creates if r["name"] == "copilot.query")
    assert all(r["trace_id"] == root["trace_id"] for r in recorder.creates)
    ids = {r["id"] for r in recorder.creates}
    assert all(r.get("parent_run_id") in ids for r in recorder.creates if r["id"] != root["id"])


@pytest.mark.asyncio
async def test_parallel_requests_and_workers_keep_context(caplog):
    caplog.set_level(logging.INFO, logger="src.telemetry")
    recorder = RecordingClient()
    app, _ = make_app(recorder)

    @app.post("/api/v1/copilot/query")
    async def query():
        request_id = obs._request.get().request_id

        def worker():
            with obs.span("db.execute", backend="pgvector"):
                assert obs._request.get().request_id == request_id
                return request_id

        results = await asyncio.gather(bounded_io(worker, 1), bounded_io(worker, 1))
        assert results == [request_id, request_id]
        return {"request_id": request_id}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        responses = await asyncio.gather(*[client.post("/api/v1/copilot/query") for _ in range(2)])
    assert len({r.headers["x-request-id"] for r in responses}) == 2
    for response in responses:
        assert response.json()["request_id"] == response.headers["x-request-id"]
    roots = {r["id"]: r for r in recorder.creates if r["name"] == "copilot.query"}
    assert len(roots) == 2
    assert all(r["trace_id"] in roots for r in recorder.creates)
    durations = [
        r.telemetry["duration_ms"] for r in caplog.records if hasattr(r, "telemetry") and "duration_ms" in r.telemetry
    ]
    assert durations and all(d >= 0 for d in durations)


@pytest.mark.asyncio
async def test_timeout_retains_slot_and_records_late_completion(caplog):
    caplog.set_level(logging.INFO, logger="src.telemetry")
    recorder = RecordingClient()
    app, _ = make_app(recorder)
    release, entered, finished = threading.Event(), threading.Event(), threading.Event()

    @app.post("/api/v1/copilot/query")
    async def query():
        def worker():
            entered.set()
            release.wait(2)
            finished.set()

        with pytest.raises(TimeoutError):
            await bounded_io(worker, 0.02)
        return {"timed_out": True}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/v1/copilot/query")
    assert response.status_code == 200 and entered.is_set() and not finished.is_set()
    release.set()
    for _ in range(100):
        if any(r.get("extra", {}).get("metadata", {}).get("late_completion") for r in recorder.updates):
            break
        await asyncio.sleep(0.01)
    assert any(r.get("extra", {}).get("metadata", {}).get("late_completion") for r in recorder.updates)
    assert any(getattr(r, "telemetry", {}).get("event") == "timeout" for r in caplog.records)


@pytest.mark.asyncio
async def test_export_failure_disabled_sampling_and_other_routes():
    class BrokenClient(RecordingClient):
        def create_run(self, *args, **kwargs):
            raise ConnectionError("Authorization: Bearer dangerous-key")

        def update_run(self, *args, **kwargs):
            raise ConnectionError("cloud unavailable")

    app, _ = make_app(BrokenClient())

    @app.post("/api/v1/copilot/query")
    async def query():
        with obs.span("readiness"):
            return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        assert (await client.post("/api/v1/copilot/query")).status_code == 200
    recorder = RecordingClient()
    app, _ = make_app(recorder, langsmith_sampling_rate=0)
    app.post("/api/v1/copilot/query")(query)
    app.post("/api/v1/roleplay/query")(query)
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        await client.post("/api/v1/copilot/query")
        roleplay = await client.post("/api/v1/roleplay/query")
    assert recorder.creates == [] and "x-request-id" not in roleplay.headers


def test_configuration_defaults_aliases_and_production_guard(monkeypatch):
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    assert settings().langsmith_tracing is False
    assert settings(LANGCHAIN_TRACING_V2=True).langsmith_tracing is True
    assert settings(LANGSMITH_TRACING=False, LANGCHAIN_TRACING_V2=True).langsmith_tracing is False
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", langsmith_capture_content=True)
    assert settings(app_env="production").langsmith_project == "p043-copilot-prod"


def test_content_is_structured_redacted_and_bounded():
    from src.agents.copilot.state import Requirement

    class RuntimeSecret:
        def __str__(self):
            raise AssertionError("Runtime objects must not be serialized")

    content = obs.safe_content({
        "query": "VF 5 user@example.com 0901234567 sk-secret123",
        "requirements": [Requirement(requirement_id="R1", description="VF 5", kind="fact")],
        "analysis": {"decision": "allow", "OPENROUTER_API_KEY": "never-upload", "password": "hidden"},
        "runtime": RuntimeSecret(), "snapshot": RuntimeSecret(), "progress_queue": RuntimeSecret(),
        "customer_context": "private-crm", "unknown_state": "not-approved",
    }, state=True)
    assert content["requirements"][0]["description"] == "VF 5"
    assert content["analysis"] == {"decision": "allow"}
    serialized = json.dumps(content)
    for secret in ["user@example.com", "0901234567", "sk-secret123", "never-upload", "private-crm", "not-approved"]:
        assert secret not in serialized
    large = obs.safe_content({"answer_context": "x" * 100000, "selected_evidence": [{"content": "y" * 16000}] * 100}, state=True)
    assert len(json.dumps(large)) < 66000
    assert "[TRUNCATED]" in json.dumps(large)


@pytest.mark.asyncio
@pytest.mark.parametrize("capture", [False, True])
async def test_shared_knowledge_content_exports_root_nodes_and_model_only_when_enabled(capture):
    recorder = RecordingClient()
    app, _ = make_app(recorder, langsmith_capture_content=capture, app_env="development")
    model = schema_model(responses=[AIMessage(content="checked-answer")])

    async def analyze(state):
        await model.ainvoke([HumanMessage(content=state["query"])])
        return {"analysis": {"route": "simple"}, "draft_answer": "node-draft", "runtime": object()}

    graph = StateGraph(dict)
    graph.add_node("analyze_and_route", analyze)
    graph.add_edge(START, "analyze_and_route")
    graph.add_edge("analyze_and_route", END)

    @app.post("/api/v1/copilot/knowledge/stream")
    async def query():
        obs.capture_knowledge_input("VF 5 safe-question user@example.com")
        await graph.compile().ainvoke({"query": "safe-question", "snapshot": object()}, config=obs.graph_config())
        obs.capture_knowledge_output({"answer": "persisted-final-answer", "status": "answered"})
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as http:
        assert (await http.post("/api/v1/copilot/knowledge/stream")).status_code == 200
    root = next(run for run in recorder.creates if run["name"] == "copilot.query")
    completed = next(run for run in recorder.updates if run["id"] == root["id"])
    node = next(run for run in recorder.creates if run["name"] == "analyze_and_route")
    node_end = next(run for run in recorder.updates if run["id"] == node["id"])
    payload = json.dumps([recorder.creates, recorder.updates], default=str)
    for text in ["safe-question", "node-draft", "checked-answer", "persisted-final-answer"]:
        assert (text in payload) == capture
    assert "user@example.com" not in payload and "snapshot" not in payload and "runtime" not in payload
    assert completed["extra"]["metadata"]["http_route"] == "/api/v1/copilot/knowledge/stream"
    if capture:
        assert "query" in completed["inputs"]
        assert completed["outputs"]["answer"] == "persisted-final-answer"
        assert node_end["outputs"]["analysis"]["route"] == "simple"
    else:
        assert not completed.get("inputs") and not completed.get("outputs") and not node_end["outputs"]


def test_exporter_configuration_and_shutdown(monkeypatch):
    captured = {}
    recorder = RecordingClient()

    def factory(**kwargs):
        captured.update(kwargs)
        return recorder

    monkeypatch.setattr(obs, "Client", factory)
    service = obs.TelemetryService(settings(LANGSMITH_TRACING=True, LANGSMITH_API_KEY="test-key"))
    assert captured["timeout_ms"] == 2000 and captured["retry_config"].total == 1
    assert captured["auto_batch_tracing"] is True
    import os

    assert os.environ["LANGSMITH_TRACING_QUEUE_MAX_SIZE"] == "1000"
    assert os.environ["LANGSMITH_MAX_INGEST_MEMORY_BYTES"] == str(16 * 1024 * 1024)
    service.close()
    assert recorder.timeout == 2


@pytest.mark.asyncio
async def test_cancelled_request_closes_spans(caplog):
    caplog.set_level(logging.INFO, logger="src.telemetry")
    recorder = RecordingClient()
    app, _ = make_app(recorder)
    entered = asyncio.Event()

    @app.post("/api/v1/copilot/query")
    async def query():
        with obs.span("llm.provider"):
            entered.set()
            await asyncio.Event().wait()

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        task = asyncio.create_task(client.post("/api/v1/copilot/query"))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert any(r.get("error") == "CancelledError" for r in recorder.updates)
    assert any(getattr(r, "telemetry", {}).get("event") == "cancelled" for r in caplog.records)
    assert obs._request.get() is None


def test_metadata_allowlist_redaction_and_log_payload():
    assert obs.safe_metadata({"query": "hidden", "database_url": "hidden", "input_tokens": None}) == {
        "input_tokens": None
    }
    value = obs.redact(
        "sk-secret123 user@example.com Authorization: Bearer token123 postgresql://user:pw@db " + "x" * 20000
    )
    assert len(value) == 16000
    assert all(secret not in value for secret in ("secret123", "user@example.com", "token123", "user:pw"))
    formatter = obs.JsonFormatter()
    record = logging.LogRecord("langsmith.client", logging.WARNING, "", 1, "payload-secret", (), None)
    assert "payload-secret" not in formatter.format(record)


@pytest.mark.asyncio
async def test_sdk_full_queue_drops_telemetry_without_failing_query(monkeypatch):
    import langsmith.client as sdk

    sdk.ls_utils.get_env_var.cache_clear()
    monkeypatch.setattr(sdk, "_tracing_control_thread_func", lambda *_: None)
    monkeypatch.setenv("LANGSMITH_TRACING_QUEUE_MAX_SIZE", "1")
    client = sdk.Client(api_key="test-key", info={"batch_ingest_config": {"use_multipart_endpoint": False}})
    client.tracing_queue.put_nowait(("occupied", object()))
    app, _ = make_app(client)

    @app.post("/api/v1/copilot/query")
    async def query():
        with obs.span("readiness"):
            return {"ok": True}

    try:
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as http:
            assert (await http.post("/api/v1/copilot/query")).status_code == 200
        assert client.tracing_queue.qsize() == 1
    finally:
        client.tracing_queue.get_nowait()
        client.tracing_queue.task_done()
        client.close(timeout=0)


@pytest.mark.asyncio
async def test_model_parse_failure_is_safe_and_has_no_hidden_retry(monkeypatch):
    from pydantic import BaseModel

    from src.agents.copilot import model_io

    class Answer(BaseModel):
        ok: bool

    responses = [
        AIMessage(content="invalid-json"),
        AIMessage(content='{"ok":true}', usage_metadata={"input_tokens": 8, "output_tokens": 3, "total_tokens": 11}),
    ]
    model = schema_model(responses=responses)
    monkeypatch.setattr(model_io, "get_llm", lambda **_: model)
    recorder = RecordingClient()
    app, _ = make_app(recorder)

    @app.post("/api/v1/copilot/query")
    async def query():
        obs.allow_content()
        state = {}

        async def node(_):
            answer, _ = await model_io._invoke_json(state, "system", {"private": "secret-prompt"}, Answer)
            return {"ok": answer.ok}

        graph = StateGraph(dict)
        graph.add_node("answer", node)
        graph.add_edge(START, "answer")
        graph.add_edge("answer", END)
        from src.agents.copilot.errors import CopilotModelOutputError

        try:
            return await graph.compile().ainvoke({}, config=obs.graph_config())
        except CopilotModelOutputError:
            raise HTTPException(503, "Model output invalid") from None

    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as http:
        response = await http.post("/api/v1/copilot/query")
    assert response.status_code == 503
    attempts = [r for r in recorder.creates if r["name"] == "llm.attempt"]
    assert len(attempts) == 1
    failed = next(r for r in recorder.updates if r["id"] == attempts[0]["id"])
    assert failed["error"] == "CopilotModelOutputError"
    root_id = next(r["id"] for r in recorder.creates if r["name"] == "copilot.query")
    root = [r for r in recorder.updates if r["id"] == root_id][-1]["extra"]["metadata"]
    assert root["llm_attempts"] == 1 and root["provider_retry"] == 0
    assert root["input_tokens"] is None and root["output_tokens"] is None
    assert len([r for r in recorder.creates if r["run_type"] == "llm"]) == 1
    assert "secret-prompt" not in json.dumps([recorder.creates, recorder.updates], default=str)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
@pytest.mark.parametrize("surface", ["legacy", "knowledge", "knowledge_stream"])
async def test_real_copilot_http_graph_session_and_guard_export(client, tmp_path, monkeypatch, blocked, surface):
    from src.agents.copilot import model_io
    from src.agents.copilot.nodes import retrieval
    from src.agents.copilot.tools import _make_hit
    from src.api.copilot import current_copilot_user
    from src.config import get_settings
    from src.integrations.copilot_sessions import SQLCopilotSessionsRepository
    from src.knowledge.index_readiness import CorpusSnapshot, load_snapshot
    from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk
    from src.main import app
    from tests.test_agents.test_copilot_agentic import checked, generated, intake

    recorder = RecordingClient()
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "")
    service = app.state.copilot_telemetry
    knowledge = surface != "legacy"
    for name, value in {"enabled": True, "client": recorder, "capture": blocked or knowledge, "sampling": 1.0}.items():
        monkeypatch.setattr(service, name, value)
    repository = SQLCopilotSessionsRepository(f"sqlite:///{tmp_path / 'sessions.db'}")
    monkeypatch.setattr(app.state, "copilot_sessions", repository)
    chunk = KnowledgeChunk(
        chunk_id="chunk-1",
        document_id="vf5",
        content="VF 5 chạy được 326 km.",
        metadata=ChunkMetadata(
            chunk_id="chunk-1",
            document_id="vf5",
            title="Thông số VF 5",
            document_type="product_specs",
            product_model="VF 5",
            effective_date="2026-01-01",
            source="https://example.com/vf5",
        ),
    )
    snapshot = CorpusSnapshot("test-corpus", load_snapshot().documents, {chunk.chunk_id: chunk})
    monkeypatch.setattr(app.state, "copilot_readiness", lambda: snapshot)

    async def user():
        return SimpleNamespace(user_id="observer")

    app.dependency_overrides[current_copilot_user] = user
    blocked_decision = intake("blocked")
    blocked_decision["guard_decision"] = {"decision": "block", "reason": "instruction_override"}
    outputs = [blocked_decision] if blocked else [intake(), generated(), checked()]
    model = schema_model(
        responses=[
            AIMessage(
                content=json.dumps(output), usage_metadata={"input_tokens": 8, "output_tokens": 3, "total_tokens": 11}
            )
            for output in outputs
        ]
    )
    monkeypatch.setattr(model_io, "get_llm", lambda **_: model)
    search = SimpleNamespace(search=lambda **_: [_make_hit(chunk, 0.9, 1, "dense")])
    monkeypatch.setattr(retrieval, "get_dense_search_engine", lambda: search)
    monkeypatch.setattr(retrieval, "get_bm25_search_engine", lambda: search)
    try:
        path = {"legacy": "/api/v1/copilot/query", "knowledge": "/api/v1/copilot/knowledge",
                "knowledge_stream": "/api/v1/copilot/knowledge/stream"}[surface]
        body = {"query": "Quãng đường VF 5?"}
        if not knowledge:
            body["customer_context"] = "private-context-never-upload"
        response = await client.post(path, json=body)
        assert response.status_code == 200
        if surface == "knowledge_stream":
            import re
            data = json.loads(re.search(r"event: final\ndata: (.*)", response.text).group(1))
        else:
            data = response.json()
        assert data["request_id"] == response.headers["x-request-id"]
        root = next(r for r in recorder.creates if r["name"] == "copilot.query")
        metadata = next(r for r in recorder.updates if r["id"] == root["id"])["extra"]["metadata"]
        assert metadata["input_tokens"] == len(outputs) * 8
        assert metadata["output_tokens"] == len(outputs) * 3
        assert metadata["outcome"] == ("abstained" if blocked else "answered")
        assert len([r for r in recorder.creates if r["run_type"] == "llm"]) == len(outputs)
        payload = json.dumps([recorder.creates, recorder.updates], ensure_ascii=False, default=str)
        assert "private-context-never-upload" not in payload
        assert ("Quãng đường VF 5?" in payload) == knowledge
        completed = next(r for r in recorder.updates if r["id"] == root["id"])
        if knowledge:
            assert completed["inputs"]["query"] == "Quãng đường VF 5?"
            assert completed["outputs"]["answer"] == data["answer"]
            assert any(r["name"] == "analyze_and_route" and r["outputs"].get("analysis") for r in recorder.updates)
            assert '"readiness_loader":' not in payload and '"snapshot":' not in payload
        if blocked:
            assert data["session_id"] == (repository.advisor_session("observer") if knowledge else None)
            assert not any(r["name"] == "session.save" for r in recorder.creates)
        else:
            kwargs = {"advisor": True} if knowledge else {}
            assert repository.load(data["session_id"], "observer", **kwargs)["history"]
            assert any(r["name"] == "db.execute" for r in recorder.creates)
        assert all(r["trace_id"] == root["trace_id"] for r in recorder.creates)
    finally:
        app.dependency_overrides.pop(current_copilot_user, None)
        repository.engine.dispose()
