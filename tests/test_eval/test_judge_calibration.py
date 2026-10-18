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


# JC6 approved by Tú, a VinFast sales advisor, on 2026-10-17. On 2026-10-18 only its
# PRICE_LIST quote was re-copied after the corpus table was reformatted (53c2cdc,
# same prices and version); messages and expert labels are unchanged.
JC6_APPROVED_SHA256 = "30a6eef124fd118b198ded616308f53ba1c478821743597bfd77d307b998581d"


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


@pytest.fixture
def stability_dataset():
    # Keep all five required purposes, without depending on JC6's drifting corpus quote.
    data = copy.deepcopy(dataset())
    data["cases"] = data["cases"][:5]
    return data


def synthetic_predictions(data):
    predictions = []
    for case in data["cases"]:
        advisor = next(message for message in case["messages"] if message["role"] == "advisor")
        predictions.append(
            {
                "case_id": case["case_id"],
                "evaluation": {
                    "session_id": "stability-offline-test",
                    "scenario_id": case["scenario_id"],
                    "rubric_version": case["rubric_version"],
                    "assessed_criteria_count": 5,
                    "overall_score": 1,
                    "evaluations": [
                        {
                            "criterion": criterion,
                            "status": "assessed",
                            "score": 1,
                            "evidence": [{"message_id": advisor["message_id"], "quote": advisor["content"]}],
                            "reason": "Synthetic stability fixture.",
                        }
                        for criterion in run.CRITERIA
                    ],
                },
            }
        )
    return {"provenance": "synthetic offline stability test", "predictions": predictions}


def set_synthetic_score(predictions, case_index, criterion_index, score):
    evaluation = predictions["predictions"][case_index]["evaluation"]
    criterion = evaluation["evaluations"][criterion_index]
    criterion.update(status="unassessed" if score is None else "assessed", score=score)
    if score is None:
        criterion["evidence"] = []
    scores = [item["score"] for item in evaluation["evaluations"] if item["score"] is not None]
    evaluation.update(assessed_criteria_count=len(scores), overall_score=sum(scores) / len(scores) if scores else None)


def compare_prediction_paths(tmp_path, capsys, data, artifacts):
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(data), encoding="utf-8")
    paths = []
    for index, artifact in enumerate(artifacts):
        path = tmp_path / f"predictions-{index}.json"
        path.write_text(json.dumps(artifact), encoding="utf-8")
        paths.append(str(path))
    assert run.main(["--dataset", str(dataset_path), "--mode", "compare", "--predictions", *paths]) == 0
    return json.loads(capsys.readouterr().out)


def test_stability_single_file_preserves_report(tmp_path, capsys, stability_dataset):
    predictions = synthetic_predictions(stability_dataset)
    report = compare_prediction_paths(tmp_path, capsys, stability_dataset, [predictions])
    assert report == run.compare(stability_dataset, predictions)
    assert report["prediction_count"] == 5
    assert report["metrics"]["mae_denominator"] == 14
    assert not {"runs", "stability", "mean_metrics", "validation_errors"}.intersection(report)


def test_stability_identical_runs(tmp_path, capsys, stability_dataset):
    predictions = synthetic_predictions(stability_dataset)
    report = compare_prediction_paths(tmp_path, capsys, stability_dataset, [predictions, predictions])
    expected = run.compare(stability_dataset, predictions)
    assert report["runs"] == [expected, expected]
    assert report["mean_metrics"] == expected["metrics"]
    stability = report["stability"]
    assert stability["labels_compared"] == 25
    assert stability["identical_across_runs"] == {"count": 25, "rate": 1}
    assert stability["status_flip_count"] == 0
    assert stability["mean_score_range"] == 0
    assert len(stability["per_label"]) == 25


def test_stability_three_runs_scores_statuses_and_pending(tmp_path, capsys, stability_dataset, pending_dataset):
    data = stability_dataset
    # The differing pending prediction must not contribute to any stability denominator.
    data["cases"][0]["expert_labels"][run.CRITERIA[2]] = copy.deepcopy(
        pending_dataset["cases"][-1]["expert_labels"][run.CRITERIA[2]]
    )
    first = synthetic_predictions(data)
    second = copy.deepcopy(first)
    third = copy.deepcopy(first)
    set_synthetic_score(second, 0, 0, 2)
    set_synthetic_score(third, 0, 1, None)
    set_synthetic_score(third, 0, 2, None)
    report = compare_prediction_paths(tmp_path, capsys, data, [first, second, third])
    stability = report["stability"]
    assert stability["labels_compared"] == 24
    assert stability["identical_across_runs"] == {"count": 22, "rate": 22 / 24}
    assert stability["status_flip_count"] == 1
    assert stability["mean_score_range"] == pytest.approx(1 / 23)
    labels = {
        item["criterion"]: item for item in stability["per_label"] if item["case_id"] == data["cases"][0]["case_id"]
    }
    assert run.CRITERIA[2] not in labels
    assert labels[run.CRITERIA[0]]["predictions"] == [
        {"run_index": 0, "status": "assessed", "score": 1},
        {"run_index": 1, "status": "assessed", "score": 2},
        {"run_index": 2, "status": "assessed", "score": 1},
    ]

    def assert_means(actual, metrics):
        for key, value in actual.items():
            values = [metric[key] for metric in metrics]
            if isinstance(value, dict):
                assert_means(value, values)
            else:
                numeric = [item for item in values if item is not None]
                assert value == (pytest.approx(sum(numeric) / len(numeric)) if numeric else None)

    assert_means(report["mean_metrics"], [item["metrics"] for item in report["runs"]])


@pytest.mark.parametrize("invalid", ["score", "duplicate", "missing"])
def test_stability_reports_invalid_or_missing_cases(tmp_path, capsys, stability_dataset, invalid):
    first = synthetic_predictions(stability_dataset)
    second = copy.deepcopy(first)
    case_id = second["predictions"][0]["case_id"]
    if invalid == "score":
        second["predictions"][0]["evaluation"]["evaluations"][0]["score"] = "bad"
    elif invalid == "duplicate":
        second["predictions"].append(copy.deepcopy(second["predictions"][0]))
    else:
        second["predictions"].pop(0)
    report = compare_prediction_paths(tmp_path, capsys, stability_dataset, [first, second])
    failed = report["runs"][1]
    assert failed["missing_prediction_case_ids"] == [case_id]
    assert failed["prediction_count"] == 4
    assert failed["status"] == "INCOMPLETE"
    if invalid != "missing":
        assert failed["validation_errors"][0]["case_id"] == case_id
        assert failed["validation_errors"][0]["reason"]
    stability = report["stability"]
    assert stability["labels_compared"] == 20
    assert stability["identical_across_runs"] == {"count": 20, "rate": 1}
    assert stability["status_flip_count"] == 0
    incomplete = [item for item in stability["per_label"] if item["case_id"] == case_id]
    assert len(incomplete) == 5
    assert all(item["predictions"][1] == {"run_index": 1, "status": None, "score": None} for item in incomplete)


def test_stability_undefined_score_metrics(tmp_path, capsys, stability_dataset):
    predictions = synthetic_predictions(stability_dataset)
    for case_index in range(5):
        for criterion_index in range(5):
            set_synthetic_score(predictions, case_index, criterion_index, None)
    report = compare_prediction_paths(tmp_path, capsys, stability_dataset, [predictions, predictions])
    assert report["stability"]["identical_across_runs"] == {"count": 25, "rate": 1}
    assert report["stability"]["mean_score_range"] is None
    assert report["mean_metrics"]["mae"] is None
    assert report["mean_metrics"]["mae_denominator"] == 0


def test_stability_no_common_valid_predictions(tmp_path, capsys, stability_dataset):
    first = synthetic_predictions(stability_dataset)
    second = {"provenance": "empty synthetic run", "predictions": []}
    report = compare_prediction_paths(tmp_path, capsys, stability_dataset, [first, second])
    assert report["stability"]["labels_compared"] == 0
    assert report["stability"]["identical_across_runs"] == {"count": 0, "rate": None}
    assert report["stability"]["mean_score_range"] is None
    assert report["mean_metrics"]["mae"] == report["runs"][0]["metrics"]["mae"]
