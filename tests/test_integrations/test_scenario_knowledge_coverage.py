from datetime import date
from pathlib import Path

from scripts.check_scenario_knowledge import check_coverage
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.integrations.practice_policy import OfflinePolicyRetriever
from src.knowledge.validity import today_in_vietnam


def offline_retriever():
    return OfflinePolicyRetriever([Path("data/knowledge/corpus.json"), Path("data/knowledge/faq.json")])


def test_expected_policies_have_valid_corpus_sources():
    rows, missing = check_coverage(ScenarioRepository(), offline_retriever(), today_in_vietnam())
    assert missing == 0, "\n".join(rows)


def test_expired_promotion_fails_coverage():
    rows, missing = check_coverage(ScenarioRepository(), offline_retriever(), date(2026, 12, 20))
    assert missing > 0
    assert any("vtlx2" in row and "not_applicable" in row for row in rows)
    zero_down_rows = [row for row in rows if "zero_down" in row]
    assert zero_down_rows
    assert all("✅ resolved" in row and "2026-12-31" in row for row in zero_down_rows)


def test_missing_expected_policy_fails_coverage():
    retriever = offline_retriever()
    retriever.chunks = [chunk for chunk in retriever.chunks if chunk.metadata.document_type != "promotion"]
    rows, missing = check_coverage(ScenarioRepository(), retriever, date(2026, 10, 17))
    assert missing > 0
    assert any("vtlx2" in row and "❌ missing" in row for row in rows)


def test_simulated_expiry_fails_coverage():
    retriever = offline_retriever()
    for chunk in retriever.chunks:
        if chunk.metadata.document_type == "promotion":
            chunk.metadata.expiry_date = date(2026, 10, 16)
    rows, missing = check_coverage(ScenarioRepository(), retriever, date(2026, 10, 17))
    assert missing > 0
    assert any("vtlx2" in row and "only expired sources" in row for row in rows)
