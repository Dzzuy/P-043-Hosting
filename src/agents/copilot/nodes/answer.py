"""Generate structured claims, render Markdown in code, and publish verified output."""

import re

from src.agents.copilot import prompts
from src.agents.copilot.errors import CopilotModelOutputError
from src.agents.copilot.model_io import _invoke_json
from src.agents.copilot.nodes._shared import observed
from src.agents.copilot.runtime import CopilotDependencyError
from src.agents.copilot.state import FALLBACK_ANSWERS, CopilotResponse, GeneratedAnswer
from src.agents.copilot.validation.structured import (
    bind_citation_dependencies,
    render_answer,
    validate_generated_answer,
)
from src.observability import annotate


def _repair_question(snapshot, requirements):
    """Ask only a repairable gap, keeping its scope and dependency context intact."""
    reqs = {r.requirement_id: r for r in requirements}
    for diagnostic in snapshot.requirement_diagnostics:
        if diagnostic.requirement_id not in snapshot.missing_requirement_ids or diagnostic.evidence_status != "sufficient":
            continue
        requirement = reqs.get(diagnostic.requirement_id)
        if requirement is None:
            continue
        ids = {requirement.requirement_id}
        pending = [requirement.requirement_id]
        while pending:
            for dependency in reqs[pending.pop()].depends_on:
                if dependency in reqs and dependency not in ids:
                    ids.add(dependency)
                    pending.append(dependency)
        parts = []
        for rid, req in reqs.items():
            if rid in ids:
                scope = [req.description, req.product_model, req.variant, *req.qualifiers]
                parts.append("; ".join(dict.fromkeys(value for value in scope if value)))
        question = f"Theo tài liệu áp dụng ngày {snapshot.resolved_date}, làm rõ: " + "; ".join(parts) + "?"
        # Truncating a qualifier or dependency can change the question's meaning.
        if len(question) <= 500:
            return question
    return None


@observed
async def generate_answer(state):
    count = state.get("generation_count", 0)
    if count >= 2:
        has_snapshot = bool(state.get("verified_snapshot"))
        return {
            "route": "finalize_response" if has_snapshot else "fallback_response",
            "fallback_reason": state.get("fallback_reason", "verification_failed"),
        }
    annotate(generation_attempt=count + 1)

    def validate(answer):
        bind_citation_dependencies(answer, state)
        validate_generated_answer(answer, state)

    try:
        generated, _ = await _invoke_json(
            state,
            prompts.GENERATE_PROMPT,
            {
                "query": state["query"],
                "history": state.get("history", [])[-6:],
                "sources": state.get("answer_context", "") or "",
                "source_ids": [h["citation_id"] for h in state.get("selected_evidence", [])],
                "requirements": [r.model_dump() for r in state.get("requirements", [])],
                "lookup_date": state["resolved_date"],
                "customer_context": state.get("customer_context", ""),
                "memory_summary": state.get("memory_summary") or "",
                "feedback": state.get("feedback", ""),
                "unsupported_claims": state.get("unsupported_claims", []),
                "previous_draft": state.get("draft_answer"),
            },
            GeneratedAnswer,
            node="generate_answer",
            validator=validate,
        )
        result = {
            "grounding_review": None,
            "generated_answer": generated,
            "draft_answer": render_answer(generated),
        }
    except CopilotModelOutputError:
        result = {
            "grounding_review": None,
            "generated_answer": None,
            "draft_answer": None,
            "feedback": "Lần sinh trước không đạt hợp đồng output. Xuất GeneratedAnswer đúng schema, fact có citation đúng nguồn; limitation/advice không dùng để giấu fact. Giữ phần có nguồn và nêu giới hạn phần chưa xác minh.",
        }
    return {**result, "generation_count": count + 1, "route": "check_grounding"}


@observed
async def finalize_response(state):
    snapshot = state.get("verified_snapshot")
    if snapshot is not None:
        # Check snapshot binding with request
        if (
            snapshot.resolved_date
            and state.get("resolved_date")
            and snapshot.resolved_date != str(state.get("resolved_date"))
        ):
            return {
                "route": "fallback_response",
                "fallback_reason": "verification_failed",
            }
        answer = snapshot.answer
        citations = [c.model_copy(deep=True) for c in snapshot.citations]
        status = snapshot.status
        missing = list(snapshot.missing_information)
        fallback_reason = state.get("fallback_reason")
        reason_code = (fallback_reason if fallback_reason else snapshot.reason_code) if status != "answered" else None

        from src.agents.copilot.insights import build_complementary_insights

        product_insights = build_complementary_insights(state, answer, existing_citations=citations)

        # Snapshot strictly owns all published suggestions; never leak from later drafts/state
        suggested_message = snapshot.suggested_message
        suggested_next_question = snapshot.suggested_next_question
        diagnostics = snapshot.requirement_diagnostics
        if status == "partial":
            pending = [d for d in diagnostics if d.requirement_id in snapshot.missing_requirement_ids]
            repairable = [d for d in pending if d.evidence_status == "sufficient"]
            if repairable:
                suggested_next_question = _repair_question(snapshot, state.get("requirements", []))
            elif pending:
                # Splitting cannot repair missing sources, unavailable inputs or
                # external systems. Do not imply that another wording will do so.
                suggested_next_question = None
        talking_points = [answer] if len(answer) <= 500 and status == "answered" else []

        ans_kind = snapshot.answer_kind
        final = CopilotResponse(
            status=status,
            answer=answer,
            citations=citations,
            product_insights=product_insights,
            missing_information=missing if status == "partial" else [],
            talking_points=talking_points,
            suggested_message=suggested_message,
            suggested_next_question=suggested_next_question,
            sales_actions=[],
            request_id=state.get("request_id"),
            reason_code=reason_code,
            answer_kind=ans_kind,
            requirement_diagnostics=[d.model_copy(deep=True) for d in diagnostics],
        )
        return {"final_response": final, "route": "end"}

    return {"route": "fallback_response", "fallback_reason": "verification_failed"}


@observed
async def fallback_response(state):
    reason = state.get("fallback_reason", "insufficient_evidence")
    question = state.get("clarification_question")
    if question and reason != "input_blocked":
        if (
            not question.endswith("?")
            or "\n" in question
            or len(question) > 500
            or re.search(r"\[C\d|cam kết|miễn phí", question, re.I)
        ):
            question = "Bạn có thể bổ sung mẫu xe, thời điểm hoặc nhu cầu khách cần tư vấn không?"
        final = CopilotResponse(
            status="needs_clarification",
            answer=question,
            clarification_question=question,
            request_id=state.get("request_id"),
        )
    else:
        if state.get("retrieval_errors") and reason not in {"input_blocked", "out_of_scope"}:
            raise CopilotDependencyError("retrieval degraded without a verified answer")
        final = CopilotResponse(
            status="abstained",
            answer=FALLBACK_ANSWERS.get(reason, FALLBACK_ANSWERS["insufficient_evidence"]),
            reason_code=reason,
            missing_information=[r.description for r in state.get("requirements", [])],
            request_id=state.get("request_id"),
        )
    return {"final_response": final, "route": "end"}
