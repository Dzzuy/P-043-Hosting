import json
from pathlib import Path

import pytest

from src.agents.roleplay.scenario_loader import (
    ScenarioDatasetError,
    ScenarioNotFoundError,
    ScenarioRepository,
    _voice_gender_from_name,
)

SCENARIOS = Path("data/scenarios/scenarios.json")


def test_repository_default_path_loads_project_scenarios():
    repository = ScenarioRepository()

    assert len(repository.list_public()) == 4


def test_repository_loads_scenarios_and_returns_defensive_copies():
    repository = ScenarioRepository(SCENARIOS)

    first = repository.get("SCENARIO_01_VF5_TAXI")
    first.persona["name"] = "changed"

    assert repository.get("SCENARIO_01_VF5_TAXI").persona["name"] == "Anh Nam"


def test_public_summaries_do_not_expose_private_scenario_fields():
    repository = ScenarioRepository(SCENARIOS)

    summaries = [summary.model_dump() for summary in repository.list_public()]

    assert len(summaries) == 4
    private_fields = {
        "persona",
        "hidden_facts",
        "buyer_intent",
        "customer_goals",
        "disclosure_rules",
        "objections",
        "success_conditions",
        "acceptable_outcomes",
        "upsell_benefits",
        "upsell_rule",
        "policy_expectations",
    }
    assert all(private_fields.isdisjoint(summary) for summary in summaries)
    assert {summary["scenario_id"]: summary["voice_gender"] for summary in summaries} == {
        "SCENARIO_01_VF5_TAXI": "male",
        "SCENARIO_02_VF7_VS_CX5": "female",
        "SCENARIO_03_VF6_APARTMENT": "male",
        "SCENARIO_04_VF6_ECO_PLUS_UPSELL": "female",
    }


def test_voice_gender_is_not_guessed_for_ambiguous_customer_title():
    assert _voice_gender_from_name("Bác Minh") is None


def test_unknown_scenario_has_a_domain_specific_error():
    repository = ScenarioRepository(SCENARIOS)

    with pytest.raises(ScenarioNotFoundError, match="unknown scenario_id"):
        repository.get("SCENARIO_DOES_NOT_EXIST")


def test_duplicate_scenario_identifiers_are_rejected(tmp_path):
    raw_scenario = json.loads(SCENARIOS.read_text(encoding="utf-8"))[0]
    dataset_path = tmp_path / "scenarios.json"
    dataset_path.write_text(json.dumps([raw_scenario, raw_scenario]), encoding="utf-8")

    with pytest.raises(ScenarioDatasetError, match="duplicate scenario_id"):
        ScenarioRepository(dataset_path)


def test_non_array_dataset_is_rejected(tmp_path):
    dataset_path = tmp_path / "scenarios.json"
    dataset_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ScenarioDatasetError, match="must be a JSON array"):
        ScenarioRepository(dataset_path)


def test_new_scenario_exposes_internal_contracts_only_on_private_lookup():
    repository = ScenarioRepository(SCENARIOS)
    scenario = repository.get("SCENARIO_04_VF6_ECO_PLUS_UPSELL")
    assert scenario.scenario_version == "1.4"
    assert [policy.policy_id for policy in scenario.policy_expectations] == [
        "vtlx2",
        "vf6_price",
        "charging",
        "warranty",
        "zero_down",
        "deposit",
    ]
    price = scenario.policy_expectations[1]
    assert price.level == "expected"
    assert price.topic == "Giá niêm yết VF 6 Eco và Plus theo bảng giá hiện hành"
    assert price.lookup.model_dump() == {
        "query": "VF 6",
        "document_type": "price_list",
        "policy_type": None,
        "product_model": "VF 6",
    }
    assert price.requires_eligibility_check is False
    assert [objection.objection_id for objection in scenario.objections] == [
        "OBJ_VF6_PROMO_ELIGIBILITY",
        "OBJ_VF6_PLUS_WORTH",
    ]
    eligibility = scenario.objections[0]
    assert eligibility.objection_text == (
        "Giá vẫn hơi cao so với dự tính của chị. Ưu đãi đó chị có được áp dụng không em?"
    )
    assert "Dạ được ạ" in eligibility.resolve_condition
    assert "KHÔNG bắt buộc" in eligibility.resolve_condition
    assert "policy_accuracy" in eligibility.resolve_condition
    assert scenario.upsell_rule.objection_id == "OBJ_VF6_PLUS_WORTH"
    assert len(scenario.upsell_benefits) == 4
    assert scenario.acceptable_outcomes[0].outcome_id == "close_eco"
    assert scenario.acceptable_outcomes[1].preferred is True
    assert len(scenario.disclosure_rules) == 8
    assert "real_concern" not in {rule.fact_key for rule in scenario.disclosure_rules}
    summary = next(item for item in repository.list_public() if item.scenario_id == scenario.scenario_id)
    assert summary.outcome_labels == ["Chốt VF 6 Eco", "Upsell VF 6 Plus"]
    public = summary.model_dump_json()
    for private_value in [
        *scenario.hidden_facts.values(),
        *[benefit.benefit_id for benefit in scenario.upsell_benefits],
        *[outcome.product for outcome in scenario.acceptable_outcomes],
        *[objection.objection_id for objection in scenario.objections],
    ]:
        assert private_value not in public
