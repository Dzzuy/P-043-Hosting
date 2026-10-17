"""Common budgets, profiles and request-local observation."""

import time
from functools import wraps
from types import SimpleNamespace

from src.agents.copilot.runtime import BudgetExhaustedError, RuntimeBudget
from src.config import get_settings
from src.knowledge.validity import is_document_retrievable, parse_target_date, today_in_vietnam
from src.observability import annotate, span


def _runtime(state):
    if not state.get("runtime"):
        state["runtime"] = RuntimeBudget.create(get_settings())
    return state["runtime"]


def _profile(state):
    name = state.get("profile_name", "simple")
    settings = get_settings()
    return SimpleNamespace(
        **{
            key: getattr(settings, f"copilot_{name}_{key}")
            for key in ("dense_top_k", "bm25_top_k", "candidate_pool", "evidence_blocks", "context_characters")
        }
    )


NODE_STATUS_MESSAGES: dict[str, tuple[str, str]] = {
    "analyze_and_route": ("analyzing", "Đang phân tích câu hỏi & đối chiếu ngữ cảnh..."),
    "plan_queries": ("planning", "Đang lập kế hoạch tra cứu tài liệu..."),
    "retrieve_documents": ("searching", "Đang tìm kiếm thông tin liên quan..."),
    "select_evidence": ("synthesizing", "Đang tổng hợp dữ liệu đối chiếu..."),
    "build_context": ("synthesizing", "Đang xây dựng ngữ cảnh trích dẫn..."),
    "generate_answer": ("generating", "Đang soạn thảo câu trả lời..."),
    "check_grounding": ("verifying", "Đang thẩm định chống suy diễn với tài liệu..."),
    "finalize_response": ("finalizing", "Đang hoàn thiện phản hồi..."),
    "fallback_response": ("fallback", "Đang xử lý phản hồi an toàn..."),
}


def observed(node):
    @wraps(node)
    async def run(state):
        runtime = _runtime(state)
        progress_queue = state.get("progress_queue")
        if progress_queue is not None and node.__name__ in NODE_STATUS_MESSAGES:
            step, text = NODE_STATUS_MESSAGES[node.__name__]
            try:
                progress_queue.put_nowait({"step": step, "text": text})
            except Exception:
                pass
        started, error = time.monotonic(), None
        try:
            with span(node.__name__, export=False, node=node.__name__):
                result = await node(state)
        except BudgetExhaustedError:
            self_check = state.get("self_check")
            is_grounded = bool(self_check and getattr(self_check, "grounded", False))
            has_snapshot = bool(state.get("verified_snapshot") or (is_grounded and state.get("draft_answer")))
            result = {
                "route": "finalize_response" if has_snapshot else "fallback_response",
                "fallback_reason": "budget_exhausted",
            }
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            runtime.events.append(
                {
                    "node": node.__name__,
                    "llm": False,
                    "elapsed_seconds": time.monotonic() - started,
                    **({"error_type": error} if error else {}),
                }
            )
        return {**result, "runtime": runtime, "trace": list(runtime.events)}

    return run


def _requirements(state):
    return {r.requirement_id: r for r in state.get("requirements", [])}


def _lookup_date(state):
    return parse_target_date(state.get("target_date") or state.get("resolved_date")) or today_in_vietnam()


def _valid_evidence_date(hit, state):
    try:
        if state.get("target_date") is None and hit["status"] != "active":
            return False
        return is_document_retrievable(
            SimpleNamespace(
                status=hit["status"], effective_date=hit["effective_from"], expiry_date=hit.get("effective_to")
            ),
            _lookup_date(state),
        )
    except (ValueError, TypeError, KeyError):
        return False


def _valid_evidence_scope(hit, state):
    wanted = set(getattr(state.get("analysis"), "product_models", []) or [])
    return not wanted or hit.get("product_model") in wanted | {"ALL"}


def can_regenerate(state):
    settings, runtime = get_settings(), _runtime(state)
    return (
        state.get("generation_count", 0) < 2
        and runtime.remaining() >= settings.copilot_regenerate_min_seconds
        and runtime.attempts + 2 <= runtime.max_attempts
    )


def schedule_corrective(state, *, anchors=None, feedback=""):
    settings, runtime = get_settings(), _runtime(state)
    if (
        state.get("corrective_retrieval_count", 0) >= 1
        or state.get("generation_count", 0) >= 2
        or runtime.remaining() < settings.copilot_corrective_min_seconds
        or runtime.attempts + (2 if anchors else 3) > runtime.max_attempts
        or (
            not anchors
            and (
                state.get("tool_calls", 0) >= settings.copilot_max_search_calls
                or state.get("retrieval_rounds", 0) >= settings.copilot_max_retrieval_rounds
            )
        )
    ):
        return None
    annotate(corrective_round=1)
    return {
        "corrective_retrieval_count": 1,
        "profile_name": "corrective",
        "feedback": feedback,
        "read_anchor_ids": anchors or [],
        "retrieval_mode": "read_context" if anchors else "search",
        "route": "retrieve_documents" if anchors else "plan_queries",
    }
