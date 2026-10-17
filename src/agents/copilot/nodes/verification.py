import hashlib
import re

from src.agents.copilot import prompts
from src.agents.copilot.model_io import _invoke_json
from src.agents.copilot.nodes._shared import can_regenerate, observed, schedule_corrective
from src.agents.copilot.state import SelfCheckVerdict, VerifiedAnswerSnapshot
from src.agents.copilot.tools import build_evidence_context, parse_answer_citations
from src.observability import annotate, event


@observed
async def check_grounding(state):
    draft = state.get("draft_answer")

    if not draft:
        if state.get("verified_snapshot"):
            return {
                "route": "finalize_response",
                "fallback_reason": "verification_failed",
            }
        return {
            "feedback": "Không nhận được câu trả lời hợp lệ; vui lòng sinh lại.",
            "fallback_reason": "verification_failed",
            "route": "generate_answer" if can_regenerate(state) else "fallback_response",
        }

    # Context and evidence check
    allowed_ids = set()
    all_citations = []
    if state.get("selected_evidence"):
        _, all_citations = build_evidence_context(state["selected_evidence"])
        allowed_ids.update(c.citation_id for c in all_citations)
    if state.get("answer_context"):
        allowed_ids.update(re.findall(r"\[(C\d+)\]", state["answer_context"]))

    # Shared citation parser checking both unknown IDs and malformed markers
    parsed_cits = parse_answer_citations(draft, allowed_cids=allowed_ids if allowed_ids else None)
    invalid_markers = parsed_cits["malformed"] + parsed_cits["unknown_ids"]
    if invalid_markers:
        verdict = SelfCheckVerdict(
            grounded=False,
            feedback=f"Trích dẫn không hợp lệ hoặc sai định dạng: {', '.join(invalid_markers)}.",
            unsupported_claims=[f"Marker sai: {cid}" for cid in invalid_markers[:5]],
            missing_information=[],
            answered_requirement_ids=[],
            missing_requirement_ids=[r.requirement_id for r in state.get("requirements", [])],
            recovery="regenerate",
            suggestions_safe=False,
        )
        if can_regenerate(state):
            return {
                "self_check": verdict,
                "feedback": verdict.feedback,
                "unsupported_claims": verdict.unsupported_claims,
                "fallback_reason": "verification_failed",
                "route": "generate_answer",
            }
        if state.get("verified_snapshot"):
            return {
                "self_check": verdict,
                "fallback_reason": "verification_failed",
                "route": "finalize_response",
            }
        return {
            "self_check": verdict,
            "feedback": verdict.feedback,
            "unsupported_claims": verdict.unsupported_claims,
            "fallback_reason": "verification_failed",
            "route": "fallback_response",
        }

    req_list = [
        {"requirement_id": r.requirement_id, "kind": r.kind, "description": r.description}
        for r in state.get("requirements", [])
    ]

    verdict, _ = await _invoke_json(
        state,
        prompts.CHECK_PROMPT,
        {
            "query": state["query"],
            "requirements": req_list,
            "history": state.get("history", [])[-6:],
            "draft_answer": draft,
            "sources": state.get("answer_context", "") or "",
            "lookup_date": state["resolved_date"],
            "customer_context": state.get("customer_context", ""),
            "memory_summary": state.get("memory_summary") or "",
            "unsupported_claims": state.get("unsupported_claims", []),
        },
        SelfCheckVerdict,
        node="check_grounding",
    )

    event(
        "verification.self_check",
        grounded=verdict.grounded,
        unsupported_count=len(verdict.unsupported_claims),
        generation_attempt=state.get("generation_count", 0),
    )

    annotate(
        grounded=verdict.grounded,
        unsupported_count=len(verdict.unsupported_claims),
        generation_attempt=state.get("generation_count", 0),
    )

    req_map = {r.requirement_id: r for r in state.get("requirements", [])}
    all_req_ids = set(req_map.keys())
    missing_ids = list(getattr(verdict, "missing_requirement_ids", []) or [])
    answered_ids = list(getattr(verdict, "answered_requirement_ids", []) or [])

    # Invariant: reject unknown requirement IDs (e.g. R99 cannot make R1 answered)
    if not (set(answered_ids) <= all_req_ids) or not (set(missing_ids) <= all_req_ids):
        verdict = verdict.model_copy(
            update={
                "grounded": False,
                "feedback": "Phát hiện mã yêu cầu không hợp lệ trong kết quả kiểm tra.",
            }
        )
    else:
        # Tự động bổ sung các IDs còn thiếu vào missing_requirement_ids nếu checker bỏ sót
        unmentioned = all_req_ids - (set(answered_ids) | set(missing_ids))
        if unmentioned:
            missing_ids.extend(sorted(unmentioned))

    missing_fact_ids = [rid for rid in missing_ids if req_map.get(rid) and req_map[rid].kind == "fact"]
    has_missing_fact = bool(missing_fact_ids)
    if not missing_ids and verdict.missing_information:
        # Keep the conservative outcome, but expose inconsistent checker coverage.
        event("verification.inconsistent_coverage", missing_information_count=len(verdict.missing_information))

    # Invariant: an answer with 0 citations when evidence exists and fact requirements exist cannot be grounded
    registry = {c.citation_id: c for c in all_citations}
    used_cids = [cid for cid in parsed_cits["cited_ids"] if cid in registry]
    if (
        verdict.grounded
        and not used_cids
        and state.get("selected_evidence")
        and any(r.kind == "fact" for r in state.get("requirements", []))
    ):
        verdict = verdict.model_copy(
            update={"grounded": False, "feedback": "Câu trả lời thiếu trích dẫn nguồn cho các dữ kiện."}
        )
    if verdict.grounded and verdict.unsupported_claims:
        verdict = verdict.model_copy(
            update={
                "grounded": False,
                "feedback": verdict.feedback or "Phát hiện phát biểu không được tài liệu nguồn hỗ trợ.",
            }
        )

    if verdict.grounded:
        # Build snapshot for current grounded draft
        draft_hash = hashlib.sha256(draft.encode()).hexdigest()
        context_hash = hashlib.sha256(state.get("answer_context", "").encode()).hexdigest()
        req_str = "|".join(f"{r.requirement_id}:{r.kind}" for r in state.get("requirements", []))
        requirements_hash = hashlib.sha256(req_str.encode()).hexdigest()
        corpus_fp = getattr(state.get("snapshot"), "fingerprint", "") or ""
        snapshot_citations = [registry[cid].model_copy(deep=True) for cid in used_cids]

        # Set-based coverage check: all requirements must be in answered set
        answered_set = set(answered_ids)
        is_fully_answered = (
            (bool(all_req_ids) or state.get("answer_kind") == "coaching")
            and (all_req_ids <= answered_set)
            and not verdict.missing_information
        )
        snap_status = "answered" if is_fully_answered else "partial"

        snapshot_missing: list[str] = []
        if snap_status == "partial":
            snapshot_missing = [str(m).strip() for m in verdict.missing_information if str(m).strip()]
            if not snapshot_missing:
                for mid in missing_ids:
                    req = req_map.get(mid)
                    if req and req.description:
                        snapshot_missing.append(f"Chưa có đủ dữ liệu xác thực cho: {req.description}"[:500])
                    else:
                        snapshot_missing.append(f"Chưa có đủ dữ liệu xác thực cho yêu cầu {mid}."[:500])
            if not snapshot_missing:
                snapshot_missing.append("Một số nội dung yêu cầu chưa có đủ tài liệu xác thực để đối chiếu.")

        suggestions_safe = getattr(verdict, "suggestions_safe", True)
        suggested_message = state.get("suggested_message") if suggestions_safe else None
        suggested_next_question = state.get("suggested_next_question") if suggestions_safe else None

        snapshot = VerifiedAnswerSnapshot(
            answer=draft,
            draft_hash=draft_hash,
            context_hash=context_hash,
            requirements_hash=requirements_hash,
            resolved_date=str(state.get("resolved_date", "")),
            corpus_fingerprint=corpus_fp,
            citations=snapshot_citations,
            answered_requirement_ids=answered_ids,
            missing_requirement_ids=missing_ids,
            missing_information=snapshot_missing,
            status=snap_status,
            reason_code="insufficient_evidence" if snap_status == "partial" else None,
            created_at_attempt=state.get("generation_count", 0),
            answer_kind=state.get("answer_kind", "factual"),
            suggested_message=suggested_message,
            suggested_next_question=suggested_next_question,
        )

        # If there are missing factual requirements, evaluate targeted recovery
        if has_missing_fact:
            # Relevance heuristics cannot establish factual support. Follow the
            # checker; absent an explicit regeneration request, retrieve facts.
            if verdict.recovery == "regenerate" and can_regenerate(state):
                return {
                    "self_check": verdict,
                    "verified_snapshot": snapshot,
                    "feedback": verdict.feedback
                    or f"Bổ sung dữ kiện còn thiếu cho yêu cầu {', '.join(missing_fact_ids)}.",
                    "recovery_requirement_ids": missing_fact_ids,
                    "route": "generate_answer",
                }
            if verdict.recovery != "regenerate":
                corrective = schedule_corrective(
                    state, feedback=verdict.feedback or "Tìm kiếm nguồn bổ sung cho dữ kiện còn thiếu."
                )
                if corrective:
                    return {
                        "self_check": verdict,
                        "verified_snapshot": snapshot,
                        "recovery_requirement_ids": missing_fact_ids,
                        **corrective,
                    }

        return {
            "self_check": verdict,
            "verified_snapshot": snapshot,
            "feedback": "",
            "unsupported_claims": [],
            "route": "finalize_response",
        }

    # Not grounded (extrapolation or unsupported claims detected)
    if verdict.recovery != "regenerate" and has_missing_fact:
        corrective = schedule_corrective(
            state,
            feedback=verdict.feedback or "Tìm kiếm nguồn bổ sung cho phát biểu thiếu dẫn chứng.",
        )
        if corrective:
            return {
                "self_check": verdict,
                "recovery_requirement_ids": missing_fact_ids,
                **corrective,
            }

    if can_regenerate(state):
        annotate(recovery="regenerate")
        return {
            "self_check": verdict,
            "feedback": verdict.feedback or "Phát hiện suy diễn vượt chứng cứ hoặc thiếu nguồn hỗ trợ.",
            "unsupported_claims": verdict.unsupported_claims,
            "route": "generate_answer",
        }

    # Recovery exhausted:
    # If a previous snapshot was verified, fall back to that snapshot!
    if state.get("verified_snapshot"):
        return {
            "self_check": verdict,
            "fallback_reason": "verification_failed",
            "route": "finalize_response",
        }

    # No valid snapshot ever -> ABSTAIN dứt khoát
    return {
        "self_check": verdict,
        "feedback": verdict.feedback,
        "unsupported_claims": verdict.unsupported_claims,
        "fallback_reason": "verification_failed",
        "route": "fallback_response",
    }
