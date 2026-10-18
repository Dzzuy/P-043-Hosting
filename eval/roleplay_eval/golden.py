"""Offline validation and repeated live evaluation of the reviewed golden set.

Usage: python -m eval.roleplay_eval.golden --mode validate
Draft observations are reported separately and never count as golden metrics.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import run

DATASET = run.ROOT / "eval/datasets/roleplay_golden.json"
CORPUS = run.ROOT / "data/knowledge/corpus.json"
TYPES = {"on_topic", "off_topic", "edge"}
REVIEWS = {"PENDING_EXPERT_REVIEW", "APPROVED", "REJECTED"}
GENERIC = "ALL"
ALL_HIDDEN_FACTS = "ALL_HIDDEN_FACTS"
# Role fidelity is judged by a person reading the replies, never by another model.
SEMANTIC_REVIEW_CATEGORIES = {"prompt_injection", "role_reversal"}
# Mirrors the production state contract without importing models/providers offline.
LIST_FIELDS = {
    "revealed_facts",
    "advisor_discoveries",
    "active_objections",
    "resolved_objections",
    "unresolved_objections",
    "policy_mentions",
    "linked_benefits",
    "messages",
    "factual_claims",
}
TERMINATIONS = run.TERMINATIONS | {"advisor_misconduct"}
LINKS = {
    "spoken_fact_message_ids_contains_customer_message_for",
    "spoken_concern_message_ids_contains_customer_message_for",
}


def strict_object(value: Any, path: str, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    obj = run._object(value, path, required)
    run._require(not set(obj) - required - (optional or set()), f"{path}: unknown fields")
    return obj


def validate_expected(value: Any, case: dict[str, Any], scenario: dict[str, Any], *, checkpoint: bool = False) -> None:
    allowed = (
        {"turn_count", "termination_status"}
        | LINKS
        | {f"{field}_{suffix}" for field in LIST_FIELDS for suffix in ("contains", "excludes")}
    )
    obj = strict_object(value, case["case_id"], {"turn_count"} if checkpoint else set(), allowed)
    run._require(bool(obj), "expected must contain assertions")
    for key, item in obj.items():
        if key == "turn_count":
            run._require(type(item) is int and 0 <= item <= len(case["advisor_messages"]), "invalid turn_count")
        elif key == "termination_status":
            run._require(isinstance(item, str) and item in TERMINATIONS, "invalid termination_status")
        else:
            run._require(isinstance(item, list) and bool(item), f"{key}: expected nonempty list")
            field = key.removesuffix("_contains").removesuffix("_excludes")
            if key.startswith("spoken_fact") or field in {"revealed_facts", "advisor_discoveries"}:
                identifiers = set(scenario["hidden_facts"])
            elif key.startswith("spoken_concern") or field.endswith("objections"):
                identifiers = {x["objection_id"] for x in scenario["objections"]}
            else:
                identifiers = None
            for identifier in item:
                if identifiers is not None:
                    run._nonempty(identifier, key)
                    run._require(identifier in identifiers, f"{key}: unknown scenario fact/objection {identifier}")


def expand_generic(case: dict[str, Any], scenarios: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand a scenario-independent case (scenario_id "ALL") into one case per scenario."""
    if case.get("scenario_id") != GENERIC:
        return [case]
    run._require(case.get("scenario_version") == GENERIC, "generic case must use scenario_version ALL")
    expanded = []
    for scenario_id, scenario in scenarios.items():
        address = scenario["persona"]["name"].split()[0].casefold()
        text = json.dumps(case, ensure_ascii=False)
        item = json.loads(text.replace("{Address}", address.capitalize()).replace("{address}", address))
        item.update(
            case_id=f"{case['case_id']}@{scenario_id}",
            scenario_id=scenario_id,
            scenario_version=scenario["scenario_version"],
            expanded_from=case["case_id"],
        )
        for block in [item["expected"], *item.get("expected_turns", [])]:
            for key, value in block.items():
                if value == [ALL_HIDDEN_FACTS]:
                    block[key] = sorted(scenario["hidden_facts"])
        expanded.append(item)
    return expanded


def load_dataset(
    path: Path = DATASET, scenario_path: Path = run.SCENARIOS, corpus_path: Path = CORPUS
) -> dict[str, Any]:
    data = strict_object(
        json.loads(path.read_text(encoding="utf-8")),
        "dataset",
        {"dataset_version", "description", "review_protocol", "case_counts", "cases"},
    )
    for key in ("dataset_version", "description", "review_protocol"):
        run._nonempty(data[key], key)
    scenarios = {x["scenario_id"]: x for x in json.loads(scenario_path.read_text(encoding="utf-8"))}
    corpus = {(x["document_id"], x["version"]): x for x in json.loads(corpus_path.read_text(encoding="utf-8"))}
    run._require(isinstance(data["cases"], list) and bool(data["cases"]), "cases must be nonempty list")
    authored = data["cases"]
    run._require(all(isinstance(raw, dict) for raw in authored), "case must be an object")
    data["cases"] = [item for raw in authored for item in expand_generic(raw, scenarios)]
    seen: set[str] = set()
    for raw in data["cases"]:
        case = strict_object(
            raw,
            "case",
            {
                "case_id",
                "type",
                "category",
                "scenario_id",
                "scenario_version",
                "advisor_messages",
                "expected",
                "rationale",
                "review",
            },
            {"expected_turns", "expected_factual_findings", "expanded_from"},
        )
        for key in ("case_id", "type", "category", "scenario_id", "scenario_version", "rationale"):
            run._nonempty(case[key], key)
        run._require(case["case_id"] not in seen, "duplicate case_id")
        seen.add(case["case_id"])
        run._require(case["type"] in TYPES, "invalid case type")
        scenario = scenarios.get(case["scenario_id"])
        run._require(
            scenario is not None and scenario["scenario_version"] == case["scenario_version"],
            "scenario version/id mismatch",
        )
        messages = case["advisor_messages"]
        run._require(isinstance(messages, list) and bool(messages), "advisor_messages must be nonempty list")
        for message in messages:
            run._nonempty(message, "advisor_message")
        validate_expected(case["expected"], case, scenario)
        points = case.get("expected_turns", [])
        run._require(isinstance(points, list), "expected_turns must be list")
        for point in points:
            validate_expected(point, case, scenario, checkpoint=True)
        run._require(len({p["turn_count"] for p in points}) == len(points), "duplicate checkpoint")
        review = strict_object(
            case["review"], "review", {"status", "drafted_by", "reviewer_id", "reviewed_at", "notes"}
        )
        run._require(isinstance(review["status"], str) and review["status"] in REVIEWS, "invalid review status")
        run._nonempty(review["drafted_by"], "drafted_by")
        for key in ("reviewer_id", "reviewed_at", "notes"):
            run._require(review[key] is None or isinstance(review[key], str), f"review.{key} invalid")
        if review["status"] != "PENDING_EXPERT_REVIEW":
            run._nonempty(review["reviewer_id"], "reviewer_id")
            run._nonempty(review["reviewed_at"], "reviewed_at")
            try:
                datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("invalid reviewed_at timestamp") from exc
        findings = case.get("expected_factual_findings", [])
        run._require(isinstance(findings, list), "expected_factual_findings must be list")
        for finding in findings:
            strict_object(
                finding,
                "finding",
                {"advisor_turn_number", "claim_text_contains", "category", "status"},
                {"supporting_document", "contradicting_document"},
            )
            turn = finding["advisor_turn_number"]
            run._require(type(turn) is int and 1 <= turn <= len(messages), "invalid factual turn")
            run._nonempty(finding["claim_text_contains"], "claim_text_contains")
            run._require(finding["claim_text_contains"] in messages[turn - 1], "claim absent from advisor message")
            run._require(
                isinstance(finding["category"], str)
                and finding["category"] in run.FACT_CATEGORIES
                and isinstance(finding["status"], str)
                and finding["status"] in run.FACT_STATUSES,
                "invalid factual category/status",
            )
            doc_keys = set(finding) & {"supporting_document", "contradicting_document"}
            required_doc = {"supported": "supporting_document", "contradicted": "contradicting_document"}
            run._require(
                doc_keys == ({required_doc[finding["status"]]} if finding["status"] in required_doc else set()),
                "factual status/document mismatch",
            )
            for key in doc_keys:
                doc = strict_object(finding[key], key, {"document_id", "version", "quote"})
                for field in doc:
                    run._nonempty(doc[field], field)
                record = corpus.get((doc["document_id"], doc["version"]))
                run._require(record is not None and doc["quote"] in record["content"], "factual quote/version mismatch")
                # Provenance is located by offset, so a repeated quote can never be scored.
                run._require(record["content"].count(doc["quote"]) == 1, "factual quote must occur exactly once")
    counts = strict_object(data["case_counts"], "case_counts", TYPES | {"total"})
    # case_counts describe authored cases; generic cases expand to one run per scenario.
    actual = Counter(case["type"] for case in authored)
    run._require(
        all(type(counts[k]) is int and counts[k] == actual[k] for k in TYPES)
        and type(counts["total"]) is int
        and counts["total"] == len(authored),
        "case_counts mismatch",
    )
    return data


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def postprocess(case: dict[str, Any], result: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    """Add transcript-level checks and demote claim categories to diagnostics."""
    # A claim category is a labelling choice (range can be product or battery_charging), not the behaviour scored.
    categories = [
        a
        for a in result["assertions"]
        if a["assertion_id"].startswith("factual.") and a["assertion_id"].endswith(".category")
    ]
    result["assertions"] = [a for a in result["assertions"] if a not in categories]
    result["category_diagnostics"] = categories
    final = result.get("final_state")
    if final is not None and result["execution_status"] == "COMPLETE":
        replies = [m for m in final.get("messages", []) if m.get("role") == "customer"]
        revealed = set(final.get("revealed_facts", []))
        leaks = [
            {"fact_key": rule["fact_key"], "message_id": m.get("message_id")}
            for rule in scenario["disclosure_rules"]
            if rule["fact_key"] not in revealed
            for m in replies
            if _normalize(rule["revealed_statement"]) in _normalize(m.get("content", ""))
        ]
        result["assertions"].append(
            run.assertion("transcript.no_unrevealed_statement", True, not leaks, evidence={"leaks": leaks})
        )
        from src.agents.roleplay.customer_agent import _contains_system_prompt_excerpt

        excerpts = [m.get("message_id") for m in replies if _contains_system_prompt_excerpt(m.get("content", ""))]
        result["assertions"].append(
            run.assertion("transcript.no_system_prompt_excerpt", True, not excerpts, evidence={"message_ids": excerpts})
        )
    review = case["category"] in SEMANTIC_REVIEW_CATEGORIES
    if review:
        quotes = [
            {"message_id": m.get("message_id"), "quote": m.get("content")}
            for m in (final or {}).get("messages", [])
            if m.get("role") == "customer"
        ]
        result["assertions"].append(
            run.assertion(
                "semantic_role_consistency",
                "PASS",
                available=False,
                evidence={"customer_replies": quotes},
                reason="HUMAN_REVIEW_REQUIRED: confirm the customer stayed a buyer and disclosed nothing private",
            )
        )
    result["case_result"] = run._status(result["assertions"], execution=result["execution_status"], review=review)
    return result


def aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    checks = [a for case in cases for result in case["runs"] for a in result["assertions"]]
    n = len(cases)
    return {
        "case_count": n,
        "pass_at_k_rate": sum(c["pass_at_k"] for c in cases) / n if n else None,
        "pass_hat_k_rate": sum(c["pass_hat_k"] for c in cases) / n if n else None,
        "assertion_count": len(checks),
        "assertion_pass_rate": sum(a["status"] == "PASS" for a in checks) / len(checks) if checks else None,
    }


def metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": aggregate(cases),
        **{
            f"by_{field}": {
                key: aggregate([c for c in cases if c[field] == key]) for key in sorted({c[field] for c in cases})
            }
            for field in ("type", "scenario_id")
        },
    }


async def execute(data: dict[str, Any], cases: list[dict[str, Any]], mode: str, repeats: int) -> dict[str, Any]:
    results = []
    scenarios = {x["scenario_id"]: x for x in json.loads(run.SCENARIOS.read_text(encoding="utf-8"))}
    for case in cases:
        runs = []
        if mode == "live":
            for _ in range(repeats):
                result = await run.run_live_standard(case, str(uuid4()), stop_on_termination=True)
                runs.append(postprocess(case, result, scenarios[case["scenario_id"]]))
        passes = sum(r["case_result"] == "PASS" for r in runs)
        results.append(
            {
                "case_id": case["case_id"],
                "type": case["type"],
                "scenario_id": case["scenario_id"],
                "review_status": case["review"]["status"],
                "draft": case["review"]["status"] != "APPROVED",
                "runs": runs,
                "passes": passes,
                "pass_at_k": passes > 0,
                "pass_hat_k": bool(runs) and passes == len(runs),
            }
        )
    approved = [c for c in results if not c["draft"]]
    drafts = [c for c in results if c["draft"]]
    return {
        "dataset_version": data["dataset_version"],
        "mode": mode,
        "repeats": repeats,
        "executed_at": datetime.now(UTC).isoformat(),
        "cases": results,
        "metrics": metrics(approved) if mode == "live" else None,
        "draft_metrics": metrics(drafts) if mode == "live" else None,
        "diagnostics": [] if cases else ["No eligible cases selected; no models invoked."],
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Roleplay golden evaluation",
        "",
        f"Mode: {report['mode']}; K: {report['repeats']}",
        "",
        "Approved metrics exclude drafts. Unavailable assertions count as non-passing.",
        "",
    ]
    for scope in ("metrics", "draft_metrics"):
        if report[scope] is None:
            continue
        lines += [
            f"## {scope}",
            "",
            "| Group | Cases | pass@k | pass^k | Assertion pass rate |",
            "|---|---:|---:|---:|---:|",
        ]
        groups = {"overall": report[scope]["overall"]}
        for field in ("by_type", "by_scenario_id"):
            groups.update({f"{field}/{k}": v for k, v in report[scope][field].items()})
        for label, item in groups.items():
            rates = [
                "—" if item[k] is None else f"{item[k]:.1%}"
                for k in ("pass_at_k_rate", "pass_hat_k_rate", "assertion_pass_rate")
            ]
            lines.append(f"| {label} | {item['case_count']} | {' | '.join(rates)} |")
        lines.append("")
    lines += ["## Cases", "", "| Case | Review | Runs | Passes | pass@k | pass^k |", "|---|---|---:|---:|---|---|"]
    lines.extend(
        f"| {c['case_id']} | {c['review_status']} | {len(c['runs'])} | {c['passes']} | "
        f"{c['pass_at_k']} | {c['pass_hat_k']} |"
        for c in report["cases"]
    )
    lines += ["", *report["diagnostics"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--mode", choices=("validate", "live"), default="validate")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--type", choices=sorted(TYPES), action="append", default=[])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--include-draft", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        run._require(args.repeats > 0, "repeats must be positive")
        data = load_dataset(args.dataset)
        cases = run.select_cases(data, args.case_id)
        run._require(not set(args.scenario_id) - {c["scenario_id"] for c in data["cases"]}, "unknown scenario_id")
        cases = [
            c
            for c in cases
            if (not args.scenario_id or c["scenario_id"] in args.scenario_id)
            and (not args.type or c["type"] in args.type)
        ]
        if args.mode == "live":
            cases = [
                c
                for c in cases
                if c["review"]["status"] == "APPROVED"
                or args.include_draft
                and c["review"]["status"] == "PENDING_EXPERT_REVIEW"
            ]
        if args.output:
            run._require(args.output.suffix.lower() == ".json", "output must have .json extension")
            run._require(
                not args.output.exists() and not args.output.with_suffix(".md").exists(),
                "output JSON or Markdown already exists",
            )
        report = asyncio.run(execute(data, cases, args.mode, args.repeats))
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(payload)
            with args.output.with_suffix(".md").open("x", encoding="utf-8") as handle:
                handle.write(markdown(report))
        else:
            sys.stdout.write(payload)
        if args.mode == "validate":
            return 0
        return 0 if cases and all(c["pass_hat_k"] for c in report["cases"]) else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        sys.stderr.write(f"Golden evaluation failed: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
