"""Evaluate curated Judge transcripts with the production RoleplayEvaluator.

The state built here is evaluation-only. It is not a RoleplayGraph session or a
checkpoint, and unobserved runtime fields retain their scenario defaults.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.agents.roleplay.evaluator import KnowledgeEvidence, RoleplayEvaluator
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import AdvisorFactualClaim, RoleplayMessage, RoleplayState, TerminationStatus
from src.config import get_settings
from src.integrations.practice_runtime import SharedLLMEvaluationModel
from src.services.llm import get_llm

from .run import (
    DEFAULT_DATASET,
    compare,
    evaluator_prompt_version,
    load_knowledge_sources,
    read_json,
    validate_dataset,
    validate_prediction,
)

PROVENANCE = (
    "curated_synthetic JC1-JC5 transcripts; evaluation-only RoleplayState from scenario defaults; "
    "COMPLETED marks transcript end; no RoleplayGraph session, checkpoint, or runtime events"
)


def evaluation_inputs(
    dataset: dict[str, Any],
    scenarios: ScenarioRepository,
    corpus: dict[str, dict[str, Any]],
    *,
    case_id: str | None = None,
) -> list[tuple[dict[str, Any], Any, RoleplayState, list[KnowledgeEvidence]]]:
    """Map existing fixture data to evaluator inputs without replaying graph events."""
    validate_dataset(dataset)
    prepared = []
    for case in dataset["cases"]:
        if case_id is not None and case["case_id"] != case_id:
            continue
        scenario = scenarios.get(case["scenario_id"])
        if scenario.scenario_version != case["scenario_version"]:
            raise ValueError(f"{case['case_id']} scenario version mismatch")
        state = RoleplayState.from_scenario(f"judge-calibration-{case['case_id']}", scenario)
        # COMPLETED denotes the end of the curated transcript only. No finish
        # event, graph transition, checkpoint, or runtime observation is claimed.
        state = RoleplayState.model_validate(
            {
                **state.model_dump(mode="json"),
                "messages": [RoleplayMessage.model_validate(item).model_dump(mode="json") for item in case["messages"]],
                "factual_claims": [
                    AdvisorFactualClaim(
                        message_id=item["message_id"], text=item["text"], category=item["category"]
                    ).model_dump(mode="json")
                    for item in case["annotated_claims"]
                ],
                "termination_status": TerminationStatus.COMPLETED.value,
            }
        )
        evidence = []
        for source in case["knowledge_sources"]:
            record = corpus[source["document_id"]]
            if record["version"] != source["version"] or source["quote"] not in record["content"]:
                raise ValueError(f"{case['case_id']} source mismatch: {source['document_id']}")
            evidence.append(
                KnowledgeEvidence(source_id=record["document_id"], version=record["version"], content=record["content"])
            )
        prepared.append((case, scenario, state, evidence))
    return prepared


def select_inputs(prepared: list[tuple], case_id: str | None) -> list[tuple]:
    if case_id is None:
        return prepared
    selected = [item for item in prepared if item[0]["case_id"] == case_id]
    if not selected:
        raise ValueError(f"unknown case_id: {case_id}")
    return selected


def make_artifact(
    dataset: dict[str, Any],
    predictions: list[dict[str, Any]],
    failures: list[dict[str, str]],
    *,
    provider: str,
    model: str,
) -> dict[str, Any]:
    cases = {case["case_id"]: case for case in dataset["cases"]}
    seen: set[str] = set()
    for item in predictions:
        case_id = item["case_id"]
        if case_id not in cases or case_id in seen:
            raise ValueError(f"unknown or duplicate prediction case_id: {case_id}")
        validate_prediction(item["evaluation"], cases[case_id])
        seen.add(case_id)
    failed = {item["case_id"]: item for item in failures}
    if len(failed) != len(failures) or any(case_id not in cases for case_id in failed):
        raise ValueError("duplicate or unknown failure case_id")
    failed = {case_id: item for case_id, item in failed.items() if case_id not in seen}
    missing = sorted(cases.keys() - seen)
    return {
        "provenance": PROVENANCE,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": provider,
        "model": model,
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "successful_case_count": len(seen),
        "failed_case_count": len(failed),
        "missing_case_ids": missing,
        "predictions": predictions,
        "failures": list(failed.values()),
    }


def merge_artifacts(dataset: dict[str, Any], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    if not artifacts:
        raise ValueError("at least one input artifact is required")
    provider, model = artifacts[0]["provider"], artifacts[0]["model"]
    predictions: list[dict[str, Any]] = []
    failures: dict[str, dict[str, str]] = {}
    for artifact in artifacts:
        if artifact.get("provenance") != PROVENANCE or (artifact.get("provider"), artifact.get("model")) != (
            provider,
            model,
        ):
            raise ValueError("artifact provenance, provider, or model mismatch")
        predictions.extend(artifact["predictions"])
        for failure in artifact.get("failures", []):
            failures[failure["case_id"]] = failure
    return make_artifact(dataset, predictions, list(failures.values()), provider=provider, model=model)


def save_artifact(path: Path, artifact: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(artifact, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


async def collect_predictions(
    dataset: dict[str, Any],
    prepared: list[tuple[dict[str, Any], Any, RoleplayState, list[KnowledgeEvidence]]],
    evaluator: RoleplayEvaluator,
    *,
    provider: str,
    model: str,
) -> dict[str, Any]:
    predictions = []
    failures = []
    for case, scenario, state, evidence in prepared:
        try:
            result = await evaluator.evaluate(scenario, state, evidence)
            evaluation = result.model_dump(mode="json")
            validate_prediction(evaluation, case)
            predictions.append({"case_id": case["case_id"], "evaluation": evaluation})
        except Exception as exc:
            failures.append({"case_id": case["case_id"], "error_type": type(exc).__name__, "reason": str(exc)})
    return make_artifact(dataset, predictions, failures, provider=provider, model=model)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--preflight", action="store_true", help="Validate inputs offline; never create an LLM client")
    parser.add_argument("--case-id", help="Evaluate one case from the dataset")
    parser.add_argument("--merge", nargs="+", type=Path, metavar="ARTIFACT", help="Merge saved case artifacts offline")
    parser.add_argument("--output", type=Path, help="New prediction JSON path; existing files are never overwritten")
    args = parser.parse_args(argv)
    if args.merge and (args.preflight or args.case_id):
        parser.error("--merge cannot be combined with --preflight or --case-id")
    if not args.preflight and args.output is None:
        parser.error("--output is required")
    try:
        dataset = read_json(args.dataset)
        validate_dataset(dataset)
        if args.output is not None and args.output.exists():
            raise FileExistsError(f"output already exists: {args.output}")
        if args.merge:
            artifact = merge_artifacts(dataset, [read_json(path) for path in args.merge])
            if artifact["status"] == "COMPLETE":
                compare(dataset, artifact)
            assert args.output is not None
            save_artifact(args.output, artifact)
            print(
                json.dumps(
                    {
                        key: artifact[key]
                        for key in (
                            "status",
                            "successful_case_count",
                            "failed_case_count",
                            "missing_case_ids",
                            "failures",
                        )
                    },
                    ensure_ascii=False,
                )
            )
            return 0 if artifact["status"] == "COMPLETE" else 1
        corpus = load_knowledge_sources()
        prepared = select_inputs(
            evaluation_inputs(dataset, ScenarioRepository(), corpus, case_id=args.case_id), args.case_id
        )
        if args.preflight:
            print(
                json.dumps(
                    {
                        "status": (
                            "READY_FOR_LIVE_APPROVAL"
                            if dataset["rubric_version"] == evaluator_prompt_version()
                            else "OFFLINE_VALIDATED_RUBRIC_MISMATCH"
                        ),
                        "pending_expert_review_case_ids": [
                            item[0]["case_id"]
                            for item in prepared
                            if any(
                                label["review_status"] == "PENDING_EXPERT_REVIEW"
                                for label in item[0]["expert_labels"].values()
                            )
                        ],
                        "case_ids": [item[0]["case_id"] for item in prepared],
                        "annotated_claims": sum(len(item[2].factual_claims) for item in prepared),
                        "knowledge_sources": sum(len(item[3]) for item in prepared),
                    },
                    indent=2,
                )
            )
            return 0
        assert args.output is not None
        if dataset["rubric_version"] != evaluator_prompt_version():
            raise ValueError(
                "live evaluation requires the current rubric; historical expert labels must not be relabelled"
            )
        settings = get_settings()
        client = get_llm()
        provider = settings.llm_provider
        if provider == "openai" and not settings.openai_api_key and settings.openrouter_api_key:
            provider = "openrouter"
        artifact = asyncio.run(
            collect_predictions(
                dataset,
                prepared,
                RoleplayEvaluator(SharedLLMEvaluationModel(lambda: client)),
                provider=provider,
                model=getattr(client, "model_name", settings.model_name),
            )
        )
        if artifact["status"] == "COMPLETE":
            compare(dataset, artifact)
        save_artifact(args.output, artifact)
        print(
            json.dumps(
                {
                    "prediction_artifact": str(args.output),
                    **{
                        key: artifact[key]
                        for key in (
                            "status",
                            "successful_case_count",
                            "failed_case_count",
                            "missing_case_ids",
                            "failures",
                        )
                    },
                },
                ensure_ascii=False,
            )
        )
        return 0 if not artifact["failures"] else 1
    except (OSError, ValueError, KeyError) as exc:
        print(f"judge adapter error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
