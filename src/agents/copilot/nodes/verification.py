"""Check typed claims and requirements; publish only a verified answer snapshot."""

from src.agents.copilot import prompts
from src.agents.copilot.context import evidence_fingerprints
from src.agents.copilot.errors import CopilotModelOutputError
from src.agents.copilot.model_io import _invoke_json
from src.agents.copilot.nodes._shared import _runtime, can_regenerate, observed, schedule_corrective
from src.agents.copilot.state import StructuredGroundingReview, VerifiedAnswerSnapshot
from src.agents.copilot.tools import build_evidence_context
from src.agents.copilot.validation.structured import (
    render_answer,
    validate_generated_answer,
    validate_grounding_review,
    verified_answer,
)
from src.config import get_settings
from src.observability import annotate


@observed
async def check_grounding(state):
    draft, generated = state.get("draft_answer"), state.get("generated_answer")
    review = None
    try:
        if not draft or generated is None:
            raise ValueError("missing structured draft")
        validate_generated_answer(generated, state)
        if render_answer(generated) != draft:
            raise ValueError("draft differs from structured claims")
    except ValueError:
        return {
            "grounding_review": None,
            "feedback": (state.get("feedback") if not draft else None)
            or "Câu trả lời phải khớp các phát biểu có cấu trúc và nguồn đã chọn; vui lòng sinh lại.",
            "fallback_reason": "verification_failed",
            "route": "generate_answer"
            if not draft and can_regenerate(state)
            else "finalize_response"
            if state.get("verified_snapshot")
            else "fallback_response",
        }
    try:
        last_call = next((e for e in reversed(_runtime(state).events) if e.get("llm")), {})
        review, _ = await _invoke_json(
            state,
            prompts.CHECK_PROMPT,
            {
                "query": state["query"],
                "requirements": [r.model_dump() for r in state.get("requirements", [])],
                "sources": state.get("answer_context", ""),
                "history": state.get("history", [])[-6:],
                "generated_answer": generated.model_dump(),
                "source_ids": [h["citation_id"] for h in state.get("selected_evidence", [])],
                "lookup_date": state["resolved_date"],
                "customer_context": state.get("customer_context", ""),
                "memory_summary": state.get("memory_summary") or "",
                "validation_feedback": state.get("feedback", "")
                if last_call.get("node") == "check_grounding" and last_call.get("failure_kind") == "output_contract"
                else "",
            },
            StructuredGroundingReview,
            node="check_grounding",
            validator=lambda review: validate_grounding_review(review, state),
        )
        publishable, verdict = verified_answer(review, state)
    except CopilotModelOutputError:
        runtime, settings = _runtime(state), get_settings()
        failures = [
            e for e in runtime.events
            if e.get("llm") and e.get("node") == "check_grounding" and e.get("failure_kind") == "output_contract"
        ]
        # A broken review does not establish that a valid draft needs rewriting.
        # Retry this review once, inside the same request-wide attempt budget.
        retry = (
            len(failures) == 1
            and runtime.attempts < runtime.max_attempts
            and runtime.remaining() > settings.copilot_check_timeout_seconds + runtime.reserve_seconds
        )
        feedback = "Kiểm tra lại cùng generated_answer: đánh giá mỗi claim và requirement đúng một lần; chỉ dẫn claim supported có liên kết đúng requirement_id. Không tự thêm liên kết."
        if failures and failures[-1].get("validation_code"):
            feedback = "Lỗi hợp đồng trước: " + failures[-1]["validation_code"] + ". " + feedback
        if failures and failures[-1].get("validation_code") == "json_invalid":
            feedback = "Lần trước JSON không hợp lệ. Chỉ xuất MỘT object theo schema, không nối hai object hoặc thêm token/văn bản sau dấu đóng cuối. " + feedback
        elif failures and failures[-1].get("validation_code") == "evidence_quote_not_found_in_cited_source":
            feedback = "Quote chứng cứ lần trước không có nguyên văn trong citation. Trích một đoạn liên tục trong content HOẶC title/section/context_prefix; không ghép các trường, không thêm 'section:' vào quote. Dùng header cùng citation để xác định phạm vi của dòng giá trị. " + feedback
        return {
            "grounding_review": None,
            "feedback": feedback,
            "route": "check_grounding"
            if retry
            else ("finalize_response" if state.get("verified_snapshot") else "fallback_response"),
            **({"fallback_reason": "verification_failed"} if not retry else {}),
        }
    result = {"grounding_review": review, "unsupported_claims": verdict.unsupported_claims}
    annotate(
        grounded=verdict.grounded,
        unsupported_count=len(verdict.unsupported_claims),
        supported_count=len(verdict.supported_claim_indices),
        generation_attempt=state.get("generation_count", 0),
    )
    req_map = {r.requirement_id: r for r in state.get("requirements", [])}
    missing_fact_ids = [rid for rid in verdict.missing_requirement_ids if req_map[rid].kind == "fact"]

    if publishable is not None:
        _, citations = build_evidence_context(state.get("selected_evidence", []))
        used = {cid for claim in publishable.claims for cid in claim.citation_ids}
        diagnostic_ids = {cid for v in verdict.requirement_diagnostics for cid in v.evidence_citation_ids}
        citations = [c.model_copy(deep=True) for c in citations if c.citation_id in used | diagnostic_ids]
        # A supported limitation alone is not a factual answer. Keep searching or
        # abstain without replacing an earlier usable snapshot with an empty one.
        if used or state.get("answer_kind") == "coaching":
            status = "partial" if verdict.missing_requirement_ids else "answered"
            candidate_snapshot = VerifiedAnswerSnapshot(
                answer=render_answer(publishable),
                resolved_date=state["resolved_date"],
                citations=citations,
                answered_requirement_ids=verdict.answered_requirement_ids,
                missing_requirement_ids=verdict.missing_requirement_ids,
                missing_information=verdict.missing_information,
                status=status,
                reason_code="insufficient_evidence" if status == "partial" else None,
                answer_kind=state.get("answer_kind", "factual"),
                suggested_message=publishable.suggested_message,
                suggested_next_question=publishable.suggested_next_question,
                requirement_diagnostics=verdict.requirement_diagnostics,
                evidence_fingerprints=evidence_fingerprints(
                    state.get("selected_evidence", []), state.get("jev_conflict_chunk_ids", [])
                ),
            )
            previous = state.get("verified_snapshot")
            if previous is None or set(previous.answered_requirement_ids) <= set(candidate_snapshot.answered_requirement_ids):
                result["verified_snapshot"] = candidate_snapshot
            if not missing_fact_ids:
                return {**result, "feedback": "", "unsupported_claims": [], "route": "finalize_response"}

    sufficient_ids = {
        v.requirement_id for v in verdict.requirement_diagnostics
        if v.evidence_status == "sufficient" and v.requirement_id in missing_fact_ids
    }
    actionable_gaps = [
        rid for rid in missing_fact_ids
        if next(v for v in verdict.requirement_diagnostics if v.requirement_id == rid).blocker
        not in {"missing_input", "external_data", "source_conflict"}
    ]
    # Source sufficiency is separate from answer coverage. Repair omissions using
    # the current context before spending another search or selection round.
    if sufficient_ids and can_regenerate(state):
        return {
            **result,
            "feedback": ("Nguồn trong context đã đủ cho " + ", ".join(sorted(sufficient_ids))
                         + "; bổ sung/sửa đúng các mục này và giữ các phần đã xác minh. " + verdict.feedback)[:500],
            "recovery_requirement_ids": actionable_gaps,
            "route": "generate_answer",
        }
    if actionable_gaps and verdict.recovery != "regenerate":
        search_ids = [rid for rid in actionable_gaps if rid not in sufficient_ids]
        corrective = schedule_corrective(
            {**state, "recovery_requirement_ids": search_ids},
            feedback=verdict.feedback or "Tìm nguồn bổ sung cho dữ kiện còn thiếu.",
        ) if search_ids else None
        if corrective:
            return {**result, "recovery_requirement_ids": search_ids, **corrective}
    if (not verdict.grounded or actionable_gaps and verdict.recovery == "regenerate") and can_regenerate(state):
        return {
            **result,
            "feedback": verdict.feedback or "Sửa phát biểu thiếu nguồn hoặc điều kiện áp dụng.",
            "unsupported_claims": verdict.unsupported_claims,
            "recovery_requirement_ids": missing_fact_ids,
            "route": "generate_answer",
        }
    if result.get("verified_snapshot") or state.get("verified_snapshot"):
        return {**result, "route": "finalize_response"}
    return {
        **result,
        "fallback_reason": "insufficient_evidence" if verdict.grounded else "verification_failed",
        "route": "fallback_response",
    }
