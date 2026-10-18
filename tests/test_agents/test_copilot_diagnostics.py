"""Evidence sufficiency must not be confused with generated answer coverage."""

import pytest

from src.agents.copilot.nodes import verification
from src.agents.copilot.state import Requirement, StructuredGroundingReview, VerifiedAnswerSnapshot
from src.agents.copilot.validation.structured import summarize_grounding_review, validate_grounding_review
from tests.test_agents.test_copilot_agentic import checked, draft_state


def missing_review(**changes):
    value = checked(answered=["R1"], missing=["R2"], recovery="search")
    value["requirement_verdicts"][1].update({
        "missing_information": "Dung lượng pin", "evidence_status": "sufficient",
        "evidence_citation_ids": ["C1"], "evidence_proofs": [{"citation_id": "C1", "quote": "VF 5"}], "blocker": "answer_omission", **changes,
    })
    if not value["requirement_verdicts"][1]["evidence_citation_ids"]:
        value["requirement_verdicts"][1]["evidence_proofs"] = []
    return StructuredGroundingReview(**value)


def state():
    value = draft_state()
    value["requirements"].append(Requirement(requirement_id="R2", description="Dung lượng pin", product_model="VF 5"))
    return value


def test_unknown_diagnostic_citations_fail():
    review = missing_review()
    review.requirement_verdicts[1].evidence_citation_ids = ["C99"]
    with pytest.raises(ValueError, match="diagnostic citation"):
        validate_grounding_review(review, state())


def test_sufficient_fact_needs_sources():
    review = missing_review()
    review.requirement_verdicts[1].evidence_citation_ids = []
    review.requirement_verdicts[1].evidence_proofs = []
    with pytest.raises(ValueError, match="requires source citations"):
        validate_grounding_review(review, state())


def test_not_found_can_reference_the_inspected_source_without_proving_a_missing_value():
    review = missing_review(evidence_status="not_found", blocker="insufficient_context")
    result = summarize_grounding_review(review, state())
    assert result.answered_requirement_ids == ["R1"]
    item = result.requirement_diagnostics[1]
    assert item.status == "missing" and item.evidence_status == "not_found"
    assert item.evidence_citation_ids == ["C1"]


def test_conflicting_evidence_cannot_be_declared_sufficient():
    with pytest.raises(ValueError, match="unresolved evidence blocker"):
        validate_grounding_review(missing_review(blocker="source_conflict"), state())


@pytest.mark.parametrize("evidence_status", ["partial", "not_found", "unknown"])
def test_bad_answer_and_incomplete_evidence_can_coexist_without_discarding_valid_goals(evidence_status):
    review = missing_review(evidence_status=evidence_status, blocker="incorrect_answer",
                            evidence_citation_ids=[], evidence_proofs=[])
    result = summarize_grounding_review(review, state())
    assert result.answered_requirement_ids == ["R1"]
    assert result.missing_requirement_ids == ["R2"]
    item = result.requirement_diagnostics[1]
    assert item.evidence_status == evidence_status
    assert item.blocker == ("verification_uncertain" if evidence_status == "unknown" else "insufficient_context")
    assert review.requirement_verdicts[1].blocker == "incorrect_answer"


@pytest.mark.asyncio
async def test_answer_omission_regenerates_before_search(monkeypatch):
    async def invoke(*args, **kwargs):
        return missing_review(), {}
    monkeypatch.setattr(verification, "_invoke_json", invoke)
    result = await verification.check_grounding(state())
    assert result["route"] == "generate_answer"
    assert "corrective_retrieval_count" not in result
    assert result["verified_snapshot"].requirement_diagnostics[1].blocker == "answer_omission"


@pytest.mark.asyncio
async def test_external_input_gap_does_not_search(monkeypatch):
    review = missing_review()
    review.requirement_verdicts[1].evidence_status = "unknown"
    review.requirement_verdicts[1].evidence_citation_ids = []
    review.requirement_verdicts[1].evidence_proofs = []
    review.requirement_verdicts[1].blocker = "missing_input"
    async def invoke(*args, **kwargs):
        return review, {}
    monkeypatch.setattr(verification, "_invoke_json", invoke)
    result = await verification.check_grounding(state())
    assert result["route"] == "finalize_response"


def test_downgraded_checker_link_does_not_publish_answered_diagnostic():
    current = state()
    review = missing_review()
    item = review.requirement_verdicts[1]
    item.status, item.blocker, item.supporting_claim_indices = "answered", "none", [0]
    item.missing_information = ""
    result = summarize_grounding_review(review, current)
    diagnostic = result.requirement_diagnostics[1]
    assert diagnostic.status == "missing"
    assert diagnostic.blocker == "answer_omission"
    assert diagnostic.evidence_status == "sufficient"
    assert diagnostic.supporting_claim_indices == []
    assert "đã có nguồn" in diagnostic.missing_information
    assert item.status == "answered"  # Preserve the raw review for audit.


@pytest.mark.asyncio
async def test_missing_input_does_not_regenerate_on_unhelpful_model_recovery(monkeypatch):
    review = missing_review(evidence_status="unknown", evidence_citation_ids=[], blocker="missing_input")
    review.recovery = "regenerate"
    async def invoke(*args, **kwargs):
        return review, {}
    monkeypatch.setattr(verification, "_invoke_json", invoke)
    result = await verification.check_grounding(state())
    assert result["route"] == "finalize_response"


def test_followup_preserves_scope_and_complete_dependency_chain():
    from src.agents.copilot.nodes.answer import _repair_question
    requirements = [
        Requirement(requirement_id="R1", description="Giá VF 3", product_model="VF 3", variant="Plus TC2", qualifiers=["kèm pin gồm VAT"]),
        Requirement(requirement_id="R2", description="Giá VF 5", product_model="VF 5", variant="Plus TC1", qualifiers=["kèm pin gồm VAT"]),
        Requirement(requirement_id="R3", description="Tính chênh lệch giá", depends_on=["R1", "R2"]),
    ]
    snapshot = VerifiedAnswerSnapshot(
        answer="Một phần", resolved_date="2026-10-01", status="partial", missing_information=["Chênh lệch"],
        missing_requirement_ids=["R3"],
        requirement_diagnostics=[{"requirement_id": "R3", "status": "missing", "evidence_status": "sufficient"}],
    )
    question = _repair_question(snapshot, requirements)
    assert all(value in question for value in ["2026-10-01", "VF 3", "VF 5", "Plus TC2", "Plus TC1", "kèm pin gồm VAT"])
    requirements[0].description = "x" * 500
    assert _repair_question(snapshot, requirements) is None


@pytest.mark.asyncio
async def test_finalize_rollback_keeps_published_snapshot_diagnostics():
    from src.agents.copilot.nodes.answer import finalize_response
    current = state()
    snapshot = VerifiedAnswerSnapshot(
        answer=current["draft_answer"], citations=[], resolved_date=current["resolved_date"],
        status="partial", answer_kind="coaching", missing_information=["Dung lượng pin"],
        answered_requirement_ids=["R1"], missing_requirement_ids=["R2"],
        requirement_diagnostics=missing_review().requirement_verdicts,
    )
    current.update(verified_snapshot=snapshot, grounding_review=missing_review(evidence_status="unknown", evidence_citation_ids=[], blocker="external_data"))
    result = (await finalize_response(current))["final_response"]
    assert result.requirement_diagnostics[1].evidence_status == "sufficient"
    assert "Dung lượng pin" in result.suggested_next_question
