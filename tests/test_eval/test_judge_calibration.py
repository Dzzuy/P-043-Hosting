"""Approved calibration data and synthetic pending labels retain distinct semantics."""

import copy
import hashlib
import json

import pytest

from eval.judge_eval import adapter, run

JC6_CASE_ID = "JC6_VF6_PLUS_UPSELL"


def dataset():
    return run.read_json(run.DEFAULT_DATASET)


@pytest.fixture
def pending_dataset():
    data = copy.deepcopy(dataset())
    for label in data["cases"][5]["expert_labels"].values():
        label.update(
            review_status=run.PENDING,
            adjudication_status="PENDING",
            evidence=[],
            **dict.fromkeys(
                [
                    "status",
                    "score",
                    "rationale",
                    "expected_weakness",
                    "reviewer_id",
                    "reviewed_at",
                    "provenance",
                ]
            ),
        )
    return data


@pytest.fixture
def pending_dataset_path(tmp_path, pending_dataset):
    path = tmp_path / "pending_calibration.json"
    path.write_text(json.dumps(pending_dataset, ensure_ascii=False), encoding="utf-8")
    return path


def test_real_dataset_has_six_expert_approved_transcripts():
    data = dataset()
    report = run.validate_dataset(data)
    assert report["transcript_count"] == 6
    assert report["approved_label_count"] == 30
    assert report["missing_expert_label_count"] == 0
    assert report["status"] == "READY_FOR_COMPARISON"
    assert data["cases"][5]["case_id"] == JC6_CASE_ID
    assert all(
        label["review_status"] == "APPROVED" and label["reviewer_id"] == "tú-vinfast-sales-advisor"
        for label in data["cases"][5]["expert_labels"].values()
    )


def test_pending_case_validates_without_expert_judgements(pending_dataset):
    data = pending_dataset
    report = run.validate_dataset(data)
    assert report["transcript_count"] == 6
    assert report["approved_label_count"] == 25
    assert report["missing_expert_label_count"] == 5
    assert report["status"] == run.PENDING
    assert all(
        label["review_status"] == run.PENDING and label["score"] is None
        for label in data["cases"][-1]["expert_labels"].values()
    )


# SHA-256 of the five expert-approved cases (JC1–JC5) as approved on develop.
APPROVED_CASES_SHA256 = "347b5174196d05cafe2ca35b09d74c505b820a6c9ea5deb6f831226c32e42885"


def test_expert_approved_cases_are_unchanged():
    approved = dataset()["cases"][:5]
    digest = hashlib.sha256(json.dumps(approved, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert digest == APPROVED_CASES_SHA256
    assert dataset()["dataset_version"] == "gate4-judge-calibration-v1"


# JC6 approved by Tú, a VinFast sales advisor, on 2026-10-17.
JC6_APPROVED_SHA256 = "dcb6feb2ce43a4f1e193d8d3a4496308f19f0be3361f560b77ce4590924ed104"


def test_expert_approved_jc6_is_unchanged():
    approved = [dataset()["cases"][5]]
    digest = hashlib.sha256(json.dumps(approved, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert digest == JC6_APPROVED_SHA256


def test_pending_prediction_is_excluded_from_all_agreement_metrics(pending_dataset):
    data = pending_dataset
    predictions = run.read_json(run.ROOT / "eval/reports/judge_calibration_predictions_2026-10-09.json")
    before = run.compare(data, predictions)
    pending = data["cases"][-1]
    prediction = {
        "case_id": pending["case_id"],
        "evaluation": {
            "session_id": "pending-offline-test",
            "scenario_id": pending["scenario_id"],
            "rubric_version": pending["rubric_version"],
            "assessed_criteria_count": 0,
            "overall_score": None,
            "evaluations": [
                {
                    "criterion": criterion,
                    "status": "unassessed",
                    "score": None,
                    "evidence": [],
                    "reason": "Offline exclusion fixture.",
                }
                for criterion in run.CRITERIA
            ],
        },
    }
    predictions["predictions"].append(prediction)
    after = run.compare(data, predictions)
    assert after["metrics"] == before["metrics"]
    assert after["evaluated_transcript_count"] == before["evaluated_transcript_count"] + 1
    assert any("Pending expert labels" in message for message in after["diagnostics"])


@pytest.mark.parametrize(
    "field,value", [("score", 3), ("reviewer_id", "invented"), ("adjudication_status", "APPROVED")]
)
def test_pending_labels_reject_judgement_or_provenance(field, value, pending_dataset):
    data = pending_dataset
    data["cases"][-1]["expert_labels"][run.CRITERIA[0]][field] = value
    with pytest.raises(ValueError, match="pending"):
        run.validate_dataset(data)


def test_pending_case_adapter_preflight_offline(monkeypatch, capsys, pending_dataset_path):
    def no_llm(*args, **kwargs):
        raise AssertionError("preflight must not construct an LLM")

    monkeypatch.setattr(adapter, "get_llm", no_llm)
    assert adapter.main(["--dataset", str(pending_dataset_path), "--preflight", "--case-id", JC6_CASE_ID]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["case_ids"] == [JC6_CASE_ID]
    assert report["pending_expert_review_case_ids"] == [JC6_CASE_ID]
    assert report["status"] == "OFFLINE_VALIDATED_RUBRIC_MISMATCH"
    assert report["annotated_claims"] == 11
    assert report["knowledge_sources"] == 3


def test_offline_validate_and_live_dry_path(capsys, pending_dataset_path):
    assert run.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "READY_FOR_COMPARISON"
    assert run.main(["--dataset", str(pending_dataset_path)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == run.PENDING
    assert run.main(["--dataset", str(pending_dataset_path), "--mode", "live"]) == 3
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "NOT_EVALUATED"
    assert report["missing_expert_label_count"] == 5


def test_historical_versions_are_reported_without_relabelling():
    report = run.validate_dataset(dataset())
    assert any("Historical rubric" in message for message in report["diagnostics"])
    assert sum("historical scenario version" in message for message in report["diagnostics"]) == 5
