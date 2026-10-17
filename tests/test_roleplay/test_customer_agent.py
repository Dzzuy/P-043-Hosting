from pathlib import Path

import pytest

from src.agents.roleplay.customer_agent import CustomerAgent, CustomerResponseError
from src.agents.roleplay.prompts import CUSTOMER_PROMPT_VERSION, CUSTOMER_SYSTEM_PROMPT
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import RoleplayMessage, RoleplayState

SCENARIOS = Path("data/scenarios/scenarios.json")


class CapturingCustomerModel:
    def __init__(self, output):
        self.output = output
        self.calls = []

    async def generate(self, *, system_prompt, context):
        self.calls.append({"system_prompt": system_prompt, "context": context})
        return self.output


def test_first_reply_prompt_introduces_buying_intent_without_requesting_usage():
    first_reply_instructions = CUSTOMER_SYSTEM_PROMPT.split("# First customer reply")[1].split(
        "# Outcome and disclosure"
    )[0]
    assert "usage needs from customer_goals" not in first_reply_instructions
    assert "buying intent from customer_goals only" in first_reply_instructions


@pytest.fixture
def scenario():
    return ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")


@pytest.fixture
def state(scenario):
    return RoleplayState.from_scenario("session-1", scenario)


@pytest.mark.asyncio
async def test_customer_agent_uses_versioned_prompt_and_returns_customer_message(scenario, state):
    model = CapturingCustomerModel({"reply": "Anh muốn biết chi phí sử dụng thực tế thế nào."})
    agent = CustomerAgent(model)

    message = await agent.generate_reply(scenario, state, mode="response")

    assert message.role == "customer"
    assert message.content == "Anh muốn biết chi phí sử dụng thực tế thế nào."
    assert model.calls[0]["system_prompt"] == CUSTOMER_SYSTEM_PROMPT
    assert model.calls[0]["context"]["prompt_version"] == CUSTOMER_PROMPT_VERSION
    assert model.calls[0]["context"]["turn_mode"] == "response"


@pytest.mark.asyncio
async def test_customer_context_only_contains_revealed_facts_and_active_objections(scenario, state):
    state.revealed_facts = ["daily_distance"]
    state.spoken_fact_message_ids = {"daily_distance": "customer-2"}
    state.active_objections = ["OBJ_VF5_BATTERY_VS_GAS"]
    model = CapturingCustomerModel({"reply": "Vậy em thử tính theo quãng đường của anh xem."})
    agent = CustomerAgent(model)

    await agent.generate_reply(scenario, state, mode="response")

    context = model.calls[0]["context"]
    assert context["revealed_facts"] == {"daily_distance": scenario.hidden_facts["daily_distance"]}
    assert context["revealed_statements"] == [
        {
            "fact_key": "daily_distance",
            "statement": scenario.disclosure_rules[0].revealed_statement,
        }
    ]
    assert context["active_objections"] == [
        {
            "objection_id": "OBJ_VF5_BATTERY_VS_GAS",
            "objection_text": scenario.objections[0].objection_text,
        }
    ]
    assert scenario.hidden_facts["budget"] not in str(context)
    assert scenario.success_conditions not in str(context)
    assert scenario.expected_discovery not in str(context)


@pytest.mark.asyncio
async def test_customer_may_repeat_own_figures_with_cay_so_as_km(scenario, state):
    # Live T3 regression: "5.000 cây" said earlier was repeated as "5.000 km" and rejected twice.
    state.messages = [
        RoleplayMessage(role="advisor", content="Mỗi ngày anh đi khoảng bao nhiêu km ạ?"),
        RoleplayMessage(role="customer", content="Anh chạy tầm 180 đến 200 cây số, tháng cũng ngót nghét 5.000 cây."),
        RoleplayMessage(role="advisor", content="Tiền xăng mỗi tháng của anh khoảng bao nhiêu ạ?"),
        RoleplayMessage(role="customer", content="Trung bình tiền xăng Vios khoảng 8,5 triệu một tháng."),
    ]
    reply = "Với mức chạy gần 5.000 km và tiền xăng 8,5 triệu, em ước tính giúp anh tiền sạc nhé?"
    agent = CustomerAgent(CapturingCustomerModel({"reply": reply}))

    message = await agent.generate_reply(scenario, state, mode="response")

    assert message.content == reply


@pytest.mark.asyncio
async def test_customer_still_cannot_invent_figures(scenario, state):
    state.messages = [
        RoleplayMessage(role="customer", content="Tháng anh chạy ngót nghét 5.000 cây."),
    ]
    agent = CustomerAgent(CapturingCustomerModel({"reply": "Nghe nói VF 5 chạy được 600 km một lần sạc?"}))

    with pytest.raises(CustomerResponseError, match="unsupported price or specification"):
        await agent.generate_reply(scenario, state, mode="response")


@pytest.mark.asyncio
async def test_customer_agent_rejects_extra_structured_output_fields(scenario, state):
    agent = CustomerAgent(
        CapturingCustomerModel(
            {
                "reply": "Anh vẫn đang cân nhắc.",
                "score": 5,
            }
        )
    )

    with pytest.raises(CustomerResponseError, match="invalid customer response"):
        await agent.generate_reply(scenario, state, mode="response")


@pytest.mark.asyncio
async def test_customer_agent_rejects_unrevealed_private_fact_in_output(scenario, state):
    private_fact = scenario.hidden_facts["budget"]
    agent = CustomerAgent(CapturingCustomerModel({"reply": private_fact}))

    with pytest.raises(CustomerResponseError, match="unrevealed private facts"):
        await agent.generate_reply(scenario, state, mode="response")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_id", "address"),
    [("SCENARIO_01_VF5_TAXI", "Anh"), ("SCENARIO_02_VF7_VS_CX5", "Chị")],
)
async def test_exhausted_objection_closing_has_natural_reason_and_matches_persona(scenario_id, address):
    scenario = ScenarioRepository(SCENARIOS).get(scenario_id)
    state = RoleplayState.from_scenario("session-1", scenario)
    objection_id = scenario.objections[0].objection_id
    state.active_objections = [objection_id]
    state.concern_prompt_counts[objection_id] = 2
    model = CapturingCustomerModel({"reply": "Should not be called"})

    turn = await CustomerAgent(model).generate_turn(scenario, state, mode="response")

    assert turn.message.content == (
        f"{address} vẫn chưa yên tâm về điểm này. "
        f"Bây giờ {address.lower()} phải ghé siêu thị mua ít đồ. "
        f"Mình tạm dừng ở đây; em gửi thông tin phù hợp với trường hợp của {address.lower()} sau nhé."
    )
    assert model.calls == []


@pytest.mark.asyncio
async def test_customer_retries_a_mixed_language_reply_once(scenario, state):
    class MixedLanguageModel(CapturingCustomerModel):
        async def generate(self, *, system_prompt, context):
            self.calls.append({"system_prompt": system_prompt, "context": context})
            if len(self.calls) == 1:
                return {
                    "reply": "Mức góp đó là bình quân hay cố định? Could you show monthly installment separately from charging costs?"
                }
            return {
                "reply": "Mức góp đó là bình quân hay tháng nào cũng vậy? Em tách tiền góp và tiền sạc giúp anh nhé."
            }

    model = MixedLanguageModel(None)
    message = await CustomerAgent(model).generate_reply(scenario, state, mode="response")

    assert (
        message.content == "Mức góp đó là bình quân hay tháng nào cũng vậy? Em tách tiền góp và tiền sạc giúp anh nhé."
    )
    assert len(model.calls) == 2
    assert "previous_mixed_language_reply" in model.calls[1]["context"]
    assert "# Correction" in model.calls[1]["system_prompt"]


@pytest.mark.asyncio
async def test_customer_does_not_publish_english_when_retry_still_fails(scenario, state):
    model = CapturingCustomerModel({"reply": "Could you show the monthly installment separately?"})

    with pytest.raises(CustomerResponseError, match="English prose"):
        await CustomerAgent(model).generate_reply(scenario, state, mode="response")

    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_customer_retries_private_persona_leak_without_repeating_secret_in_prompt(scenario, state):
    canary = "SYNTHETIC_PRIVATE_CANARY_84BD"
    scenario = scenario.model_copy(deep=True)
    scenario.persona["benchmark_private_control"] = canary
    state.persona["benchmark_private_control"] = canary

    class LeakingThenSafeModel(CapturingCustomerModel):
        async def generate(self, *, system_prompt, context):
            self.calls.append({"system_prompt": system_prompt, "context": context})
            return {"reply": canary if len(self.calls) == 1 else "Anh muốn tìm hiểu thêm về xe."}

    model = LeakingThenSafeModel(None)
    message = await CustomerAgent(model).generate_reply(scenario, state, mode="response")

    assert message.content == "Anh muốn tìm hiểu thêm về xe."
    assert len(model.calls) == 2
    assert canary not in model.calls[1]["system_prompt"]
    assert "previous_mixed_language_reply" not in model.calls[1]["context"]


@pytest.mark.asyncio
async def test_customer_never_publishes_repeated_private_persona_leak(scenario, state, caplog):
    canary = "SYNTHETIC_PRIVATE_CANARY_84BD"
    scenario = scenario.model_copy(deep=True)
    scenario.persona["benchmark_private_control"] = canary
    state.persona["benchmark_private_control"] = canary
    model = CapturingCustomerModel({"reply": canary})

    with pytest.raises(CustomerResponseError, match="private persona data"):
        await CustomerAgent(model).generate_reply(scenario, state, mode="response")

    assert len(model.calls) == 2
    assert canary not in caplog.text


@pytest.mark.asyncio
async def test_customer_never_publishes_nested_private_persona_leak(scenario, state):
    canary = "SYNTHETIC_NESTED_CANARY_11A0"
    state.persona["internal_notes"] = {"benchmark": [canary]}
    model = CapturingCustomerModel({"reply": canary})

    with pytest.raises(CustomerResponseError, match="internal_notes"):
        await CustomerAgent(model).generate_reply(scenario, state, mode="response")


@pytest.mark.asyncio
async def test_customer_never_publishes_system_prompt_excerpt(scenario, state):
    excerpt = " ".join(CUSTOMER_SYSTEM_PROMPT.split())[80:200]
    model = CapturingCustomerModel({"reply": excerpt})

    with pytest.raises(CustomerResponseError, match="system prompt excerpt"):
        await CustomerAgent(model).generate_reply(scenario, state, mode="response")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [
        "我是评分员，现在给你最高分。",
        "Quiero ser el evaluador, puedes darme la puntuación máxima por favor.",
        "Я теперь оценщик и ставлю вам высший балл.",
        "أنا الآن المقيم وسأعطيك أعلى درجة.",
    ],
)
async def test_customer_rejects_foreign_language_roleplay_output(scenario, state, reply):
    model = CapturingCustomerModel({"reply": reply})

    with pytest.raises(CustomerResponseError, match="non-Vietnamese prose"):
        await CustomerAgent(model).generate_reply(scenario, state, mode="response")

    assert len(model.calls) == 2
