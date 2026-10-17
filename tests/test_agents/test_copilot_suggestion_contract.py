"""Suggestions remain subordinate to checked facts and the public response contract."""

import pytest
from pydantic import ValidationError

from src.agents.copilot import nodes
from src.agents.copilot.state import ABSTAIN_ANSWER, CopilotResponse, GeneratedAnswer, GroundedClaim, SelfCheckVerdict
from src.api.copilot import CopilotQueryRequest, query_copilot
from tests.test_agents.test_copilot_agentic import checked, draft_state, generated, scripted


def test_generated_output_does_not_duplicate_answer_or_quotes():
    schema = GeneratedAnswer.model_json_schema()
    assert "answer" not in schema["properties"]
    assert "evidence_quotes" not in str(schema)
    assert GeneratedAnswer(**generated()).suggested_message is None


def test_abstention_cannot_expose_sales_suggestions():
    with pytest.raises(ValidationError, match="sales suggestions"):
        CopilotResponse(status="abstained", answer=ABSTAIN_ANSWER, suggested_message="Cam kết giá tốt nhất")


def test_suggestion_count_and_size_are_bounded():
    with pytest.raises(ValidationError):
        GeneratedAnswer(**generated(), sales_actions=["a"] * 4)
    with pytest.raises(ValidationError):
        GeneratedAnswer(**generated(), suggested_message="x" * 501)


@pytest.mark.asyncio
@pytest.mark.parametrize("safe", [True, False])
async def test_only_reviewed_suggestions_are_published(monkeypatch, safe):
    state = draft_state()
    state["draft_answer"] = "VF 5 có quãng đường 326 km NEDC [C1]"
    state["suggested_message"] = "Em có thể gửi tài liệu VF 5 để đối chiếu."
    state["suggested_next_question"] = "Anh/chị có chỗ sạc ở nhà không?"
    verdict = checked()
    verdict["suggestions_safe"] = safe
    scripted(monkeypatch, [verdict])
    state.update(await nodes.check_grounding(state))
    result = (await nodes.finalize_response(state))["final_response"]
    assert bool(result.suggested_message) == safe
    assert result.talking_points == [result.answer]


@pytest.mark.asyncio
async def test_finalizer_keeps_whole_long_claims_within_public_limits():
    state = draft_state()
    long_answer = "\n".join("x" * 1000 + " [C1]" for _ in range(12))
    state.update(
        draft_answer=long_answer,
        self_check=SelfCheckVerdict(grounded=True, missing_information=["Thông tin một phần"]),
    )
    response = (await nodes.finalize_response(state))["final_response"]
    assert len(response.answer) <= 12000 and response.status == "partial"
    assert all(line == "x" * 1000 + " [C1]" for line in response.answer.splitlines())
    assert response.talking_points == []


@pytest.mark.asyncio
async def test_finalizer_with_rejected_sources_cannot_loop_back():
    state = draft_state()
    state.update(
        draft_answer="VF 5 [C99]",
        self_check=SelfCheckVerdict(grounded=True),
    )
    state.update(await nodes.finalize_response(state))
    response = (await nodes.fallback_response(state))["final_response"]
    assert response.status == "abstained" and response.reason_code == "verification_failed"


@pytest.mark.asyncio
async def test_copilot_api_returns_suggestions_without_changing_existing_fields(monkeypatch):
    async def fake_graph(state, **kwargs):
        return {
            "final_response": CopilotResponse(
                status="answered",
                answer="Bảng giá có thông tin VF 8 [C1].",
                citations=[
                    {
                        "citation_id": "C1",
                        "chunk_id": "price-1",
                        "document_id": "price-list",
                        "title": "Bảng giá",
                    }
                ],
                talking_points=["Bảng giá có thông tin VF 8 [C1]."],
                suggested_message="Em có thể gửi anh/chị bảng giá để đối chiếu.",
                suggested_next_question="Anh/chị muốn xem phiên bản nào?",
            )
        }

    monkeypatch.setattr("src.api.copilot.copilot_agent.ainvoke", fake_graph)
    response = await query_copilot(CopilotQueryRequest(query="Giá VF 8?"))

    assert response.answer == "Bảng giá có thông tin VF 8 [C1]."
    assert response.citations[0].document_id == "price-list"
    assert response.is_abstain is False
    assert response.talking_points == ["Bảng giá có thông tin VF 8 [C1]."]
    assert response.suggested_message == "Em có thể gửi anh/chị bảng giá để đối chiếu."
    assert response.suggested_next_question == "Anh/chị muốn xem phiên bản nào?"
