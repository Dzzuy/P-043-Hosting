"""Gate 4 judge calibration: fixed transcript validation and offline comparison.

The default command is read-only and never invokes an LLM. Fixed synthetic
transcripts cannot currently be imported through a public RoleplayGraph API.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.models.evaluation import CriterionStatus, CriterionType, ReviewStatus, SessionEvaluationResult

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "eval" / "datasets" / "judge_calibration.json"
SCENARIOS = ROOT / "data" / "scenarios" / "scenarios.json"
CORPUS = ROOT / "data" / "knowledge" / "corpus.json"
FAQ = ROOT / "data" / "knowledge" / "faq.json"
ROLEPLAY_BENCHMARK = ROOT / "eval" / "datasets" / "roleplay_benchmark.json"
EVALUATOR_PROMPT = ROOT / "src" / "agents" / "roleplay" / "prompts" / "evaluator.py"
CRITERIA = tuple(item.value for item in CriterionType)
PURPOSES = {"weak", "adequate", "strong", "factual_error", "partial"}
PENDING = "PENDING_EXPERT_REVIEW"
APPROVED = "APPROVED"


def evaluator_prompt_version() -> str:
    """Read the production prompt constant without importing LangGraph."""
    tree = ast.parse(EVALUATOR_PROMPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "EVALUATOR_PROMPT_VERSION" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("production evaluator prompt version not found")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def obj(value: Any, name: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{name} must be an object")
    return value


def nonempty(value: Any, name: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{name} must be a nonempty string")
    return value


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_knowledge_sources() -> dict[str, dict[str, Any]]:
    """Load both checked-in knowledge collections used by calibration sources."""
    return {item["document_id"]: item for path in (CORPUS, FAQ) for item in read_json(path)}


def check_evidence(items: Any, messages: dict[str, dict[str, str]], name: str) -> None:
    require(isinstance(items, list), f"{name} must be a list")
    for index, raw in enumerate(items):
        item = obj(raw, f"{name}[{index}]")
        message_id = nonempty(item.get("message_id"), f"{name}[{index}].message_id")
        quote = nonempty(item.get("quote"), f"{name}[{index}].quote")
        require(message_id in messages, f"{name}[{index}] references unknown message_id")
        require(quote in messages[message_id]["content"], f"{name}[{index}] quote is not exact")


def validate_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    dataset = obj(dataset, "dataset")
    nonempty(dataset.get("dataset_version"), "dataset_version")
    require(
        dataset.get("rubric_version") in {"sales-rubric-v3", evaluator_prompt_version()}, "unsupported rubric_version"
    )
    require(dataset.get("set_role") == "calibration_only_not_held_out", "dataset must declare calibration-only role")
    require(dataset.get("transcript_origin") == "curated_synthetic", "transcript provenance is unsupported")
    nonempty(dataset.get("transcript_note"), "transcript_note")
    cases = dataset.get("cases")
    require(isinstance(cases, list) and len(cases) >= 5, "dataset must contain at least five cases")
    scenarios = {item["scenario_id"]: item for item in read_json(SCENARIOS)}
    corpus = load_knowledge_sources()
    benchmark = read_json(ROLEPLAY_BENCHMARK)
    benchmark_advisor_sequences = [
        tuple(item.get("advisor_messages", [])) for item in benchmark.get("cases", []) if isinstance(item, dict)
    ]
    seen_cases: set[str] = set()
    seen_messages: set[str] = set()
    seen_transcripts: set[tuple[tuple[str, str], ...]] = set()
    purposes: set[str] = set()
    approved_count = 0
    pending_count = 0
    label_statuses: dict[str, dict[str, str]] = {}
    version_diagnostics = []
    if dataset["rubric_version"] != evaluator_prompt_version():
        version_diagnostics.append(
            "Historical rubric differs from production evaluator; offline comparison uses stored rubric only."
        )
    for case in cases:
        case = obj(case, "case")
        case_id = nonempty(case.get("case_id"), "case_id")
        require(case_id not in seen_cases, f"duplicate case_id: {case_id}")
        seen_cases.add(case_id)
        purpose = nonempty(case.get("purpose"), f"{case_id}.purpose")
        require(purpose in PURPOSES, f"{case_id} has unknown purpose")
        purposes.add(purpose)
        scenario_id = nonempty(case.get("scenario_id"), f"{case_id}.scenario_id")
        require(scenario_id in scenarios, f"{case_id} references unknown scenario")
        nonempty(case.get("scenario_version"), f"{case_id}.scenario_version")
        if case["scenario_version"] != scenarios[scenario_id]["scenario_version"]:
            version_diagnostics.append(
                f"{case_id}: historical scenario version differs from current scenario; runtime replay requires matching versions."
            )
        require(case.get("rubric_version") == dataset["rubric_version"], f"{case_id} rubric version mismatch")
        require(
            case.get("completion_context") == "curated_conversation_ended_no_runtime_state",
            f"{case_id} must not claim a production RoleplayState",
        )
        messages = case.get("messages")
        require(isinstance(messages, list) and len(messages) >= 2, f"{case_id} transcript needs customer and advisor")
        first_role = obj(messages[0], f"{case_id}.messages[0]").get("role")
        require(first_role in {"customer", "advisor"}, f"{case_id} invalid opening role")
        other_role = "advisor" if first_role == "customer" else "customer"
        lookup: dict[str, dict[str, str]] = {}
        for index, raw in enumerate(messages):
            msg = obj(raw, f"{case_id}.messages[{index}]")
            message_id = nonempty(msg.get("message_id"), "message_id")
            require(message_id not in seen_messages, f"duplicate message_id: {message_id}")
            seen_messages.add(message_id)
            require(
                msg.get("role") == (first_role if index % 2 == 0 else other_role),
                f"{case_id} message roles must alternate",
            )
            nonempty(msg.get("content"), f"{message_id}.content")
            lookup[message_id] = msg
        fingerprint = tuple((msg["role"], msg["content"]) for msg in messages)
        require(fingerprint not in seen_transcripts, f"{case_id} duplicates a calibration transcript")
        seen_transcripts.add(fingerprint)
        advisor_sequence = tuple(msg["content"] for msg in messages if msg["role"] == "advisor")
        require(advisor_sequence not in benchmark_advisor_sequences, f"{case_id} copies a T1-T6 advisor trajectory")
        sources = case.get("knowledge_sources")
        require(isinstance(sources, list), f"{case_id}.knowledge_sources must be a list")
        source_ids: set[str] = set()
        for source in sources:
            source = obj(source, f"{case_id}.knowledge_source")
            document_id = nonempty(source.get("document_id"), "document_id")
            require(document_id not in source_ids, f"{case_id} duplicate knowledge source")
            source_ids.add(document_id)
            record = corpus.get(document_id)
            require(
                record is not None and record.get("status") == "active",
                f"{case_id} source is absent or inactive: {document_id}",
            )
            require(source.get("version") == record["version"], f"{case_id} source version mismatch")
            require(
                nonempty(source.get("quote"), "source.quote") in record["content"],
                f"{case_id} source quote is not exact",
            )
        claims = case.get("annotated_claims")
        require(isinstance(claims, list), f"{case_id}.annotated_claims must be a list")
        for claim in claims:
            claim = obj(claim, f"{case_id}.claim")
            message_id = nonempty(claim.get("message_id"), "claim.message_id")
            require(
                message_id in lookup and lookup[message_id]["role"] == "advisor",
                f"{case_id} claim must reference advisor message",
            )
            require(
                nonempty(claim.get("text"), "claim.text").casefold() in lookup[message_id]["content"].casefold(),
                f"{case_id} claim text is not exact",
            )
            require(claim.get("source_document_id") in source_ids, f"{case_id} claim source not declared")
        labels = obj(case.get("expert_labels"), f"{case_id}.expert_labels")
        require(set(labels) == set(CRITERIA), f"{case_id} must provide exactly five criterion labels")
        label_statuses[case_id] = {}
        for criterion in CRITERIA:
            label = obj(labels[criterion], f"{case_id}.{criterion}")
            name = f"{case_id}.{criterion}"
            require(label.get("label_version") == dataset["rubric_version"], f"{name} label version mismatch")
            review = label.get("review_status")
            adjudication = label.get("adjudication_status")
            require(review in {PENDING, APPROVED}, f"{name} invalid review status")
            label_statuses[case_id][criterion] = review
            if review == PENDING:
                require(adjudication == "PENDING", f"{name} pending adjudication mismatch")
                require(
                    label.get("status") is None and label.get("score") is None and label.get("evidence") == [],
                    f"{name} pending label contains a judgement",
                )
                require(
                    all(
                        label.get(key) is None
                        for key in ("rationale", "expected_weakness", "reviewer_id", "reviewed_at", "provenance")
                    ),
                    f"{name} pending label contains review provenance",
                )
                pending_count += 1
                continue
            require(adjudication == APPROVED, f"{name} needs approved adjudication")
            status = label.get("status")
            require(status in {item.value for item in CriterionStatus}, f"{name} invalid criterion status")
            score = label.get("score")
            if status == CriterionStatus.ASSESSED.value:
                require(type(score) is int and 1 <= score <= 3, f"{name} assessed score must be integer 1-3")
                require(bool(label.get("evidence")), f"{name} assessed label needs evidence")
            else:
                require(score is None, f"{name} unassessed score must be null")
            check_evidence(label.get("evidence"), lookup, f"{name}.evidence")
            nonempty(label.get("rationale"), f"{name}.rationale")
            nonempty(label.get("reviewer_id"), f"{name}.reviewer_id")
            nonempty(label.get("provenance"), f"{name}.provenance")
            reviewed_at = nonempty(label.get("reviewed_at"), f"{name}.reviewed_at")
            try:
                datetime.fromisoformat(reviewed_at)
            except ValueError as exc:
                raise ValueError(f"{name}.reviewed_at must be ISO datetime") from exc
            weakness = label.get("expected_weakness")
            require(
                weakness is None or (isinstance(weakness, str) and bool(weakness.strip())),
                f"{name}.expected_weakness invalid",
            )
            if score in {2, 3}:
                roles = {lookup[item["message_id"]]["role"] for item in label["evidence"]}
                require("advisor" in roles, f"{name} score 2-3 needs advisor evidence")
                if score == 3:
                    require("customer" in roles, f"{name} score 3 needs customer evidence")
            approved_count += 1
    require(purposes == PURPOSES, "all five case purposes are required")
    return {
        "mode": "validate",
        "status": "READY_FOR_COMPARISON" if pending_count == 0 else "PENDING_EXPERT_REVIEW",
        "structural_valid": True,
        "dataset_version": dataset["dataset_version"],
        "rubric_version": dataset["rubric_version"],
        "case_ids": [case["case_id"] for case in cases],
        "transcript_count": len(cases),
        "approved_label_count": approved_count,
        "missing_expert_label_count": pending_count,
        "label_statuses": label_statuses,
        "evaluated_transcript_count": 0,
        "comparable_criterion_pair_count": 0,
        "metrics": None,
        "diagnostics": ["Fixed transcript live import is not supported by the public graph contract."]
        + (["Pending expert review: unreviewed labels are excluded from agreement metrics."] if pending_count else [])
        + version_diagnostics,
        "provenance": {"transcripts": dataset["transcript_origin"], "expert_labels": "per-criterion review records"},
    }


def validate_prediction(raw: Any, case: dict[str, Any]) -> SessionEvaluationResult:
    raw = obj(raw, f"{case['case_id']}.evaluation")
    evaluations = raw.get("evaluations")
    require(isinstance(evaluations, list), f"{case['case_id']} prediction evaluations must be a list")
    for item in evaluations:
        item = obj(item, f"{case['case_id']} prediction criterion")
        require(
            type(item.get("score")) is int or item.get("score") is None,
            f"{case['case_id']} prediction score has invalid type",
        )
    try:
        result = SessionEvaluationResult.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{case['case_id']} invalid production evaluation: {exc}") from exc
    require(result.scenario_id == case["scenario_id"], f"{case['case_id']} prediction scenario mismatch")
    require(result.rubric_version == case["rubric_version"], f"{case['case_id']} prediction rubric mismatch")
    require(result.review_status is ReviewStatus.AI_DRAFT, f"{case['case_id']} prediction must be AI draft")
    require(result.passed is None, f"{case['case_id']} prediction passed must be null")
    require(
        {item.criterion.value for item in result.evaluations} == set(CRITERIA),
        f"{case['case_id']} prediction criteria incomplete",
    )
    lookup = {msg["message_id"]: msg for msg in case["messages"]}
    for evaluation in result.evaluations:
        check_evidence(
            [item.model_dump() for item in evaluation.evidence],
            lookup,
            f"{case['case_id']}.{evaluation.criterion}.evidence",
        )
        for check in evaluation.checks:
            check_evidence(
                [item.model_dump() for item in check.evidence],
                lookup,
                f"{case['case_id']}.{evaluation.criterion}.checks",
            )
        if evaluation.status is CriterionStatus.ASSESSED and evaluation.score in {2, 3}:
            roles = {lookup[item.message_id]["role"] for item in evaluation.evidence}
            require("advisor" in roles, "prediction score 2-3 needs advisor evidence")
            if evaluation.score == 3:
                require("customer" in roles, "prediction score 3 needs customer evidence")
    for finding in result.factual_findings:
        message = lookup.get(finding.message_id)
        require(
            message is not None and message["role"] == "advisor",
            f"{case['case_id']} factual finding references non-advisor message",
        )
        require(
            finding.claim.casefold() in message["content"].casefold(),
            f"{case['case_id']} factual finding claim is not exact",
        )
        if finding.status.value in {"supported", "contradicted"}:
            require(
                bool(finding.source_references),
                f"{case['case_id']} supported/contradicted finding needs source references",
            )
    return result


def compare(dataset: dict[str, Any], prediction_file: dict[str, Any]) -> dict[str, Any]:
    """Compare stored production-schema outputs: {provenance, predictions:[{case_id,evaluation}]}."""
    report = validate_dataset(dataset)
    prediction_file = obj(prediction_file, "prediction_file")
    nonempty(prediction_file.get("provenance"), "prediction_file.provenance")
    predictions = prediction_file.get("predictions")
    require(isinstance(predictions, list), "predictions must be a list")
    cases = {case["case_id"]: case for case in dataset["cases"]}
    parsed: dict[str, SessionEvaluationResult] = {}
    for raw in predictions:
        item = obj(raw, "prediction")
        case_id = nonempty(item.get("case_id"), "prediction.case_id")
        require(case_id in cases, f"unknown prediction case_id: {case_id}")
        require(case_id not in parsed, f"duplicate prediction case_id: {case_id}")
        parsed[case_id] = validate_prediction(item.get("evaluation"), cases[case_id])
    missing_predictions = sorted(set(cases) - set(parsed))
    scored_total = 0
    absolute_error_sum = 0
    exact_total = 0
    status_total = 0
    status_match_total = 0
    per_criterion: dict[str, dict[str, Any]] = {}
    for criterion in CRITERIA:
        scored = exact = within_one = status_pairs = status_matches = 0
        for case_id, case in cases.items():
            label = case["expert_labels"][criterion]
            prediction = parsed.get(case_id)
            if label["review_status"] != APPROVED or prediction is None:
                continue
            ai = next(item for item in prediction.evaluations if item.criterion.value == criterion)
            status_pairs += 1
            status_matches += int(ai.status.value == label["status"])
            if label["status"] != CriterionStatus.ASSESSED.value or ai.status is not CriterionStatus.ASSESSED:
                continue
            scored += 1
            difference = abs(ai.score - label["score"])
            absolute_error_sum += difference
            exact += int(difference == 0)
            within_one += int(difference <= 1)
        scored_total += scored
        exact_total += exact
        status_total += status_pairs
        status_match_total += status_matches
        per_criterion[criterion] = {
            "comparable_scored_pairs": scored,
            "exact_matches": exact,
            "exact_agreement_rate": exact / scored if scored else None,
            "within_one_matches": within_one,
            "within_one_rate": within_one / scored if scored else None,
            "excluded_or_incomplete_pairs": len(cases) - scored,
            "applicability_pairs": status_pairs,
            "applicability_matches": status_matches,
            "applicability_agreement_rate": status_matches / status_pairs if status_pairs else None,
        }
    report.update(
        {
            "mode": "compare",
            "status": "EVALUATED"
            if scored_total and not missing_predictions and not report["missing_expert_label_count"]
            else "NOT_EVALUATED"
            if not scored_total
            else "INCOMPLETE",
            "prediction_provenance": prediction_file.get("provenance"),
            "prediction_count": len(parsed),
            "missing_prediction_case_ids": missing_predictions,
            "evaluated_transcript_count": len(parsed),
            "comparable_criterion_pair_count": scored_total,
            "metrics": {
                "mae": absolute_error_sum / scored_total if scored_total else None,
                "absolute_error_sum": absolute_error_sum,
                "mae_denominator": scored_total,
                "pooled_exact_matches": exact_total,
                "pooled_exact_agreement_rate": exact_total / scored_total if scored_total else None,
                "pooled_agreement_denominator": scored_total,
                "applicability_matches": status_match_total,
                "applicability_pairs": status_total,
                "applicability_agreement_rate": status_match_total / status_total if status_total else None,
                "per_criterion": per_criterion,
            },
        }
    )
    if missing_predictions:
        report["diagnostics"].append(f"Missing predictions: {', '.join(missing_predictions)}")
    if report["missing_expert_label_count"]:
        report["diagnostics"].append("Pending expert labels were excluded from all metrics.")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("validate", "compare", "live"), default="validate")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        dataset = read_json(args.dataset)
        if args.mode == "compare":
            require(args.predictions is not None, "--predictions is required for compare")
            report = compare(dataset, read_json(args.predictions))
        elif args.mode == "live":
            report = validate_dataset(dataset)
            report.update(mode="live", status="NOT_EVALUATED", metrics=None)
            report["diagnostics"].append(
                "FIXED_TRANSCRIPT_STATE_IMPORT_UNSUPPORTED: RoleplayGraph has no public fixed-transcript import; "
                "RoleplayEvaluator requires a completed RoleplayState. No model was called."
            )
        else:
            report = validate_dataset(dataset)
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(serialized)
        else:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(serialized)
        return 3 if args.mode == "live" else 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"judge calibration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
