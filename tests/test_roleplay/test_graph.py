import asyncio
from copy import deepcopy
from pathlib import Path

import pytest

from src.agents.roleplay.customer_agent import CustomerAgent, CustomerResponseError
from src.agents.roleplay.graph import (
    RoleplayGraph,
    RoleplaySessionConflictError,
    RoleplaySessionNotFoundError,
)
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import EvaluationStatus, RoleplayState, TerminationStatus
from src.agents.roleplay.turn_analyzer import TurnAnalyzer

SCENARIOS = Path("data/scenarios/scenarios.json")


class InMemoryCheckpoint:
    def __init__(self):
        self.states = {}
        self.save_count = 0

    async def save(self, session_id, state):
        self.states[session_id] = deepcopy(state)
        self.save_count += 1

    async def load(self, session_id):
        state = self.states.get(session_id)
        return deepcopy(state) if state is not None else None


class QueueCustomerModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def generate(self, *, system_prompt, context):
        self.calls.append({"system_prompt": system_prompt, "context": context})
        return self.outputs.pop(0)


class QueueAnalysisModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def analyze(self, advisor_message, scenario, state):
        self.calls.append(advisor_message)
        return self.outputs.pop(0)


def build_graph(customer_outputs, analysis_outputs):
    checkpoint = InMemoryCheckpoint()
    customer_model = QueueCustomerModel(customer_outputs)
    analysis_model = QueueAnalysisModel(analysis_outputs)
    graph = RoleplayGraph(
        ScenarioRepository(SCENARIOS),
        TurnAnalyzer(analysis_model),
        CustomerAgent(customer_model),
        checkpoint,
    )
    return graph, checkpoint, customer_model, analysis_model


@pytest.mark.parametrize(
    "scenario_id",
    [
        "SCENARIO_01_VF5_TAXI",
        "SCENARIO_02_VF7_VS_CX5",
        "SCENARIO_03_VF6_APARTMENT",
        "SCENARIO_04_VF6_ECO_PLUS_UPSELL",
    ],
)
@pytest.mark.asyncio
async def test_start_creates_session_and_is_idempotent(scenario_id):
    graph, checkpoint, customer_model, _ = build_graph(
        [{"reply": "Anh đang cân nhắc đổi sang xe điện."}],
        [],
    )

    first = await graph.start("session-1", scenario_id)
    second = await graph.start("session-1", scenario_id)

    assert first == second
    assert first["session_id"] == "session-1"
    assert first["messages"] == []
    assert first["conversation_stage"] == "opening"
    assert first["turn_count"] == 0
    assert first["pending_customer_reply"] is False
    assert customer_model.calls == []
    assert checkpoint.save_count == 1


@pytest.mark.asyncio
async def test_continue_session_updates_state_and_preserves_history():
    graph, checkpoint, _, analysis_model = build_graph(
        [
            {"reply": "Anh đang cân nhắc đổi sang xe điện."},
        ],
        [
            {
                "detected_intents": ["ask_daily_travel_distance"],
                "discovered_fact_ids": ["daily_distance"],
                "current_topic": "daily_usage",
            }
        ],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")

    result = await graph.continue_session(
        "session-1",
        "Mỗi ngày anh thường chạy khoảng bao nhiêu km?",
    )

    saved = RoleplayState.model_validate(await checkpoint.load("session-1"))
    assert result["turn_count"] == 1
    assert [message["role"] for message in result["messages"]] == [
        "advisor",
        "customer",
    ]
    assert saved.revealed_facts == ["daily_distance"]
    assert saved.spoken_fact_message_ids["daily_distance"] == saved.messages[-1].message_id
    assert "180" in saved.messages[-1].content
    assert saved.current_topic == "daily_usage"
    assert analysis_model.calls == ["Mỗi ngày anh thường chạy khoảng bao nhiêu km?"]


@pytest.mark.asyncio
async def test_customer_discloses_mileage_once_before_claiming_it_was_spoken():
    graph, checkpoint, customer_model, _ = build_graph(
        [{"reply": "Anh đang xem VF 5."}, {"reply": "Anh muốn tính tiếp."}],
        [
            {"detected_intents": ["ask_daily_travel_distance"], "discovered_fact_ids": ["daily_distance"]},
            {},
        ],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")
    first = await graph.continue_session("session-1", "Mỗi ngày anh đi bao nhiêu km?")
    assert "180" in first["messages"][-1]["content"]
    assert len(customer_model.calls) == 1  # The model introduces the goal; the application guarantees the disclosure.
    await graph.continue_session("session-1", "Em sẽ tính theo quãng đường đó.")
    assert len(customer_model.calls) == 2
    assert (
        customer_model.calls[-1]["context"]["spoken_fact_message_ids"]["daily_distance"]
        == first["messages"][-1]["message_id"]
    )
    assert RoleplayState.model_validate(await checkpoint.load("session-1")).spoken_fact_message_ids


@pytest.mark.asyncio
async def test_unresolved_cost_concern_gets_two_prompts_then_customer_defers():
    graph, checkpoint, customer_model, _ = build_graph(
        [
            {"reply": "Cộng tiền pin với sạc thì có đáng đổi không em?"},
            {"reply": "Anh muốn biết tổng chi phí thực tế thôi."},
        ],
        [
            {"factual_claims": [{"text": "Giá xe là 500 triệu", "category": "price"}]},
            {},
            {},
        ],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")
    await graph.continue_session("session-1", "Giá xe là 500 triệu")
    await graph.continue_session("session-1", "Dạ em hiểu.")
    final = await graph.continue_session("session-1", "Để em xem thêm.")

    assert [call["context"]["focus_objection_prompt_number"] for call in customer_model.calls] == [1, 2]
    assert len(customer_model.calls) == 2
    assert final["termination_status"] == TerminationStatus.DROPPED_OUT.value
    saved = RoleplayState.model_validate(await checkpoint.load("session-1"))
    assert saved.concern_prompt_counts["OBJ_VF5_BATTERY_VS_GAS"] == 2


@pytest.mark.asyncio
async def test_customer_acceptance_after_follow_up_allows_next_concern():
    cost = "OBJ_VF5_BATTERY_VS_GAS"
    charging = "OBJ_VF5_CHARGING_TIME"
    graph, checkpoint, _, _ = build_graph(
        [
            {"reply": "Tiền pin và sạc có đáng đổi không?", "raised_objection_id": cost},
            {"reply": "Em tính thêm giúp anh nhé.", "raised_objection_id": cost},
            {"reply": "Ừ, em gửi bảng tính cho anh.", "accepted_next_step": True},
            {"reply": "Sạc giữa ca có mất nhiều cuốc không?", "raised_objection_id": charging},
        ],
        [
            {"factual_claims": [{"text": "Giá xe là 500 triệu", "category": "price"}]},
            {},
            {"next_step_attempted": True},
            {"next_step_attempted": True},
        ],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")
    await graph.continue_session("session-1", "Giá xe là 500 triệu")
    await graph.continue_session("session-1", "Em ghi nhận điều này.")
    accepted = await graph.continue_session("session-1", "Em sẽ gửi bảng chi phí theo quãng đường anh chạy.")
    assert accepted["termination_status"] == TerminationStatus.ACTIVE.value
    assert cost in RoleplayState.model_validate(await checkpoint.load("session-1")).resolved_objections
    continued = await graph.continue_session("session-1", "Mình cũng kiểm tra lịch sạc giữa ca nhé?")
    saved = RoleplayState.model_validate(await checkpoint.load("session-1"))
    assert continued["termination_status"] == TerminationStatus.ACTIVE.value
    assert charging in saved.active_objections
    assert saved.concern_prompt_counts.get(charging, 0) == 0


@pytest.mark.asyncio
async def test_selected_turn_limit_is_persisted_and_enforced():
    graph, checkpoint, _, _ = build_graph(
        [{"reply": "Anh muốn tìm hiểu xe."}, *[{"reply": "Vâng."} for _ in range(11)]],
        [{} for _ in range(11)],
    )
    started = await graph.start("session-1", "SCENARIO_01_VF5_TAXI", max_turns=11)
    assert started["max_turns"] == 11
    for turn in range(11):
        final = await graph.continue_session("session-1", f"Tin nhắn {turn}")
    assert final["turn_count"] == 11
    assert final["termination_status"] == TerminationStatus.MAX_TURNS.value
    assert final["messages"][-1]["role"] == "advisor"
    assert RoleplayState.model_validate(await checkpoint.load("session-1")).max_turns == 11


@pytest.mark.asyncio
async def test_session_keeps_five_advisor_turns_of_history():
    customer_outputs = [
        {"reply": "Anh muốn tìm hiểu xe."},
        *[{"reply": f"Phản hồi khách hàng {index}."} for index in range(1, 6)],
    ]
    graph, checkpoint, _, _ = build_graph(
        customer_outputs,
        [{} for _ in range(5)],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")

    for index in range(1, 6):
        await asyncio.wait_for(
            graph.continue_session("session-1", f"Tin nhắn tư vấn {index}"),
            timeout=2,
        )

    saved = RoleplayState.model_validate(await checkpoint.load("session-1"))
    assert saved.turn_count == 5
    assert len(saved.messages) == 10
    assert [message.content for message in saved.messages if message.role == "advisor"] == [
        f"Tin nhắn tư vấn {index}" for index in range(1, 6)
    ]


@pytest.mark.asyncio
async def test_explicit_finish_skips_another_customer_generation():
    graph, checkpoint, customer_model, _ = build_graph(
        [{"reply": "Anh muốn tìm hiểu xe."}],
        [{"advisor_requested_finish": True}],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")

    result = await graph.continue_session("session-1", "Kết thúc bài luyện tập.")

    saved = RoleplayState.model_validate(await checkpoint.load("session-1"))
    assert result["termination_status"] == TerminationStatus.ADVISOR_ENDED.value
    assert saved.termination_status is TerminationStatus.ADVISOR_ENDED
    assert [message.role for message in saved.messages] == ["advisor"]
    assert len(customer_model.calls) == 0


@pytest.mark.asyncio
async def test_finish_freezes_session_without_adding_a_fake_advisor_message():
    graph, checkpoint, customer_model, analysis_model = build_graph(
        [{"reply": "Anh muốn tìm hiểu xe."}],
        [],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")

    first = await graph.finish_session("session-1")
    saves_after_first_finish = checkpoint.save_count
    second = await graph.finish_session("session-1")

    assert first.termination_status is TerminationStatus.ADVISOR_ENDED
    assert first.evaluation_status is EvaluationStatus.PENDING
    assert second == first
    assert checkpoint.save_count == saves_after_first_finish
    assert first.messages == []
    assert len(customer_model.calls) == 0
    with pytest.raises(RoleplaySessionConflictError):
        await graph.continue_session("session-1", "Một tin nhắn sau khi kết thúc")
    assert analysis_model.calls == []


@pytest.mark.asyncio
async def test_finish_accepts_session_already_ended_by_turn_limit():
    graph, checkpoint, _, _ = build_graph(
        [{"reply": "Anh muốn tìm hiểu xe."}],
        [{"advisor_requested_finish": True}],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")
    await graph.continue_session("session-1", "Kết thúc bài luyện tập.")

    finished = await graph.finish_session("session-1")

    assert finished.termination_status is TerminationStatus.ADVISOR_ENDED
    assert finished.evaluation_status is EvaluationStatus.PENDING
    assert len(RoleplayState.model_validate(await checkpoint.load("session-1")).messages) == 1


@pytest.mark.asyncio
async def test_customer_provider_failure_does_not_lose_advisor_turn():
    graph, checkpoint, _, analysis_model = build_graph(
        [
            {"reply": "", "unexpected": "field"},
            {"reply": "Anh muốn biết thêm về xe."},
        ],
        [{}],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")

    with pytest.raises(CustomerResponseError):
        await graph.continue_session("session-1", "Anh cần em tư vấn thêm.")

    saved = RoleplayState.model_validate(await checkpoint.load("session-1"))
    assert saved.turn_count == 1
    assert saved.messages[-1].role == "advisor"
    assert saved.messages[-1].content == "Anh cần em tư vấn thêm."
    assert saved.pending_customer_reply
    with pytest.raises(RoleplaySessionConflictError, match="pending"):
        await graph.continue_session("session-1", "Một câu mới")
    with pytest.raises(RoleplaySessionConflictError, match="pending"):
        await graph.finish_session("session-1")

    recovered = await graph.retry_customer_reply("session-1")
    assert recovered["pending_customer_reply"] is False
    assert recovered["turn_count"] == 1
    assert [message["role"] for message in recovered["messages"]] == ["advisor", "customer"]
    assert analysis_model.calls == ["Anh cần em tư vấn thêm."]
    with pytest.raises(RoleplaySessionConflictError, match="no customer reply"):
        await graph.retry_customer_reply("session-1")


@pytest.mark.asyncio
async def test_unknown_session_has_a_domain_specific_error():
    graph, _, _, _ = build_graph([], [])

    with pytest.raises(RoleplaySessionNotFoundError, match="unknown session_id"):
        await graph.continue_session("missing", "Xin chào")


@pytest.mark.asyncio
async def test_session_id_cannot_be_reused_for_another_scenario():
    graph, _, _, _ = build_graph(
        [{"reply": "Anh muốn tìm hiểu xe."}],
        [],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")

    with pytest.raises(RoleplaySessionConflictError, match="different scenario"):
        await graph.start("session-1", "SCENARIO_02_VF7_VS_CX5")


@pytest.mark.parametrize("discover_vehicle", [False, True])
@pytest.mark.asyncio
async def test_first_customer_reply_introduces_eco_goal_and_preserves_disclosure_rules(discover_vehicle):
    scenario_id = "SCENARIO_04_VF6_ECO_PLUS_UPSELL"
    scenario = ScenarioRepository(SCENARIOS).get(scenario_id)
    analysis = (
        {
            "detected_intents": ["ask_current_vehicle_or_promo"],
            "discovered_fact_ids": ["current_vehicle"],
        }
        if discover_vehicle
        else {}
    )
    introduction = "Chào em, chị đang tìm hiểu chiếc VF 6 Eco."
    graph, checkpoint, customer, _ = build_graph([{"reply": introduction}], [analysis])
    await graph.start("session-1", scenario_id)
    greeting = "Em chào chị, VF 6 đang có ưu đãi tốt ạ."
    if discover_vehicle:
        greeting += " Có ưu đãi 9% Vì Tương Lai Xanh; chị đang đi xe gì ạ?"
    result = await graph.continue_session("session-1", greeting)
    assert result["turn_count"] == 1
    assert [message["role"] for message in result["messages"]] == ["advisor", "customer"]
    assert result["messages"][-1]["content"].startswith(introduction)
    context = customer.calls[0]["context"]
    assert context["replying_to_advisor_opening"] is True
    assert context["customer_goals"] == scenario.customer_goals
    saved = RoleplayState.model_validate(await checkpoint.load("session-1"))
    assert ("current_vehicle" in saved.spoken_fact_message_ids) is discover_vehicle
    assert ("xe máy xăng" in saved.messages[-1].content) is discover_vehicle
    assert scenario.hidden_facts["budget"] not in str(context)
    for key in ("family_usage", "weekend_trips", "priorities"):
        assert scenario.hidden_facts[key] not in str(context)
        assert key not in saved.revealed_facts
        assert key not in saved.spoken_fact_message_ids
    if discover_vehicle:
        rule = next(rule for rule in scenario.disclosure_rules if rule.fact_key == "current_vehicle")
        assert rule.revealed_statement in saved.messages[-1].content
        assert saved.spoken_fact_message_ids["current_vehicle"] == saved.messages[-1].message_id


@pytest.mark.asyncio
async def test_guardrail_insult_uses_report_exit_without_model_calls():
    graph, _, customer, analyzer = build_graph([], [])
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")

    result = await graph.continue_session("session-1", "ngu ngu ngu")

    assert result["termination_status"] == TerminationStatus.ADVISOR_MISCONDUCT.value
    assert result["messages"][-1]["role"] == "customer"
    assert result["messages"][-1]["content"] == (
        "Anh sẽ báo cáo em lên quản lý. Anh không có nhu cầu mua xe ở đây nữa."
    )
    assert customer.calls == []
    assert analyzer.calls == []


@pytest.mark.asyncio
async def test_one_off_topic_turn_reaches_customer_context_and_normal_turn_resets_it():
    graph, _, customer, _ = build_graph(
        [{"reply": "Anh chưa hiểu, anh đang tìm hiểu xe."}, {"reply": "Anh muốn xem VF 5."}],
        [{"off_topic": True}, {}],
    )
    await graph.start("session-1", "SCENARIO_01_VF5_TAXI")

    first = await graph.continue_session("session-1", "xyz xyz xyz")
    state = await graph.get_session_state("session-1")
    assert first["termination_status"] == TerminationStatus.ACTIVE.value
    assert state.consecutive_off_topic_turns == 1
    assert state.customer_prompt_context()["advisor_off_topic"] is True
    assert customer.calls[-1]["context"]["advisor_off_topic"] is True

    second = await graph.continue_session("session-1", "Anh muốn tìm hiểu mẫu xe nào ạ?")
    state = await graph.get_session_state("session-1")
    assert second["termination_status"] == TerminationStatus.ACTIVE.value
    assert state.consecutive_off_topic_turns == 0
    assert customer.calls[-1]["context"]["advisor_off_topic"] is False


@pytest.mark.parametrize(
    "scenario_id,address",
    [("SCENARIO_01_VF5_TAXI", "Anh"), ("SCENARIO_04_VF6_ECO_PLUS_UPSELL", "Chị")],
)
@pytest.mark.asyncio
async def test_repeated_off_topic_ends_with_scripted_reply_without_customer_call(scenario_id, address):
    graph, _, customer, _ = build_graph(
        [{"reply": f"{address} chưa hiểu, mình quay lại chuyện mua xe nhé."}],
        [{"off_topic": True}, {"off_topic": True}],
    )
    await graph.start("session-1", scenario_id)
    await graph.continue_session("session-1", "xyz xyz xyz")

    result = await graph.continue_session("session-1", "qwerty qwerty")

    assert result["termination_status"] == TerminationStatus.DROPPED_OUT.value
    assert result["termination_reason"] == "Customer left after repeated off-topic advisor messages."
    assert result["conversation_stage"] == "finished"
    assert result["pending_customer_reply"] is False
    assert result["messages"][-1]["role"] == "customer"
    assert result["messages"][-1]["content"] == (
        f"{address} thấy em không tập trung tư vấn nên {address.lower()} xin phép dừng ở đây. Chào em."
    )
    assert (await graph.get_session_state("session-1")).consecutive_off_topic_turns == 2
    assert len(customer.calls) == 1
    with pytest.raises(RoleplaySessionConflictError, match="finished"):
        await graph.continue_session("session-1", "Em xin tư vấn tiếp.")
