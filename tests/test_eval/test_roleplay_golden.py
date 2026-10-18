import copy
import json
from types import SimpleNamespace

import pytest

from eval.roleplay_eval import golden, run


def raw_dataset():
    return json.loads(golden.DATASET.read_text(encoding="utf-8"))


def test_dataset_validates():
    raw = raw_dataset()
    data = golden.load_dataset()
    generic = [c for c in raw["cases"] if c["scenario_id"] == golden.GENERIC]
    assert raw["case_counts"]["total"] == len(raw["cases"])
    assert len(data["cases"]) == len(raw["cases"]) - len(generic) + 4 * len(generic)


def test_generic_case_expands_per_scenario():
    data = golden.load_dataset()
    runs = [c for c in data["cases"] if c.get("expanded_from") == "GEN_OFF_ROLE_REVERSAL"]
    assert {c["scenario_id"] for c in runs} == {s["scenario_id"] for s in json.loads(run.SCENARIOS.read_text())}
    s01 = next(c for c in runs if c["scenario_id"] == "SCENARIO_01_VF5_TAXI")
    s04 = next(c for c in runs if c["scenario_id"] == "SCENARIO_04_VF6_ECO_PLUS_UPSELL")
    assert s01["advisor_messages"][0].startswith("Từ giờ anh") and ". Anh giới thiệu" in s01["advisor_messages"][0]
    assert s04["advisor_messages"][0].startswith("Từ giờ chị")
    assert "budget" in s04["expected"]["revealed_facts_excludes"]
    assert golden.ALL_HIDDEN_FACTS not in json.dumps(runs)


@pytest.mark.parametrize("mutation", ["fact", "quote", "version", "claim", "unknown", "repeated_quote"])
def test_invalid_dataset(tmp_path, mutation):
    data = raw_dataset()
    if mutation == "repeated_quote":
        doc = data["cases"][1]["expected_factual_findings"][0]["supporting_document"]
        doc.update(document_id="PRODUCT_VF7_20260922", version="2026.09.22", quote="7 năm hoặc 160.000km")
    elif mutation == "fact":
        data["cases"][0]["expected"]["revealed_facts_contains"] = ["unknown_fact"]
    elif mutation == "version":
        data["cases"][0]["scenario_version"] = "invalid"
    elif mutation == "unknown":
        data["cases"][0]["expected"]["mystery_contains"] = ["x"]
    else:
        finding = data["cases"][1]["expected_factual_findings"][0]
        if mutation == "quote":
            finding["supporting_document"]["quote"] = "fabricated quote"
        else:
            finding["claim_text_contains"] = "absent claim"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        golden.load_dataset(path)


def test_aggregation():
    cases = [
        {
            "pass_at_k": True,
            "pass_hat_k": False,
            "runs": [
                {"assertions": [run.assertion("a", True, True)]},
                {"assertions": [run.assertion("a", True, False)]},
            ],
        },
        {
            "pass_at_k": True,
            "pass_hat_k": True,
            "runs": [
                {"assertions": [run.assertion("a", True, True)]},
                {"assertions": [run.assertion("a", True, True), run.assertion("b", True, available=False)]},
            ],
        },
    ]
    assert golden.aggregate(cases) == {
        "case_count": 2,
        "pass_at_k_rate": 1,
        "pass_hat_k_rate": 0.5,
        "assertion_count": 5,
        "assertion_pass_rate": 0.6,
    }
    assert golden.aggregate([])["pass_at_k_rate"] is None


@pytest.mark.parametrize("terminal", ["dropped_out", "advisor_misconduct"])
@pytest.mark.parametrize("conflict", [False, True])
def test_early_termination(monkeypatch, terminal, conflict):
    import asyncio

    import src.integrations.practice_runtime as runtime

    class ConflictError(Exception):
        pass

    class Graph:
        calls = 0

        def __init__(self, *args):
            self.state = {"turn_count": 0, "termination_status": "active"}

        async def start(self, *args):
            pass

        async def get_session_state(self, *args):
            return SimpleNamespace(model_dump=lambda **kwargs: dict(self.state))

        async def continue_session(self, *args):
            Graph.calls += 1
            self.state = {"turn_count": 1, "termination_status": terminal}
            if conflict:
                raise ConflictError("finished")

    monkeypatch.setattr(run, "_runtime", lambda: (None, lambda x: x, Graph, ConflictError, lambda x: x, lambda x: x))
    monkeypatch.setattr(runtime, "SharedLLMCustomerModel", lambda: None)
    monkeypatch.setattr(runtime, "SharedLLMTurnAnalysisModel", lambda: None)
    case = copy.deepcopy(golden.load_dataset()["cases"][0])
    case["advisor_messages"] = ["first", "must not send"]
    case["expected"] = {"turn_count": 1, "termination_status": terminal}
    result = asyncio.run(run.run_live_standard(case, "fresh", stop_on_termination=True))
    assert Graph.calls == 1
    assert result["case_result"] == "PASS"
    assert result["final_state"]["termination_status"] == terminal


def fake_result(messages=(), revealed=(), assertions=None):
    return {
        "case_result": "PASS",
        "execution_status": "COMPLETE",
        "assertions": assertions or [run.assertion("a", True, True)],
        "final_state": {
            "messages": [{"message_id": f"m{i}", "role": "customer", "content": m} for i, m in enumerate(messages)],
            "revealed_facts": list(revealed),
        },
    }


SCENARIOS = {x["scenario_id"]: x for x in json.loads(run.SCENARIOS.read_text(encoding="utf-8"))}


def test_postprocess_demotes_category_and_flags_leaks():
    case = next(c for c in golden.load_dataset()["cases"] if c["case_id"] == "S01_EDGE_FALSE_RANGE")
    scenario = SCENARIOS[case["scenario_id"]]
    budget = next(r["revealed_statement"] for r in scenario["disclosure_rules"] if r["fact_key"] == "budget")
    result = fake_result(
        messages=[f"Dạ. {budget}"],
        assertions=[run.assertion("factual.0.category", "product", "battery_charging"), run.assertion("a", True, True)],
    )
    out = golden.postprocess(case, result, scenario)
    assert [a["assertion_id"] for a in out["category_diagnostics"]] == ["factual.0.category"]
    leak = next(a for a in out["assertions"] if a["assertion_id"] == "transcript.no_unrevealed_statement")
    assert leak["status"] == "FAIL" and leak["evidence"]["leaks"][0]["fact_key"] == "budget"
    assert out["case_result"] == "FAIL"
    clean = golden.postprocess(
        case,
        fake_result(messages=["Dạ."], assertions=[run.assertion("factual.0.category", "product", "battery_charging")]),
        scenario,
    )
    assert clean["case_result"] == "PASS"


def test_role_cases_need_human_review():
    case = next(c for c in golden.load_dataset()["cases"] if c["case_id"].startswith("GEN_OFF_ROLE_REVERSAL@"))
    out = golden.postprocess(case, fake_result(messages=["Anh vẫn muốn hỏi về xe."]), SCENARIOS[case["scenario_id"]])
    review = next(a for a in out["assertions"] if a["assertion_id"] == "semantic_role_consistency")
    assert review["status"] == "NOT_EVALUATED" and review["evidence"]["customer_replies"][0]["quote"]
    assert out["case_result"] == "NEEDS_REVIEW"


def test_review_selection_and_output(tmp_path, monkeypatch):
    async def fake(case, run_id, **kwargs):
        assert case["review"]["status"] != "REJECTED"
        return fake_result()

    monkeypatch.setattr(run, "run_live_standard", fake)
    data = raw_dataset()
    data["cases"] = [
        c for c in data["cases"] if c["case_id"] in ("S01_ON_DISCOVERY_WORK_SCHEDULE", "S03_ON_DISCOVERY_DISTANCE")
    ]
    data["cases"][0]["review"].update(status="PENDING_EXPERT_REVIEW", reviewer_id=None, reviewed_at=None)
    data["case_counts"] = {"total": 2, "on_topic": 2, "off_topic": 0, "edge": 0}
    dataset = tmp_path / "golden.json"
    dataset.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "report.json"
    assert (
        golden.main(
            [
                "--dataset",
                str(dataset),
                "--mode",
                "live",
                "--include-draft",
                "--repeats",
                "2",
                "--case-id",
                "S01_ON_DISCOVERY_WORK_SCHEDULE",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text())
    assert report["cases"][0]["draft"]
    assert len(report["cases"][0]["runs"]) == 2
    assert report["metrics"]["overall"]["case_count"] == 0
    assert report["draft_metrics"]["overall"]["pass_hat_k_rate"] == 1
    assert output.with_suffix(".md").exists()
    assert golden.main(["--dataset", str(dataset), "--output", str(output)]) == 2
    other = tmp_path / "approved.json"
    assert golden.main(["--dataset", str(dataset), "--mode", "live", "--output", str(other)]) == 0
    assert [c["case_id"] for c in json.loads(other.read_text())["cases"]] == ["S03_ON_DISCOVERY_DISTANCE"]
