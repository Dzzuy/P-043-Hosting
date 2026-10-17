"""Generate answer in Markdown, optionally regenerate once; render verified output."""

import re

from src.agents.copilot import prompts
from src.agents.copilot.errors import CopilotModelOutputError
from src.agents.copilot.model_io import _invoke_text
from src.agents.copilot.nodes._shared import observed
from src.agents.copilot.runtime import CopilotDependencyError
from src.agents.copilot.state import FALLBACK_ANSWERS, CopilotResponse
from src.agents.copilot.tools import build_evidence_context
from src.observability import annotate


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
    try:
        draft, _ = await _invoke_text(
            state,
            prompts.GENERATE_PROMPT,
            {
                "query": state["query"],
                "history": state.get("history", [])[-6:],
                "sources": state.get("answer_context", "") or "",
                "requirements": [r.model_dump() for r in state.get("requirements", [])],
                "lookup_date": state["resolved_date"],
                "customer_context": state.get("customer_context", ""),
                "memory_summary": state.get("memory_summary") or "",
                "feedback": state.get("feedback", ""),
                "unsupported_claims": state.get("unsupported_claims", []),
                "previous_draft": state.get("draft_answer"),
            },
            node="generate_answer",
        )
        if draft and draft.strip().startswith("{"):
            try:
                import json

                data = json.loads(draft.strip())
                if isinstance(data, dict):
                    if "claims" in data and isinstance(data["claims"], list):
                        lines = [
                            f"{c.get('text', '')} {' '.join(f'[{cid}]' for cid in c.get('citation_ids', []))}".strip()
                            for c in data["claims"]
                            if isinstance(c, dict)
                        ]
                        draft = "\n".join(lines)
                    else:
                        draft = None
            except Exception:
                draft = None
        result = {
            "self_check": None,
            "draft_answer": draft,
        }
    except CopilotModelOutputError:
        result = {
            "self_check": None,
            "draft_answer": None,
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
        suggested_message = getattr(snapshot, "suggested_message", None)
        suggested_next_question = getattr(snapshot, "suggested_next_question", None)
        talking_points = (
            [answer] if len(answer) <= 500 and (status == "answered" or state.get("talking_points")) else []
        )

        ans_kind = getattr(snapshot, "answer_kind", state.get("answer_kind", "factual"))
        final = CopilotResponse(
            status=status,
            answer=answer,
            citations=citations,
            product_insights=product_insights,
            missing_information=missing[:6] if status == "partial" else [],
            talking_points=talking_points,
            suggested_message=suggested_message,
            suggested_next_question=suggested_next_question,
            sales_actions=[],
            request_id=state.get("request_id"),
            reason_code=reason_code,
            answer_kind=ans_kind,
        )
        return {"final_response": final, "route": "end"}

    # Direct draft publication path for tests passing draft_answer and grounded self_check
    self_check = state.get("self_check")
    if not (self_check and getattr(self_check, "grounded", False)):
        return {
            "route": "fallback_response",
            "fallback_reason": state.get("fallback_reason", "verification_failed"),
        }

    answer = state.get("draft_answer")
    if not answer:
        return {
            "route": "fallback_response",
            "fallback_reason": state.get("fallback_reason", "verification_failed"),
        }

    _, citations = build_evidence_context(state.get("selected_evidence", []))
    registry = {c.citation_id: c for c in citations}
    cited_ids = list(dict.fromkeys(re.findall(r"\[(C\d+)\]", answer)))
    used = [cid for cid in cited_ids if cid in registry] if cited_ids else []

    ans_kind = state.get("answer_kind", "factual")
    if not used and ans_kind != "coaching":
        return {
            "route": "fallback_response",
            "fallback_reason": "verification_failed" if cited_ids else "insufficient_evidence",
        }

    claims_truncated = False
    if len(answer) > 12000:
        lines = []
        cur_len = 0
        for line in answer.splitlines():
            add_len = len(line) + (1 if lines else 0)
            if cur_len + add_len <= 12000:
                lines.append(line)
                cur_len += add_len
            else:
                claims_truncated = True
                break
        answer = "\n".join(lines)

    canonical_citations = []
    seen_cids = set()
    for cid in used:
        if cid not in seen_cids and cid in registry:
            seen_cids.add(cid)
            canonical_citations.append(registry[cid])

    missing = list(self_check.missing_information) if self_check and self_check.missing_information else []
    missing_reqs = getattr(self_check, "missing_requirement_ids", [])
    if missing_reqs and not missing:
        missing = [f"Yêu cầu {rid} chưa có dữ kiện" for rid in missing_reqs]
    if claims_truncated:
        status = "partial"
        if not missing:
            missing = ["Thông tin được rút gọn để phù hợp độ dài tối đa"]
    else:
        status = "partial" if missing else "answered"

    from src.agents.copilot.insights import build_complementary_insights

    product_insights = build_complementary_insights(state, answer, existing_citations=canonical_citations)

    suggestions_safe = getattr(self_check, "suggestions_safe", True)
    suggested_message = state.get("suggested_message") if suggestions_safe else None
    suggested_next_question = state.get("suggested_next_question") if suggestions_safe else None
    talking_points = (
        [answer]
        if not claims_truncated and len(answer) <= 500 and (status == "answered" or state.get("talking_points"))
        else []
    )

    final = CopilotResponse(
        status=status,
        answer=answer,
        citations=canonical_citations,
        product_insights=product_insights,
        missing_information=missing[:6] if status == "partial" else [],
        talking_points=talking_points,
        suggested_message=suggested_message,
        suggested_next_question=suggested_next_question,
        sales_actions=[],
        request_id=state.get("request_id"),
        reason_code="insufficient_evidence" if status == "partial" else None,
        answer_kind=ans_kind,
    )
    return {"final_response": final, "route": "end"}


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
            missing_information=[r.description for r in state.get("requirements", [])][:6],
            request_id=state.get("request_id"),
        )
    return {"final_response": final, "route": "end"}
