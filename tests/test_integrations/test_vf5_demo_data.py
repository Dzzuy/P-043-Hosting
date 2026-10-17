"""Guard the VF 5 service-driver demo against stale rental and missing cost inputs."""

import json
from pathlib import Path

from src.agents.copilot.tools import BM25SearchEngine
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.knowledge.chunking import chunk_document
from src.knowledge.schemas import KnowledgeDocument
from src.knowledge.validity import is_document_retrievable


def test_vf5_demo_has_discoverable_customer_cost_inputs():
    scenario = ScenarioRepository().get("SCENARIO_01_VF5_TAXI")
    disclosure_keys = {rule.fact_key for rule in scenario.disclosure_rules}

    assert scenario.scenario_version == "2.5"
    assert {"daily_distance", "fuel_cost_month", "registration_location", "work_schedule"} <= disclosure_keys
    assert "300 triệu" in scenario.hidden_facts["budget"]
    budget_disclosure = next(rule for rule in scenario.disclosure_rules if rule.fact_key == "budget")
    assert "300 triệu" in budget_disclosure.revealed_statement
    assert "tiền thuê pin" not in scenario.hidden_facts["real_concern"]
    assert "8,5 triệu" not in scenario.visible_context


def test_tariff_is_current_and_legacy_rental_is_not_current_sales_evidence():
    raw_documents = json.loads(Path("data/knowledge/corpus.json").read_text(encoding="utf-8"))
    documents = {item["document_id"]: KnowledgeDocument.model_validate(item) for item in raw_documents}

    assert len(documents) == len(raw_documents)
    tariff = documents["CHARGING_TARIFF_VINFAST_20261004"]
    assert "3.858 VNĐ/kWh" in tariff.content
    assert "01/03/2025" in tariff.content
    assert is_document_retrievable(chunk_document(tariff)[0].metadata)
    legacy = documents["POLICY_BATTERY_RENTAL_CONTRACT_20260801"]
    assert not is_document_retrievable(chunk_document(legacy)[0].metadata)


def test_vf5_charging_lookup_finds_tariff_without_legacy_rental():
    hits = BM25SearchEngine().search("Giá sạc công cộng VinFast cho VF 5 bao nhiêu tiền một kWh?", top_k=10)

    assert hits[0]["document_id"] == "CHARGING_TARIFF_VINFAST_20261004"
    assert all(hit["document_id"] != "POLICY_BATTERY_RENTAL_CONTRACT_20260801" for hit in hits)
