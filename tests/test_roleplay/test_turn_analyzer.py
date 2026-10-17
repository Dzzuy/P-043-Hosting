from pathlib import Path

import pytest

from src.agents.roleplay.prompts.analyzer import TURN_ANALYZER_SYSTEM_PROMPT
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import RoleplayState
from src.agents.roleplay.turn_analyzer import TurnAnalysisError, TurnAnalyzer

SCENARIOS = Path("data/scenarios/scenarios.json")


def test_prompt_resolves_confirmation_only_objections_in_customer_question_context():
    assert "customer's last question" in TURN_ANALYZER_SYSTEM_PROMPT
    assert "resolve_condition only requires confirmation" in TURN_ANALYZER_SYSTEM_PROMPT
    assert 'Short affirmative answers ("được", "dạ có", "đúng rồi ạ")' in TURN_ANALYZER_SYSTEM_PROMPT
    assert "both addressed and resolved" in TURN_ANALYZER_SYSTEM_PROMPT
    assert "Keep all configured upsell requirements" in TURN_ANALYZER_SYSTEM_PROMPT


class StaticAnalysisModel:
    def __init__(self, output):
        self.output = output

    async def analyze(self, advisor_message, scenario, state):
        return self.output


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "advisor_message",
    [
        "Mỗi ngày anh thường chạy khoảng bao nhiêu km?",
        "Một ngày làm việc điển hình xe của anh phải hoạt động nhiều không ạ?",
    ],
)
async def test_semantic_intent_reveals_the_same_fact_for_paraphrases(advisor_message):
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)
    analyzer = TurnAnalyzer(
        StaticAnalysisModel(
            {
                "detected_intents": ["ask_daily_travel_distance"],
                "discovered_fact_ids": ["daily_distance"],
                "current_topic": "daily_usage",
            }
        )
    )

    analysis = await analyzer.analyze(advisor_message, scenario, state)

    assert analysis.discovered_fact_ids == ["daily_distance"]


@pytest.mark.asyncio
async def test_unique_detected_intent_recovers_omitted_daily_distance_fact():
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)
    analyzer = TurnAnalyzer(StaticAnalysisModel({"detected_intents": ["ask_daily_travel_distance"]}))

    analysis = await analyzer.analyze("Anh chạy khoảng bao nhiêu km mỗi ngày ạ?", scenario, state)

    assert analysis.discovered_fact_ids == ["daily_distance"]


@pytest.mark.asyncio
async def test_omitted_fact_is_not_inferred_for_ambiguous_intent():
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    duplicate_intent = scenario.disclosure_rules[0].model_copy(update={"fact_key": "fuel_cost_month"})
    scenario = scenario.model_copy(update={"disclosure_rules": [*scenario.disclosure_rules, duplicate_intent]})
    state = RoleplayState.from_scenario("session-1", scenario)
    analyzer = TurnAnalyzer(StaticAnalysisModel({"detected_intents": ["ask_daily_travel_distance"]}))

    analysis = await analyzer.analyze("Anh chạy khoảng bao nhiêu km mỗi ngày ạ?", scenario, state)

    assert analysis.discovered_fact_ids == []


@pytest.mark.asyncio
async def test_fact_is_not_revealed_without_its_matching_intent():
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)
    analyzer = TurnAnalyzer(
        StaticAnalysisModel(
            {
                "detected_intents": ["ask_budget_or_financing"],
                "discovered_fact_ids": ["daily_distance", "unknown_fact"],
            }
        )
    )

    analysis = await analyzer.analyze("Anh dự tính trả trước bao nhiêu?", scenario, state)

    assert analysis.detected_intents == ["ask_budget_or_financing"]
    assert analysis.discovered_fact_ids == []


@pytest.mark.asyncio
async def test_only_active_addressed_objections_can_be_resolved():
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)
    state.active_objections = ["OBJ_VF5_BATTERY_VS_GAS"]
    analyzer = TurnAnalyzer(
        StaticAnalysisModel(
            {
                "addressed_objection_ids": ["OBJ_VF5_BATTERY_VS_GAS"],
                "resolved_objection_ids": [
                    "OBJ_VF5_BATTERY_VS_GAS",
                    "OBJ_VF5_CHARGING_TIME",
                ],
            }
        )
    )

    analysis = await analyzer.analyze("Em xin phép so sánh theo số km thực tế.", scenario, state)

    assert analysis.resolved_objection_ids == ["OBJ_VF5_BATTERY_VS_GAS"]


@pytest.mark.asyncio
async def test_malformed_structured_output_has_a_domain_specific_error():
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)
    analyzer = TurnAnalyzer(
        StaticAnalysisModel({"factual_claims": [{"text": "Giá hiện tại là...", "category": "invented"}]})
    )

    with pytest.raises(TurnAnalysisError, match="invalid turn analysis"):
        await analyzer.analyze("Giá hiện tại là...", scenario, state)


@pytest.mark.asyncio
async def test_analyzer_keeps_only_claims_exactly_present_in_advisor_turn():
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)
    analyzer = TurnAnalyzer(
        StaticAnalysisModel(
            {
                "factual_claims": [
                    {"text": "VF 5 được bảo hành 7 năm", "category": "warranty"},
                    {"text": "VF 5 miễn phí hoàn toàn", "category": "promotion"},
                ]
            }
        )
    )

    result = await analyzer.analyze("VF 5 được bảo hành 7 năm.", scenario, state)

    assert [claim.text for claim in result.factual_claims] == ["VF 5 được bảo hành 7 năm"]


@pytest.mark.asyncio
async def test_analyzer_preserves_original_casing_for_recorded_claim():
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)
    analyzer = TurnAnalyzer(
        StaticAnalysisModel({"factual_claims": [{"text": "Với VF 5 Plus chạy biển vàng", "category": "policy"}]})
    )

    result = await analyzer.analyze("Dạ, với VF 5 Plus chạy biển vàng có ưu đãi.", scenario, state)

    assert [claim.text for claim in result.factual_claims] == ["với VF 5 Plus chạy biển vàng"]


@pytest.mark.asyncio
@pytest.mark.parametrize("output,expected", [({}, False), ({"off_topic": True}, True), ({"off_topic": False}, False)])
async def test_off_topic_survives_analysis_validation(output, expected):
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)

    analysis = await TurnAnalyzer(StaticAnalysisModel(output)).analyze("xyz xyz", scenario, state)

    assert analysis.off_topic is expected
