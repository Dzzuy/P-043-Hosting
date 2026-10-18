"""Validate that the logged publication belongs to its checked snapshot."""

from src.agents.copilot.context import evidence_fingerprints
from src.agents.copilot.state import GeneratedAnswer, Requirement, StructuredGroundingReview
from src.agents.copilot.validation.structured import render_answer, verified_answer


def publication_matches(state, row):
    """Bind a published answer to the actual review, including safe block removal."""
    snapshot = state.get("verified_snapshot") or {}
    if snapshot.get("answer") != row.get("answer") or snapshot.get("citations") != row.get("citations"):
        return False
    if snapshot.get("resolved_date") != state.get("resolved_date"):
        return False
    if snapshot.get("evidence_fingerprints") != evidence_fingerprints(
        state.get("selected_evidence", []), state.get("jev_conflict_chunk_ids", [])
    ):
        return False
    try:
        typed = {
            **state,
            "generated_answer": GeneratedAnswer(**state["generated_answer"]),
            "requirements": [Requirement(**r) for r in state["requirements"]],
        }
        if render_answer(typed["generated_answer"]) != state.get("draft_answer"):
            return False
        candidate, verdict = verified_answer(StructuredGroundingReview(**state["grounding_review"]), typed)
        return (
            candidate is not None
            and render_answer(candidate) == row["answer"]
            and snapshot.get("requirement_diagnostics") == [d.model_dump() for d in verdict.requirement_diagnostics]
        )
    except (ValueError, KeyError, TypeError):
        return False
