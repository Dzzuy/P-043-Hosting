"""Source scope, monotonic snapshots and unchanged-context recovery."""

import json
from types import SimpleNamespace

import pytest

from src.agents.copilot import model_io
from src.agents.copilot.context import evidence_fingerprints, format_selected_context
from src.agents.copilot.nodes import evidence, verification
from src.agents.copilot.state import (
    ClaimVerdict,
    EvidenceProof,
    GroundedClaim,
    Requirement,
    StructuredGroundingReview,
    VerifiedAnswerSnapshot,
)
from src.agents.copilot.validation.structured import (
    render_answer,
    summarize_grounding_review,
    validate_grounding_review,
    verified_answer,
)
from tests.test_agents.test_copilot_agentic import checked, draft_state, scripted


def test_checker_scope_error_downgrades_goal_without_discarding_raw_review():
    current = draft_state()
    current["generated_answer"].claims[0].text = "VF 5 Plus TC99: 326 km NEDC"
    value = checked(status="unsupported", recovery="regenerate")
    value["claim_verdicts"][0]["error_codes"] = ["unsupported_scope"]
    result = summarize_grounding_review(StructuredGroundingReview(**value), current)
    assert not result.grounded and result.missing_requirement_ids == ["R1"]
    assert result.recovery == "regenerate"


def test_quote_must_come_from_actual_claim_source():
    current = draft_state()
    review = StructuredGroundingReview(**checked())
    review.claim_verdicts[0].evidence_proofs = [EvidenceProof(citation_id="C1", quote="Invented scope")]
    with pytest.raises(ValueError, match="evidence quote"):
        validate_grounding_review(review, current)


def snapshot(current, **changes):
    return VerifiedAnswerSnapshot(**{
        "answer": current["draft_answer"], "resolved_date": current["resolved_date"],
        "answered_requirement_ids": ["R1"], "status": "partial", "missing_information": ["Pin"],
        "missing_requirement_ids": ["R2"], "evidence_fingerprints": evidence_fingerprints(current["selected_evidence"]),
        **changes,
    })


def auxiliary_failure():
    current = draft_state()
    current["generated_answer"].claims.append(GroundedClaim(
        text="Chi tiết phụ VF 5 chưa có nguồn", requirement_ids=["R1"], citation_ids=["C1"],
    ))
    current["draft_answer"] = render_answer(current["generated_answer"])
    review = StructuredGroundingReview(**checked())
    review.claim_verdicts.append(ClaimVerdict(claim_index=1, status="unsupported", error_codes=["unsupported_claim"]))
    return current, review


@pytest.mark.asyncio
async def test_failed_auxiliary_block_does_not_discard_proven_goals(monkeypatch):
    from eval.copilot_eval.publication import publication_matches
    from eval.copilot_eval.telemetry import serial
    current, review = auxiliary_failure()
    original = current["draft_answer"]
    async def invoke(*args, **kwargs):
        return review, {}
    monkeypatch.setattr(verification, "_invoke_json", invoke)
    result = await verification.check_grounding(current)
    assert result["route"] == "finalize_response"
    published = result["verified_snapshot"]
    assert published.status == "answered"
    assert "Chi tiết phụ" not in published.answer
    assert current["draft_answer"] == original
    assert len(result["grounding_review"].claim_verdicts) == 2
    logged = serial({**current, **result})
    row = {"answer": published.answer, "citations": serial(published.citations)}
    assert publication_matches(logged, row)
    logged["selected_evidence"][0]["content"] = "Changed source"
    assert not publication_matches(logged, row)


def test_failed_goal_or_unsafe_review_cannot_be_salvaged():
    current, review = auxiliary_failure()
    review.suggestions_safe = False
    assert verified_answer(review, current)[0] is None
    review.suggestions_safe = True
    review.requirement_verdicts[0].supporting_claim_indices = [0, 1]
    assert verified_answer(review, current)[0] is None


def test_projection_remaps_supporting_indices_without_mutating_review():
    current, review = auxiliary_failure()
    current["generated_answer"].claims.reverse()
    review.claim_verdicts[0].claim_index = 1
    review.claim_verdicts[1].claim_index = 0
    review.requirement_verdicts[0].supporting_claim_indices = [1]
    answer, verdict = verified_answer(review, current)
    assert len(answer.claims) == 1
    assert verdict.requirement_diagnostics[0].supporting_claim_indices == [0]
    assert review.requirement_verdicts[0].supporting_claim_indices == [1]


def test_valid_goal_survives_a_failed_other_goal_as_partial():
    current, review = auxiliary_failure()
    review.claim_verdicts[1].feedback = "Dữ kiện không đúng đơn vị nguồn."
    current["requirements"].append(Requirement(requirement_id="R2", description="Other requested fact"))
    current["generated_answer"].claims[1].requirement_ids = ["R2"]
    review.requirement_verdicts.append(review.requirement_verdicts[0].model_copy(update={
        "requirement_id": "R2", "supporting_claim_indices": [1],
    }))
    answer, verdict = verified_answer(review, current)
    assert answer is not None and len(answer.claims) == 1
    assert verdict.grounded and verdict.answered_requirement_ids == ["R1"]
    assert verdict.missing_requirement_ids == ["R2"]
    assert verdict.requirement_diagnostics[1].blocker == "incorrect_answer"
    assert "không đúng đơn vị" in verdict.feedback
    assert verdict.unsupported_claims
    assert review.requirement_verdicts[1].status == "answered"


@pytest.mark.asyncio
async def test_scope_quote_retry_explains_contract_without_rewriting_answer(monkeypatch):
    current = draft_state()
    bad = checked()
    bad["claim_verdicts"][0]["evidence_proofs"] = [{
        "citation_id": "C1", "quote": "section: VF 5\n326 km",
    }]
    scripted(monkeypatch, [bad, checked()])
    first = await verification.check_grounding(current)
    assert first["route"] == "check_grounding"
    assert "không ghép" in first["feedback"]
    second = await verification.check_grounding({**current, **first})
    assert second["route"] == "finalize_response"
    assert second["verified_snapshot"].answer == current["draft_answer"]


@pytest.mark.asyncio
async def test_identical_context_keeps_verified_snapshot_but_new_content_does_not():
    current = draft_state()
    current["answer_context"] = format_selected_context(current["selected_evidence"])
    current.update(verified_snapshot=snapshot(current), corrective_retrieval_count=1)
    result = await evidence.build_context(current)
    assert result["route"] == "finalize_response"
    current["selected_evidence"][0]["content"] += "\nNew relevant fact"
    assert (await evidence.build_context(current))["route"] == "generate_answer"


@pytest.mark.asyncio
async def test_unchanged_context_does_not_skip_answer_omission_repair():
    current = draft_state()
    current["answer_context"] = format_selected_context(current["selected_evidence"])
    current.update(verified_snapshot=snapshot(current, requirement_diagnostics=[{
        "requirement_id": "R2", "status": "missing", "evidence_status": "sufficient",
    }]), corrective_retrieval_count=1)
    assert (await evidence.build_context(current))["route"] == "generate_answer"


@pytest.mark.asyncio
async def test_removing_checked_sources_keeps_snapshot_but_changed_conflict_role_does_not():
    current = draft_state()
    extra = dict(current["selected_evidence"][0], chunk_id="other", citation_id="C2", content="Other source")
    current["selected_evidence"].append(extra)
    original = snapshot(current)
    current.update(verified_snapshot=original, corrective_retrieval_count=1)
    current["selected_evidence"] = current["selected_evidence"][:1]
    result = await evidence.build_context(current)
    assert result["route"] == "finalize_response"
    assert current["verified_snapshot"] is original
    current["jev_conflict_chunk_ids"] = [current["selected_evidence"][0]["chunk_id"]]
    assert (await evidence.build_context(current))["route"] == "generate_answer"


@pytest.mark.asyncio
async def test_added_evidence_or_changed_citation_label_still_needs_verification():
    current = draft_state()
    current.update(verified_snapshot=snapshot(current), corrective_retrieval_count=1)
    current["selected_evidence"].append(dict(current["selected_evidence"][0], chunk_id="new", citation_id="C2"))
    assert (await evidence.build_context(current))["route"] == "generate_answer"
    current["selected_evidence"] = current["selected_evidence"][:1]
    current["selected_evidence"][0]["citation_id"] = "C2"
    assert (await evidence.build_context(current))["route"] == "generate_answer"


@pytest.mark.asyncio
async def test_unchanged_sources_cannot_approve_changed_date_or_unverified_draft():
    current = draft_state()
    current.update(verified_snapshot=snapshot(current), corrective_retrieval_count=1)
    current["resolved_date"] = "2026-12-01"
    assert (await evidence.build_context(current))["route"] == "generate_answer"
    current["resolved_date"] = current["verified_snapshot"].resolved_date
    current["draft_answer"] += " New unchecked statement."
    assert (await evidence.build_context(current))["route"] == "generate_answer"


@pytest.mark.asyncio
async def test_equal_count_different_goals_cannot_replace_snapshot(monkeypatch):
    current = draft_state()
    current["requirements"].append(Requirement(requirement_id="R2", description="Other goal"))
    current["verified_snapshot"] = snapshot(current)
    current["generated_answer"].claims[0].requirement_ids = ["R2"]
    current["generation_count"] = 2
    async def invoke(*args, **kwargs):
        return StructuredGroundingReview(**checked(answered=["R2"], missing=["R1"])), {}
    monkeypatch.setattr(verification, "_invoke_json", invoke)
    result = await verification.check_grounding(current)
    assert result["route"] == "finalize_response"
    assert "verified_snapshot" not in result
    assert current["verified_snapshot"].answered_requirement_ids == ["R1"]


@pytest.mark.asyncio
async def test_duplicate_json_objects_are_rejected_and_retry_targets_serialization(monkeypatch):
    class DuplicateModel:
        async def ainvoke(self, messages):
            raw = json.dumps(checked())
            return SimpleNamespace(content=raw + "\n" + raw)

    monkeypatch.setattr(model_io, "get_llm", lambda **kwargs: DuplicateModel())
    current = draft_state()
    first = await verification.check_grounding(current)
    assert first["route"] == "check_grounding"
    assert "MỘT object" in first["feedback"]
    attempts = [e for e in current["runtime"].events if e.get("llm")]
    assert attempts[-1]["validation_code"] == "json_invalid"
    assert "verified_snapshot" not in first
    second = await verification.check_grounding(current)
    assert second["route"] == "fallback_response"
    assert current["runtime"].attempts == 2

