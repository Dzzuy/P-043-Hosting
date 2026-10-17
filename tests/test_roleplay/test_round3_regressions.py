"""Round-three backend regression coverage using durable graph state."""

from copy import deepcopy
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from src.agents.roleplay.contracts import ScenarioContract
from src.agents.roleplay.customer_agent import CustomerAgent
from src.agents.roleplay.graph import RoleplayGraph, RoleplaySessionConflictError
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import RoleplayState, TerminationStatus
from src.agents.roleplay.state_reducer import apply_turn_analysis
from src.agents.roleplay.turn_analyzer import TurnAnalysis, TurnAnalyzer
from src.api.practice import create_practice_router
from src.api.practice_errors import PracticeAPIError, practice_exception_handler, session_conflict
from src.api.recorded_practice import create_recorded_practice_routers
from src.models.auth import AuthenticatedUser
from src.models.evaluation import SessionEvaluationResult
from src.services.practice_records import AssignmentConflictError, ReviewConflictError

SCENARIO = "SCENARIO_04_VF6_ECO_PLUS_UPSELL"
OBJECTION = "OBJ_VF6_PROMO_ELIGIBILITY"


class Checkpoint:
    def __init__(self):
        self.states = {}

    async def load(self, key):
        return deepcopy(self.states.get(key))

    async def save(self, key, value):
        self.states[key] = deepcopy(value)


def runtime():
    checkpoint = Checkpoint()
    analysis = Mock()
    analysis.analyze = AsyncMock(return_value={})
    customer = Mock()
    customer.generate = AsyncMock(return_value={"reply": "Chị muốn xem xe."})
    graph = RoleplayGraph(ScenarioRepository(), TurnAnalyzer(analysis), CustomerAgent(customer), checkpoint)
    return graph, checkpoint, analysis, customer


@pytest.mark.asyncio
@pytest.mark.parametrize("recorded", [False, True])
@pytest.mark.parametrize("failure", ["analysis", "customer"])
async def test_provider_error_matches_durable_advisor_turn(recorded, failure):
    graph, checkpoint, analysis, customer = runtime()
    await graph.start("session", SCENARIO)
    if failure == "analysis":
        analysis.analyze.return_value = {"factual_claims": "invalid"}
    else:
        customer.generate.return_value = {"reply": ""}
    service = Mock()

    async def send_message(session_id, *args):
        return await graph.continue_session(session_id, args[-1])

    service.send_message = send_message
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    if recorded:

        async def identity():
            return AuthenticatedUser(user_id="advisor", username="advisor", display_name="Advisor", role="advisor")

        router, _ = create_recorded_practice_routers(service, identity)
    else:
        router = create_practice_router(service)
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/practice/session/message", json={"message": "Xin chào chị"})
    assert response.status_code == 503
    if failure == "analysis":
        assert response.json() == {"code": "message_not_sent", "detail": "Chưa gửi được tin nhắn. Vui lòng gửi lại."}
        assert checkpoint.states["session"]["messages"] == []
        assert checkpoint.states["session"]["turn_count"] == 0
        customer.generate.assert_not_called()
    else:
        assert response.json()["code"] == "provider_unavailable"
        state = await graph.get_session_state("session")
        assert state.turn_count == 1
        assert state.messages[-1].content == "Xin chào chị"
        assert state.pending_customer_reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,expected",
    [
        ("different_scenario", "validation_error"),
        ("different_limit", "validation_error"),
        ("finished", "session_finished"),
        ("pending_message", "session_busy"),
        ("pending_finish", "session_busy"),
        ("no_pending", "validation_error"),
        ("active_evaluation", "validation_error"),
        ("mismatched_evaluation", "validation_error"),
        ("already_evaluated", "validation_error"),
    ],
)
async def test_each_graph_conflict_site_has_explicit_code(case, expected):
    graph, checkpoint, _, _ = runtime()
    await graph.start("session", SCENARIO)
    state = await graph.get_session_state("session")
    result = SessionEvaluationResult.model_construct(session_id="session", scenario_id=SCENARIO)
    if case == "finished":
        state.termination_status = TerminationStatus.ADVISOR_ENDED
    if case.startswith("pending"):
        from src.agents.roleplay.state import RoleplayMessage

        state.messages.append(RoleplayMessage(role="advisor", content="Xin chào"))
    if case in {"mismatched_evaluation", "already_evaluated"}:
        state.termination_status = TerminationStatus.ADVISOR_ENDED
    if case == "mismatched_evaluation":
        result = result.model_copy(update={"session_id": "other"})
    if case == "already_evaluated":
        state.evaluation_result = SessionEvaluationResult.model_construct(session_id="other", scenario_id=SCENARIO)
    # Preserve valid production states for ordinary sites; evaluation comparison
    # needs only the already-loaded typed object, not a full evaluator fixture.
    graph.get_session_state = AsyncMock(return_value=state)
    if case in {"finished", "pending_message"}:
        await checkpoint.save("session", state.model_dump(mode="json"))
    actions = {
        "different_scenario": lambda: graph.start("session", "SCENARIO_01_VF5_TAXI"),
        "different_limit": lambda: graph.start("session", SCENARIO, max_turns=8),
        "finished": lambda: graph.continue_session("session", "Xin chào"),
        "pending_message": lambda: graph.continue_session("session", "Xin chào"),
        "pending_finish": lambda: graph.finish_session("session"),
        "no_pending": lambda: graph.retry_customer_reply("session"),
    }
    with pytest.raises(RoleplaySessionConflictError) as caught:
        if case in actions:
            await actions[case]()
        else:
            await graph.save_evaluation_result("session", result)
    assert caught.value.code == expected
    caught.value.args = ("arbitrary wording without state keywords",)
    assert session_conflict(caught.value).code == expected


def test_eligibility_resolution_requires_known_vehicle():
    scenario = ScenarioRepository().get(SCENARIO)
    state = RoleplayState.from_scenario("session", scenario)
    state.active_objections = [OBJECTION]
    analysis = TurnAnalysis(addressed_objection_ids=[OBJECTION], resolved_objection_ids=[OBJECTION])
    before = apply_turn_analysis(state, scenario, "Dạ được ạ", analysis)
    assert OBJECTION in before.active_objections
    assert OBJECTION not in before.resolved_objections
    state.revealed_facts = ["current_vehicle"]
    after = apply_turn_analysis(state, scenario, "Dạ được ạ", analysis)
    assert OBJECTION in after.resolved_objections
    assert OBJECTION not in after.active_objections


def test_objection_required_facts_must_exist():
    data = ScenarioRepository().get(SCENARIO).model_dump()
    data["objections"][0]["requires_revealed_facts"] = ["unknown_vehicle"]
    with pytest.raises(ValidationError, match="unknown hidden facts"):
        ScenarioContract.model_validate(data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,reason,detail",
    [
        ("assignment", "Advisor does not exist or is inactive.", "Tư vấn viên không tồn tại hoặc đã ngừng hoạt động."),
        ("assignment", "Practice scenario was not found.", "Không tìm thấy kịch bản luyện tập."),
        ("assignment", "Due date cannot be in the past.", "Hạn hoàn thành không được ở trong quá khứ."),
        (
            "assignment",
            "Assignment does not match this advisor and scenario.",
            "Bài được giao không khớp với tư vấn viên và kịch bản này.",
        ),
        ("assignment", "Assignment is already completed.", "Bài được giao này đã hoàn thành."),
        ("review", "attempt is unfinished or already reviewed", "Lượt luyện tập chưa hoàn thành hoặc đã được duyệt."),
        ("review", "attempt is already reviewed", "Lượt luyện tập này đã được duyệt."),
        (
            "review",
            "only assessed criteria may receive score overrides",
            "Chỉ được sửa điểm của tiêu chí đã được đánh giá.",
        ),
        ("assignment", "private unrecognized diagnostics", "Không thể giao hoặc bắt đầu bài luyện tập này."),
        ("review", "private unrecognized diagnostics", "Không thể duyệt lượt luyện tập này."),
    ],
)
async def test_assignment_review_conflicts_have_specific_vietnamese_reasons(kind, reason, detail):
    service = Mock()
    error = AssignmentConflictError(reason) if kind == "assignment" else ReviewConflictError(reason)
    service.start_session = AsyncMock(side_effect=error)
    service.approve = AsyncMock(side_effect=error)

    async def identity():
        role = "advisor" if kind == "assignment" else "manager"
        return AuthenticatedUser(user_id="user", username="user", display_name="User", role=role)

    practice, manager = create_recorded_practice_routers(service, identity)
    app = FastAPI()
    app.add_exception_handler(PracticeAPIError, practice_exception_handler)
    app.include_router(practice)
    app.include_router(manager)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        if kind == "assignment":
            response = await client.post("/practice/sessions", json={"scenario_id": SCENARIO})
        else:
            response = await client.patch("/manager/reviews/session", json={"change_reason": "Đã kiểm tra nội dung"})
    assert response.status_code == 409
    assert response.json() == {"code": f"{kind}_conflict", "detail": detail}


@pytest.mark.asyncio
async def test_customer_acceptance_cannot_bypass_required_vehicle_discovery():
    graph, checkpoint, analysis, customer = runtime()
    await graph.start("session", SCENARIO)
    state = await graph.get_session_state("session")
    state.active_objections = [OBJECTION]
    # A prior customer reply ensures the next reply is not an opening.
    from src.agents.roleplay.state import RoleplayMessage

    state.messages.append(RoleplayMessage(role="customer", content="Chị có được ưu đãi không?"))
    await checkpoint.save("session", state.model_dump(mode="json"))
    analysis.analyze.return_value = {"next_step_attempted": True}
    customer.generate.return_value = {
        "reply": "Chị đồng ý lái thử.",
        "accepted_next_step": True,
        "accepted_outcome_id": "close_eco",
    }
    await graph.continue_session("session", "Chị lái thử nhé?")
    saved = await graph.get_session_state("session")
    assert OBJECTION in saved.active_objections
    assert OBJECTION not in saved.resolved_objections


def test_customer_turn_mode_contains_only_response():
    from typing import get_args

    from src.agents.roleplay.customer_agent import CustomerTurnMode

    assert get_args(CustomerTurnMode) == ("response",)


def test_scenario04_docs_and_smoke_ids_match_contract():
    import json
    from pathlib import Path

    scenario = ScenarioRepository().get(SCENARIO)
    assert scenario.scenario_version == "1.4"
    assert f"SCENARIO_04 version {scenario.scenario_version}" in Path("docs/roleplay-runtime.md").read_text()
    assert "only buying intent from `customer_goals`" in Path("docs/gate1/ROLEPLAY_CONTRACT.md").read_text()
    smoke = Path("eval/results/roleplay_realism_smoke_s04_2026-10-16.json").read_text()
    json.loads(smoke)
    assert "OBJ_VF6_PRICE_ELIGIBILITY" not in smoke
    assert OBJECTION in smoke
