"""Measure finish-time evidence recall across claim categories.

Usage: python -m eval.roleplay_eval.evidence_recall --mode validate
Run mode uses paid embeddings unless a retriever is injected into execute().
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import run

if TYPE_CHECKING:
    from src.integrations.practice_knowledge import KnowledgeRetriever

DATASET = run.ROOT / "eval/datasets/roleplay_evidence_recall.json"
CORPUS = run.ROOT / "data/knowledge/corpus.json"


def claim_categories() -> tuple[str, ...]:
    """Read the Literal without importing the package's model/provider dependencies."""
    tree = ast.parse((run.ROOT / "src/agents/roleplay/contracts.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ClaimCategory" for target in node.targets
        ):
            value = node.value
            run._require(
                isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) and value.value.id == "Literal",
                "ClaimCategory must be a Literal",
            )
            categories = ast.literal_eval(value.slice)
            run._require(
                isinstance(categories, tuple) and all(isinstance(c, str) for c in categories),
                "invalid ClaimCategory Literal",
            )
            return categories
    raise ValueError("ClaimCategory Literal not found")


def validate(path: Path = DATASET, scenario_path: Path = run.SCENARIOS, corpus_path: Path = CORPUS) -> dict[str, Any]:
    """Load and validate probes against the current scenarios, corpus and contract."""
    data = run._object(json.loads(path.read_text(encoding="utf-8")), "dataset", {"categories", "probes"})
    categories = data["categories"]
    allowed_categories = claim_categories()
    run._require(isinstance(categories, list) and bool(categories), "categories must be a nonempty list")
    for category in categories:
        run._nonempty(category, "category")
        run._require(category in allowed_categories, f"unknown ClaimCategory: {category}")
    run._require(len(set(categories)) == len(categories), "duplicate category")
    scenarios = {s["scenario_id"] for s in json.loads(scenario_path.read_text(encoding="utf-8"))}
    corpus = {(d["document_id"], d["version"]): d for d in json.loads(corpus_path.read_text(encoding="utf-8"))}
    run._require(isinstance(data["probes"], list) and bool(data["probes"]), "probes must be a nonempty list")
    seen: set[str] = set()
    for raw in data["probes"]:
        probe = run._object(raw, "probe", {"probe_id", "source", "scenario_id", "claim_text", "expected"})
        for key in ("probe_id", "source", "scenario_id", "claim_text"):
            run._nonempty(probe[key], key)
        label = probe["probe_id"]
        run._require(label not in seen, f"duplicate probe_id: {label}")
        seen.add(label)
        run._require(probe["source"] in {"golden", "paraphrase"}, f"{label}: invalid source")
        run._require(probe["scenario_id"] in scenarios, f"{label}: unknown scenario_id")
        run._require(
            isinstance(probe["expected"], list) and bool(probe["expected"]), f"{label}: expected must be nonempty list"
        )
        for raw_document in probe["expected"]:
            document = run._object(raw_document, f"{label}.expected", {"document_id", "version", "quote"})
            for key in ("document_id", "version", "quote"):
                run._nonempty(document[key], key)
            record = corpus.get((document["document_id"], document["version"]))
            run._require(record is not None, f"{label}: unknown document_id/version")
            run._require(record["content"].count(document["quote"]) == 1, f"{label}: quote must occur exactly once")
    return data


def aggregate(cells: list[dict[str, Any]]) -> dict[str, Any]:
    passing = sum(cell["passed"] for cell in cells)
    return {
        "cells": len(cells),
        "passing_cells": passing,
        "recall": passing / len(cells) if cells else None,
        "mean_evidence_chunks": sum(cell["evidence_count"] for cell in cells) / len(cells) if cells else None,
    }


def execute(
    data: dict[str, Any],
    probes: list[dict[str, Any]],
    retriever: KnowledgeRetriever | None = None,
    *,
    scenario_path: Path = run.SCENARIOS,
    **provider_options: Any,
) -> dict[str, Any]:
    """Exercise the production evidence provider once per probe/category cell."""
    from src.agents.roleplay.scenario_loader import ScenarioRepository
    from src.agents.roleplay.state import AdvisorFactualClaim, RoleplayState
    from src.integrations.practice_knowledge import RetrievalKnowledgeEvidenceProvider

    if retriever is None:
        from src.knowledge.retrieval_service import RetrievalService

        retriever = RetrievalService()
    provider = RetrievalKnowledgeEvidenceProvider(retriever, **provider_options)
    scenarios = ScenarioRepository(scenario_path)
    cells = []
    for probe in probes:
        scenario = scenarios.get(probe["scenario_id"])
        for category in data["categories"]:
            state = RoleplayState.from_scenario("recall", scenario)
            state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=probe["claim_text"], category=category)]
            evidence = asyncio.run(provider.for_session(scenario, state))
            expected = []
            for document in probe["expected"]:
                # Only the expected document and version count, as in golden provenance scoring.
                own = [
                    item
                    for item in evidence
                    if item.source_id.startswith(document["document_id"] + "_") and item.version == document["version"]
                ]
                found = any(document["quote"] in item.content for item in own)
                if not found:
                    linked = [{"chunk_id": item.source_id, "content": item.content} for item in own]
                    covered, _ = run._ground_truth_quote_coverage(document, linked)
                    found = covered is True
                expected.append({**document, "found": found})
            cells.append(
                {
                    "probe_id": probe["probe_id"],
                    "source": probe["source"],
                    "scenario_id": probe["scenario_id"],
                    "category": category,
                    "passed": all(item["found"] for item in expected),
                    "expected": expected,
                    "evidence_source_ids": [item.source_id for item in evidence],
                    "evidence_count": len(evidence),
                }
            )
    return {
        "dataset_version": data.get("dataset_version"),
        "mode": "run",
        "executed_at": datetime.now(UTC).isoformat(),
        "categories": data["categories"],
        "cells": cells,
        "metrics": {
            "overall": aggregate(cells),
            "by_category": {cat: aggregate([c for c in cells if c["category"] == cat]) for cat in data["categories"]},
            "by_source": {
                source: aggregate([c for c in cells if c["source"] == source]) for source in ("golden", "paraphrase")
            },
            "by_probe": {
                p["probe_id"]: aggregate([c for c in cells if c["probe_id"] == p["probe_id"]]) for p in probes
            },
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = ["# Roleplay evidence recall", "", f"Mode: {report['mode']}", ""]
    if report["mode"] == "validate":
        return "\n".join(
            [*lines, f"Validated {report['probe_count']} probes; {len(report['categories'])} categories.", ""]
        )
    lines += ["| Group | Passing / cells | Recall | Mean evidence chunks |", "|---|---:|---:|---:|"]
    groups = {"overall": report["metrics"]["overall"]}
    for field in ("by_category", "by_source", "by_probe"):
        groups.update({f"{field}/{key}": value for key, value in report["metrics"][field].items()})
    for label, item in groups.items():
        recall = "—" if item["recall"] is None else f"{item['recall']:.1%}"
        mean = "—" if item["mean_evidence_chunks"] is None else f"{item['mean_evidence_chunks']:.2f}"
        lines.append(f"| {label} | {item['passing_cells']} / {item['cells']} | {recall} | {mean} |")
    categories = report["categories"]
    lines += [
        "",
        "## Probe × category",
        "",
        f"| Probe | {' | '.join(categories)} |",
        "|---|" + "---|" * len(categories),
    ]
    cells = {(c["probe_id"], c["category"]): c["passed"] for c in report["cells"]}
    for probe_id in report["metrics"]["by_probe"]:
        marks = ["✓" if cells[probe_id, cat] else "✗" for cat in categories]
        lines.append(f"| {probe_id} | {' | '.join(marks)} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--mode", choices=("validate", "run"), default="validate")
    parser.add_argument("--probe-id", action="append", nargs="+", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        data = validate(args.dataset)
        selected = {identifier for group in args.probe_id for identifier in group}
        run._require(not selected - {p["probe_id"] for p in data["probes"]}, "unknown probe_id")
        probes = [p for p in data["probes"] if not selected or p["probe_id"] in selected]
        output = args.output
        if args.mode == "run" and output is None:
            output = run.ROOT / "eval/results" / f"evidence_recall_{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.json"
        if output:
            run._require(output.suffix.lower() == ".json", "output must have .json extension")
            run._require(
                not output.exists() and not output.with_suffix(".md").exists(), "output JSON or Markdown already exists"
            )
        report = (
            execute(data, probes)
            if args.mode == "run"
            else {"mode": "validate", "probe_count": len(probes), "categories": data["categories"]}
        )
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if output:
            with output.open("x", encoding="utf-8") as handle:
                handle.write(payload)
            with output.with_suffix(".md").open("x", encoding="utf-8") as handle:
                handle.write(markdown(report))
        else:
            sys.stdout.write(payload)
        return 0 if args.mode == "validate" or all(c["passed"] for c in report["cells"]) else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        sys.stderr.write(f"Evidence recall evaluation failed: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
