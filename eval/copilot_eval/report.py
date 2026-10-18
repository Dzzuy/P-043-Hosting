"""Reports persisted outcomes; never executes the agent or changes judge labels."""

import json
import math
from collections import Counter
from pathlib import Path

from eval.copilot_eval.adjudication import reviewed
from eval.copilot_eval.config import matched_outcomes, writable
from eval.copilot_eval.experiment import digest, save
from eval.copilot_eval.operations import operations, rate

METRICS = {
    "custom": ("fact_correctness", "goal_completeness", "citation_support", "scope_unit_date_conditions", "relevance"),
    "ragas": ("faithfulness", "context_recall"),
}
STAGES = ("raw", "candidate", "jev_kept", "packed", "published")


def read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def summarize(cases, rows, reviews):
    matched_outcomes(cases, rows)
    ids = {c["case_id"] for c in cases}
    by_id = {r["case_id"]: r for r in reviews}
    if len(by_id) != len(reviews) or not set(by_id) <= ids:
        raise ValueError("Unknown or duplicate review IDs")
    valid = [c for c in cases if c.get("audit_status") == "valid"]
    metrics = {}
    for kind, fields in METRICS.items():
        for field in fields:
            values = [by_id.get(c["case_id"], {}).get(kind, {}).get(field) for c in valid]
            known = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)]
            metrics[kind + "." + field] = {
                "mean": sum(known) / len(known) if known else None,
                "denominator": len(known),
                "valid_outcomes": len(valid),
                "na_or_error": len(valid) - len(known),
            }
    groups = {}
    for key in ("group", "category", "question_type"):
        groups[key] = {}
        for value in sorted({c.get(key, "unspecified") for c in cases}):
            subset = [c for c in valid if c.get(key, "unspecified") == value]
            outcomes = [by_id.get(c["case_id"], {}).get("custom", {}).get("overall", "unscored") for c in subset]
            groups[key][value] = {
                "case_pass": rate(outcomes.count("pass"), len(subset)),
                "outcomes": dict(Counter(outcomes)),
            }
    case_rows = []
    goals = []
    for case, row in zip(cases, rows, strict=True):
        review = by_id.get(case["case_id"], {})
        custom = review.get("custom", {})
        valid_case = case.get("audit_status") == "valid"
        case_rows.append(
            {
                "case_id": case["case_id"],
                "audit_status": case.get("audit_status", "unaudited"),
                "outcome": custom.get("overall", "unscored") if valid_case else "excluded",
                "diagnosis": custom.get("diagnosis", "unknown"),
                "reason": custom.get("reason"),
                "critical_issues": custom.get("critical_issues", []),
                "issues": custom.get("issues", []),
                "evaluator_error": review.get("evaluator_error"),
                "request_error": row.get("error_type"),
                "elapsed_seconds": row.get("elapsed_seconds"),
                "status": row.get("status"),
            }
        )
        if valid_case and case["expected"]["behavior"] == "answer":
            indices = {g["index"]: g for g in custom.get("goals", [])}
            expected_goals = case["expected"]["required_facts"] or [case["ground_truth"]]
            goals.extend(indices.get(i, {}) for i in range(len(expected_goals)))
    stages = {
        stage: {
            "sufficient": rate(sum(g.get(stage) == "sufficient" for g in goals), len(goals)),
            "statuses": dict(Counter(g.get(stage, "unknown") for g in goals)),
        }
        for stage in STAGES
    }
    losses = {
        a + "_" + b: sum(g.get(a) == "sufficient" and g.get(b) in {"missing", "partial"} for g in goals)
        for a, b in zip(STAGES, STAGES[1:])
    }
    critical = [r for r in case_rows if r["critical_issues"]]
    errors = [
        c["case_id"]
        for c in valid
        if by_id.get(c["case_id"], {}).get("evaluator_error")
        or not by_id.get(c["case_id"], {}).get("custom")
        or any(k.endswith("_error") for k in by_id.get(c["case_id"], {}).get("ragas", {}))
    ]
    pass_rate = rate(sum(r["outcome"] == "pass" for r in case_rows), len(valid))
    gates = {
        "all_outcomes": len(rows) == len(cases),
        "all_scored": not errors,
        "case_pass_90pct": pass_rate["value"] is not None and pass_rate["value"] >= 0.9,
        "no_critical": not critical,
        "source_audit_resolved": len(valid) == len(cases),
    }
    for metric, limit in (
        ("ragas.faithfulness", 0.95),
        ("custom.goal_completeness", 0.9),
        ("custom.citation_support", 0.95),
    ):
        mean = metrics[metric]["mean"]
        gates[metric] = mean is not None and mean >= limit
    return {
        "outcomes": len(rows),
        "expected": len(cases),
        "valid": len(valid),
        "invalid_unresolved": len(cases) - len(valid),
        "case_pass": pass_rate,
        "unresolved_cases": [c["case_id"] for c in cases if c.get("audit_status") != "valid"],
        "metrics": metrics,
        "groups": groups,
        "cases": case_rows,
        "critical": critical,
        "evaluator_errors": errors,
        "diagnoses": dict(Counter(r["diagnosis"] for r in case_rows)),
        "goal_stage_support": stages,
        "stage_losses": losses,
        "operations": operations(rows),
        "gates": gates,
        "limitations": [
            "Serial offline latency does not establish production load or auth/network SLOs.",
            "Stage support uses the union across rounds; source preparation can add dependencies.",
            "Candidate loss includes RRF cap, interleaving and eligibility; it is not exclusively RRF loss.",
            "Unknown metrics and unscored goals remain unknown; N/A is not a perfect score.",
            "Mean gates alone cannot override critical errors or replace independent source review.",
        ],
    }


def generate(run_dir: Path, output: Path | None = None, decisions: Path | None = None):
    run_dir = Path(run_dir).resolve()
    output = writable(output or run_dir / "report")
    manifest = read(run_dir / "manifest.json", {})
    cases = read(run_dir / "cases.json", [])
    rows = read(run_dir / "results.json", [])
    if not cases:
        raise ValueError("No persisted cases")
    raw_path = run_dir / "evaluation/reviews.json"
    reviews = reviewed(raw_path, decisions) if raw_path.exists() else []
    result = summarize(cases, rows, reviews)
    result["raw_judge_case_pass"] = summarize(cases, rows, read(raw_path, []))["case_pass"]
    result["decisions_hash"] = digest(decisions) if decisions else None
    result["manifest"] = manifest
    deep = read(run_dir / "cloud-deep-reconciliation.json", [])
    cloud = {r["case_id"]: r for r in deep}
    trace = [cloud.get(r["case_id"], {}) for r in rows]
    result["trace_complete"] = rate(
        sum(
            bool(
                r.get("present")
                and r.get("closed")
                and r.get("linked")
                and r.get("node_occurrences_complete")
                and r.get("llm_attempts_expected") == r.get("llm_attempts_readback")
            )
            for r in trace
        ),
        len(rows),
    )
    result["cloud_payload_content_complete"] = rate(
        sum(bool(r.get("present") and r.get("truncated_child_payloads") == 0) for r in trace), len(rows)
    )
    result["feedback_readback"] = rate(
        sum(r.get("feedback_read_back", 0) for r in trace), sum(r.get("feedback_expected", 0) for r in trace)
    )
    result["cloud_runtime_usage"] = read(run_dir / "cloud-runtime-usage.json", {})
    result["source_quality_release_blockers"] = read(run_dir / "source-quality-notes.json", [])
    result["gates"]["source_quality_resolved"] = not result["source_quality_release_blockers"]
    for name in ("trace_complete", "cloud_payload_content_complete"):
        result["gates"][name] = result[name]["value"] == 1
    result["gates"]["cloud_answers_match"] = bool(rows) and all(r.get("root_answer_matches") for r in trace)
    result["gates"]["feedback_complete"] = result["feedback_readback"]["value"] == 1
    result["release_candidate_pass"] = all(result["gates"].values())
    save(output / "summary.json", result)
    pass_score = result["case_pass"]
    lines = [
        "# Copilot evaluation",
        "",
        f"Pass: {pass_score['numerator']}/{pass_score['denominator']}; outcomes: {len(rows)}/{len(cases)}.",
        f"Candidate gates: {'PASS' if result['release_candidate_pass'] else 'FAIL'}. Production readiness remains separate.",
        f"LangSmith: {manifest.get('project_url', 'unknown')}",
        "",
        "## Metrics",
        "",
        "| Metric | Mean | Denominator | N/A or error |",
        "|---|---:|---:|---:|",
    ]
    for name, value in result["metrics"].items():
        lines.append(f"| {name} | {value['mean']} | {value['denominator']} | {value['na_or_error']} |")
    lines += ["", "## Cases", "", "| Case | Audit | Outcome | Diagnosis |", "|---|---|---|---|"]
    lines += [f"| {r['case_id']} | {r['audit_status']} | {r['outcome']} | {r['diagnosis']} |" for r in result["cases"]]
    lines += [
        "",
        "## Operational measurements",
        "",
        "```json",
        json.dumps(result["operations"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Limits",
        "",
    ]
    lines += ["- " + text for text in result["limitations"]]
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    save(
        output / "report-integrity.json",
        {
            "generator_hash": digest(Path(__file__)),
            "manifest_hash": digest(run_dir / "manifest.json"),
            "results_hash": digest(run_dir / "results.json"),
            "raw_reviews_hash": digest(raw_path) if raw_path.exists() else None,
            "report_hash": digest(output / "report.md"),
            "summary_hash": digest(output / "summary.json"),
        },
    )
    return result
