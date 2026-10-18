"""Shared graph execution, owned sessions and request lifecycle for Copilot."""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import SQLAlchemyError

from src.agents.copilot.graph import copilot_agent
from src.agents.copilot.nodes import CopilotDependencyError
from src.agents.copilot.runtime import AdmissionError, BudgetExhaustedError, RuntimeBudget, bounded_io
from src.agents.copilot.state import CopilotResponse
from src.agents.copilot.summarizer import format_summary_for_context, maybe_trigger_background_summarization
from src.config import get_settings
from src.integrations.copilot_sessions import CopilotSessionConflictError, CopilotSessionNotFoundError
from src.knowledge.index_readiness import IndexNotReadyError
from src.models.copilot import CopilotQueryRequest, CopilotQueryResponse
from src.observability import annotate, capture_knowledge_input, capture_knowledge_output, graph_config, span
from src.services.customer_lookup_context import authorize_customer, build_customer_context
from src.services.semantic_cache import semantic_cache

logger = logging.getLogger(__name__)


class CopilotStreamingResponse(StreamingResponse):
    """Release admission even when the socket fails before the body iterator starts."""

    def __init__(self, *args, cleanup, **kwargs):
        super().__init__(*args, **kwargs)
        self._cleanup = cleanup

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._cleanup()


async def query_copilot(
    request: CopilotQueryRequest,
    *,
    history: list | None = None,
    memory_summary: str | None = None,
    runtime=None,
    snapshot=None,
    request_id=None,
    readiness_loader=None,
    progress_queue=None,
) -> CopilotQueryResponse:
    request_id = request_id or uuid4().hex
    started = time.perf_counter()
    try:
        runtime = runtime or RuntimeBudget.create(get_settings())
        result = await asyncio.wait_for(
            copilot_agent.ainvoke(
                {
                    "query": request.query,
                    "target_date": request.target_date,
                    "customer_context": request.customer_context or "",
                    "memory_summary": memory_summary,
                    "history": history or [],
                    "domain": request.domain,
                    "runtime": runtime,
                    "snapshot": snapshot,
                    "readiness_loader": readiness_loader,
                    "request_id": request_id,
                    "progress_queue": progress_queue,
                },
                config={"recursion_limit": 32, **graph_config()},
            ),
            timeout=runtime.timeout(get_settings().copilot_request_timeout_seconds),
        )
        final = CopilotResponse.model_validate(result["final_response"])
        trace = runtime.events
        llm_events = [event for event in trace if event.get("llm")]
        annotate(
            outcome=final.status,
            reason_code=final.reason_code,
            workflow_version="9-evidence-review",
            generation_attempt=result.get("generation_count"),
            corrective_round=result.get("corrective_retrieval_count"),
            provider_retry=runtime.provider_retries,
            tool_calls=result.get("tool_calls"),
            llm_attempts=len(llm_events),
            input_tokens=sum(e["input_tokens"] for e in llm_events)
            if llm_events and all(e.get("input_tokens") is not None for e in llm_events)
            else None,
            output_tokens=sum(e["output_tokens"] for e in llm_events)
            if llm_events and all(e.get("output_tokens") is not None for e in llm_events)
            else None,
        )
        logger.info(
            "Copilot request_id=%s status=%s llm_attempts=%s tools=%s elapsed=%.3f usage=%s",
            request_id,
            final.status,
            len(llm_events),
            result.get("tool_calls"),
            time.perf_counter() - started,
            [
                {key: event.get(key) for key in ("node", "input_tokens", "output_tokens")}
                for event in trace
                if event.get("llm")
            ],
        )
        return CopilotQueryResponse(**{**final.model_dump(), "request_id": request_id})
    except (CopilotDependencyError, BudgetExhaustedError, IndexNotReadyError, TimeoutError) as exc:
        annotate(error_type=type(exc).__name__)
        failures = [event for event in reversed(runtime.events) if event.get("error_type")]
        failure = next((event for event in failures if event.get("llm")), failures[0] if failures else {})
        cause = exc.__cause__ or exc
        provider_status = failure.get("provider_status") or getattr(cause, "status_code", None)
        logger.error(
            "Copilot dependency failed",
            extra={
                "telemetry": {
                    "event": "copilot_dependency_failure",
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                    "cause_type": type(cause).__name__,
                    "failure_stage": failure.get("failure_stage") or failure.get("node") or "readiness",
                    "failure_kind": failure.get("failure_kind"),
                    "provider_status": provider_status,
                    "provider_error_kind": failure.get("provider_error_kind"),
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }
            },
        )
        detail = (
            "Hạn mức dịch vụ AI không đủ để tạo câu trả lời. Vui lòng liên hệ quản trị viên."
            if provider_status == 402
            else "Dịch vụ tra cứu tạm thời không khả dụng. Vui lòng thử lại."
        )
        raise HTTPException(status_code=503, detail=detail) from exc
    except Exception as exc:
        logger.error(
            "Copilot request failed",
            extra={
                "telemetry": {
                    "event": "copilot_internal_failure",
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                    "failure_stage": runtime.events[-1].get("node")
                    if getattr(runtime, "events", None)
                    else "initialization",
                }
            },
        )
        raise HTTPException(status_code=500, detail="Không thể xử lý câu hỏi lúc này.") from None


async def query_owned_session(
    payload,
    request,
    user,
    runtime,
    background_tasks: BackgroundTasks | None = None,
    progress_queue: asyncio.Queue | None = None,
    customer_conversation_id: str | None = None,
    advisor_lookup: bool = False,
) -> tuple[CopilotQueryResponse, bool]:
    repository = request.app.state.copilot_sessions
    history, revision, context = [], None, payload.customer_context or ""
    session_id = payload.session_id or uuid4().hex
    from_cache = False
    scope_kwargs = {}
    if advisor_lookup:
        session_id = await bounded_io(
            lambda: repository.advisor_session(user.user_id, create=True),
            runtime.timeout(20),
        )
        context = ""
        scope_kwargs = {"advisor": True}
        payload = payload.model_copy(
            update={
                "session_id": session_id,
                "customer_context": "",
                "domain": "all",
                "target_date": None,
            }
        )
        annotate(source_surface="advisor_lookup", session_id=session_id)
    elif customer_conversation_id:
        try:
            context = await bounded_io(
                lambda: build_customer_context(
                    request.app.state.sales_copilot_repository,
                    customer_conversation_id,
                    user.user_id,
                ),
                runtime.timeout(20),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại.") from exc
        session_id = await bounded_io(
            lambda: repository.customer_session(user.user_id, customer_conversation_id, create=True),
            runtime.timeout(20),
        )
        scope_kwargs = {"customer_conversation_id": customer_conversation_id}
        payload = payload.model_copy(
            update={
                "session_id": session_id,
                "customer_context": context,
                "domain": "all",
                "target_date": None,
            }
        )
        annotate(source_surface="customer_lookup", conversation_id=customer_conversation_id, session_id=session_id)
    else:
        annotate(source_surface="standalone_lookup", session_id=session_id)

    stored_mem_summary = None
    if payload.session_id:
        try:
            with span("session.load", backend="session"):
                stored = await bounded_io(
                    lambda: repository.load(session_id, user.user_id, **scope_kwargs),
                    runtime.timeout(20),
                )
        except CopilotSessionNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên Copilot.") from exc
        history, revision = stored["history"], stored["revision"]
        context = stored["customer_context"] if payload.customer_context is None else payload.customer_context
        stored_mem_summary = stored.get("memory_summary")

    # 1. Exact Cache check for standalone questions without active session
    is_standalone = not customer_conversation_id and not payload.session_id and not (context and context.strip())
    result = None
    if is_standalone:
        cached = await semantic_cache.get(
            query=payload.query,
            domain=payload.domain or "all",
            target_date=payload.target_date,
            customer_context="",
            session_id=None,
            history=[],
            memory_summary=None,
            readiness_loader=request.app.state.copilot_readiness,
        )
        if cached:
            cached_resp = CopilotResponse.model_validate(cached)
            request_id = getattr(request.state, "request_id", None) or uuid4().hex
            result = CopilotQueryResponse(
                **{**cached_resp.model_dump(), "request_id": request_id, "session_id": session_id}
            )
            from_cache = True

    if result is None:
        formatted_summary = format_summary_for_context(stored_mem_summary) if stored_mem_summary else None
        annotate(query_characters=len(payload.query), history_count=len(history))
        async def invoke(private_payload, private_history, private_summary):
            return await query_copilot(
                private_payload, history=private_history, memory_summary=private_summary,
                runtime=runtime, readiness_loader=request.app.state.copilot_readiness,
                request_id=getattr(request.state, "request_id", None), progress_queue=progress_queue)
        if customer_conversation_id:
            from src.integrations.customer_intelligence_store import IntelligenceStore
            from src.observability import private_customer_context
            from src.services.customer_pii import CustomerPII
            sales_repo = request.app.state.sales_copilot_repository
            customer_id = sales_repo.owned_conversation(customer_conversation_id, user.user_id)["customer_id"]
            store = IntelligenceStore(sales_repo)
            head = store.head(customer_id)
            try:
                pii = CustomerPII(head["pii_mapping"], customer_id=customer_id)
                context = pii.mask(context)
                private_history = [{**m, "content": pii.mask(m["content"])} for m in history]
                with private_customer_context():
                    result = await invoke(payload.model_copy(update={"query": pii.mask(payload.query), "customer_context": context}),
                                          private_history, pii.mask(formatted_summary) if formatted_summary else None)
                try:
                    store.save_mapping(customer_id, pii, head)
                except (SQLAlchemyError, ValueError):
                    raise HTTPException(409, "Dữ liệu riêng tư đã thay đổi. Vui lòng gửi lại câu hỏi.") from None
                # Persist masked knowledge dialogue; later turns must not reintroduce
                # restored identifiers into model context without their original label.
                history = private_history
                payload = payload.model_copy(update={"query": pii.mask(payload.query)})
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(503, "Tra cứu riêng tư tạm thời không khả dụng.") from None
        else:
            result = await invoke(payload.model_copy(update={"customer_context": context}), history, formatted_summary)

    if result.reason_code == "input_blocked":
        return result.model_copy(update={"session_id": payload.session_id}), from_cache

    result = result.model_copy(update={"session_id": session_id})

    dialogue = [
        *history,
        {"role": "user", "content": payload.query},
        {"role": "assistant", "content": result.answer[:4000]},
    ]
    with span("session.save", backend="session"):
        try:
            await bounded_io(
                lambda: repository.save(
                    session_id,
                    user.user_id,
                    dialogue,
                    context,
                    revision,
                    rich_turn={
                        "request_id": result.request_id or getattr(request.state, "request_id", None) or uuid4().hex,
                        "user_query": payload.query,
                        "response_data": result.model_dump(),
                    },
                    **scope_kwargs,
                ),
                runtime.timeout(20),
            )
        except CopilotSessionConflictError as exc:
            raise HTTPException(status_code=409, detail="Phiên đã thay đổi. Vui lòng gửi lại câu hỏi.") from exc

    # Save to exact cache if standalone, verified answered, and not already from cache
    decision_degraded = any(e.get("decision") and e.get("route") == "unscored" for e in runtime.events)
    if is_standalone and not from_cache and result.status == "answered" and result.citations and not decision_degraded:
        try:
            semantic_cache.put(
                query=payload.query,
                response_data=result.model_dump(),
                domain=payload.domain or "all",
                target_date=payload.target_date,
                customer_context="",
                session_id=None,
                history=[],
                memory_summary=None,
                readiness_loader=request.app.state.copilot_readiness,
            )
        except Exception as cache_err:
            logger.debug("Failed to put in exact cache: %s", cache_err)

    # Check background summarization
    if background_tasks and not customer_conversation_id:
        try:

            def schedule_summary():
                total_msgs = repository.get_conversation_last_seq(session_id) or len(dialogue)
                maybe_trigger_background_summarization(
                    session_id=session_id,
                    repository=repository,
                    background_tasks=background_tasks,
                    current_message_count=total_msgs,
                )

            await bounded_io(schedule_summary, runtime.timeout(20))
        except Exception as bg_err:
            logger.debug("Failed to trigger background summarization: %s", type(bg_err).__name__)

    return result.model_copy(update={"session_id": session_id}), from_cache


async def customer_lookup_history(request, user, conversation_id, *, before_seq=None, limit=20):
    runtime = RuntimeBudget.create(get_settings())
    try:
        await bounded_io(
            lambda: authorize_customer(request.app.state.sales_copilot_repository, conversation_id, user.user_id),
            runtime.timeout(20),
        )
        return await bounded_io(
            lambda: request.app.state.copilot_sessions.customer_history(
                user.user_id,
                conversation_id,
                before_seq=before_seq,
                limit=limit,
            ),
            runtime.timeout(20),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại.") from exc
    except (SQLAlchemyError, OSError, TimeoutError, BudgetExhaustedError, CopilotDependencyError) as exc:
        raise HTTPException(status_code=503, detail="Không thể tải lịch sử tra cứu lúc này.") from exc


async def advisor_lookup_history(request, user, *, before_seq=None, limit=20):
    runtime = RuntimeBudget.create(get_settings())
    try:
        return await bounded_io(
            lambda: request.app.state.copilot_sessions.advisor_history(
                user.user_id,
                before_seq=before_seq,
                limit=limit,
            ),
            runtime.timeout(20),
        )
    except (SQLAlchemyError, OSError, TimeoutError, BudgetExhaustedError, CopilotDependencyError) as exc:
        annotate(error_type=type(exc).__name__, failure_stage="advisor_history")
        raise HTTPException(status_code=503, detail="Không thể tải lịch sử tra cứu lúc này.") from exc


def _response_data(result, payload, customer_conversation_id):
    data = result.model_dump()
    if customer_conversation_id:
        data.update(query=payload.query, answered_at=datetime.now(UTC).isoformat())
        data["citations"] = [{**source, "content": source.get("excerpt") or ""} for source in data["citations"]]
    return data


async def run_copilot_request(
    payload,
    request,
    user,
    *,
    background_tasks=None,
    stream=False,
    customer_conversation_id=None,
    advisor_lookup=False,
):
    """One admission/deadline and one graph execution for either HTTP entry point."""
    runtime = RuntimeBudget.create(get_settings())
    admission = request.app.state.copilot_admission
    request_id = getattr(request.state, "request_id", None) or uuid4().hex
    request.state.request_id = request_id
    if advisor_lookup:
        capture_knowledge_input(payload.query)
    try:
        with span("admission"):
            admission.acquire(user.user_id)
    except AdmissionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail="Đang có nhiều yêu cầu. Vui lòng thử lại sau.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc

    released = False

    def release():
        nonlocal released
        if not released:
            released = True
            admission.release(user.user_id)

    try:
        if customer_conversation_id:
            try:
                await bounded_io(
                    lambda: authorize_customer(
                        request.app.state.sales_copilot_repository,
                        customer_conversation_id,
                        user.user_id,
                    ),
                    runtime.timeout(20),
                )
            except LookupError as exc:
                raise HTTPException(status_code=404, detail="Không tìm thấy cuộc hội thoại.") from exc
    except (SQLAlchemyError, OSError, TimeoutError, BudgetExhaustedError, CopilotDependencyError) as exc:
        release()
        raise HTTPException(
            status_code=503, detail="Dịch vụ tra cứu tạm thời không khả dụng. Vui lòng thử lại."
        ) from exc
    except BaseException:
        release()
        raise

    async def execute(queue=None):
        try:
            result = await asyncio.wait_for(
                query_owned_session(
                    payload,
                    request,
                    user,
                    runtime,
                    background_tasks=background_tasks,
                    progress_queue=queue,
                    customer_conversation_id=customer_conversation_id,
                    advisor_lookup=advisor_lookup,
                ),
                timeout=runtime.remaining(),
            )
            if advisor_lookup:
                capture_knowledge_output(result[0].model_dump())
            return result
        except (
            CopilotDependencyError,
            BudgetExhaustedError,
            IndexNotReadyError,
            TimeoutError,
            SQLAlchemyError,
            OSError,
        ) as exc:
            annotate(error_type=type(exc).__name__)
            raise HTTPException(
                status_code=503, detail="Dịch vụ tra cứu tạm thời không khả dụng. Vui lòng thử lại."
            ) from exc

    if not stream:
        try:
            result, _ = await execute()
            return _response_data(result, payload, customer_conversation_id) if customer_conversation_id else result
        finally:
            release()

    def event(name, data):
        return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    worker = None

    async def cleanup():
        if worker is not None:
            worker.cancel()
        release()
        if worker is not None:
            try:
                await worker
            except (asyncio.CancelledError, Exception):
                pass

    async def events():
        nonlocal worker
        queue = asyncio.Queue(maxsize=32)
        worker = asyncio.create_task(execute(queue))
        try:
            yield event("status", {"step": "analyzing", "text": "Đang phân tích câu hỏi và ngữ cảnh…"})
            while not worker.done():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield event("status", item)
                except TimeoutError:
                    pass
            while not queue.empty():
                yield event("status", queue.get_nowait())
            result, from_cache = await worker
            if from_cache:
                yield event("status", {"step": "cached", "text": "Phản hồi từ bộ nhớ đệm xác thực"})
            # These deltas contain only the checked AND persisted final answer, never an LLM draft.
            for offset in range(0, len(result.answer), 256):
                yield event("delta", {"text": result.answer[offset : offset + 256]})
            yield event("final", _response_data(result, payload, customer_conversation_id))
            if result.product_insights:
                yield event(
                    "insights",
                    {
                        "product_insights": [item.model_dump() for item in result.product_insights],
                        "request_id": result.request_id,
                        "session_id": result.session_id,
                    },
                )
            yield event("done", {})
        except Exception as exc:
            cause = exc.__cause__ or exc
            annotate(error_type=type(cause).__name__)
            detail = str(exc.detail) if isinstance(exc, HTTPException) else "Không thể xử lý câu hỏi lúc này."
            yield event("error", {"error": detail, "detail": detail, "status": "error", "request_id": request_id})
        finally:
            await cleanup()

    return CopilotStreamingResponse(
        events(),
        media_type="text/event-stream",
        background=background_tasks,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        cleanup=cleanup,
    )
