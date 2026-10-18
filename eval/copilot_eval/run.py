"""Run the approved Gate 3 benchmark against the real Copilot graph.

From the repository root: python -m eval.copilot_eval.run
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from eval.metrics import (
    appropriate_behavior,
    citation_correctness,
    metric_result,
    policy_version_correctness,
    required_fact_coverage,
)
from eval.runner import (
    build_parser,
    load_corpus_by_id,
    load_dataset,
    run_cases,
    select_cases,
    validate_gate3_benchmark_composition,
    validate_ground_truth,
    write_component_reports,
)


async def execute(args: Any) -> tuple[str, str, int]:
    from src.config import get_settings

    if getattr(args, "selection_strategy", None):
        get_settings().copilot_evidence_selection_strategy = args.selection_strategy
    dataset = load_dataset(args.dataset)
    if dataset["benchmark_version"] == "gate3-v1":
        validate_gate3_benchmark_composition(dataset)
    corpus_by_id = load_corpus_by_id()
    validate_ground_truth(dataset, corpus_by_id)
    cases = select_cases(dataset, args.case_id, args.group)
    if args.repeat < 1:
        raise ValueError("--repeat must be positive")

    from src.knowledge.retrieval_service import get_retrieval_service

    retriever = get_retrieval_service()
    from src.knowledge.index_readiness import check_copilot_index, embedding_identity

    snapshot = check_copilot_index()
    index_config = {
        "corpus_sha256": snapshot.fingerprint,
        "indexed_chunks": len(snapshot.chunks),
        "embedding": embedding_identity(get_settings()),
        "embedding_provenance": "manifest_verified",
        "vector_store": type(retriever.vector_store).__name__,
        "model_name": get_settings().model_name,
    }

    from src.agents.copilot.graph import copilot_agent

    async def observe(case: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        from src.agents.copilot.runtime import RuntimeBudget

        budget = RuntimeBudget.create(get_settings())
        try:
            state = await asyncio.wait_for(
                copilot_agent.ainvoke(
                    {
                        "query": case["query"],
                        "target_date": case["target_date"],
                        "customer_context": case.get("customer_context", ""),
                        "history": case.get("history", []),
                        "snapshot": check_copilot_index(),
                        "runtime": budget,
                    },
                    config={"recursion_limit": 80},
                ),
                timeout=get_settings().copilot_request_timeout_seconds,
            )
        except Exception as exc:
            return {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "elapsed_seconds": time.perf_counter() - started,
                "trace": budget.events,
                "llm_calls": budget.attempts,
                "input_tokens_observed": sum(e.get("input_tokens") or 0 for e in budget.events),
                "output_tokens_observed": sum(e.get("output_tokens") or 0 for e in budget.events),
            }
        if not isinstance(state, Mapping):
            raise TypeError("Copilot graph did not return a state mapping")
        chunks = state.get("evidence_registry") or []
        if not isinstance(chunks, list):
            raise TypeError("Copilot retrieved_chunks is not a list")
        final = state["final_response"].model_dump(mode="json")
        model_events = [event for event in budget.events if event.get("llm")]
        return {
            **final,
            "is_abstain": final["status"] == "abstained",
            "is_clarification": final["status"] == "needs_clarification",
            "elapsed_seconds": time.perf_counter() - started,
            "tool_calls": state.get("tool_calls", 0),
            "retrieval_rounds": state.get("retrieval_rounds", 0),
            "trace": budget.events,
            "llm_calls": len(model_events),
            "token_usage_complete": bool(model_events)
            and all(
                event.get("input_tokens") is not None and event.get("output_tokens") is not None
                for event in model_events
            ),
            "input_tokens_observed": sum(event.get("input_tokens") or 0 for event in model_events),
            "output_tokens_observed": sum(event.get("output_tokens") or 0 for event in model_events),
            "retrieved_document_ids": [chunk["document_id"] for chunk in chunks],
            "retrieved_chunk_ids": [chunk["chunk_id"] for chunk in chunks],
            "selected_chunk_ids": [chunk["chunk_id"] for chunk in state.get("selected_evidence", [])],
            "context_characters": len(state.get("answer_context", "")),
            "corrective_retrieval_count": state.get("corrective_retrieval_count", 0),
            "evidence_selection_diagnostics": state.get("evidence_selection_diagnostics", []),
        }

    def score_case(case: dict[str, Any], actual: dict[str, Any]) -> dict[str, dict[str, Any]]:
        if "error_type" in actual:
            return {
                "runtime_execution": metric_result(
                    score=0.0,
                    applicable=True,
                    passed=False,
                    reason=f"Runtime call failed: {actual['error_type']}: {actual['error']}",
                )
            }
        citations = actual["citations"]
        if not isinstance(citations, list):
            raise TypeError("Copilot citations is not a list")
        cited_ids = [item.get("document_id") for item in citations if isinstance(item, Mapping)]
        metrics = {
            "citation_correctness": citation_correctness(case["expected"], citations, corpus_by_id),
            "policy_version_correctness": policy_version_correctness(case["expected"], cited_ids, source="citations"),
            "appropriate_behavior": appropriate_behavior(case["expected"], actual),
            "required_fact_coverage": required_fact_coverage(case["expected"], actual["answer"]),
        }
        if case["expected"].get("response_status"):
            passed = actual["status"] == case["expected"]["response_status"]
            metrics["response_status"] = metric_result(
                score=float(passed),
                applicable=True,
                passed=passed,
                reason="Expected " + case["expected"]["response_status"],
            )
        if case["category"] in {"call_preparation", "comparison", "objection"}:
            actionable = bool(actual.get("answer"))
            metrics["sales_output_present"] = metric_result(
                score=float(actionable),
                applicable=True,
                passed=actionable,
                reason="Grounded answer present; optional sales fields do not block evaluation.",
            )
        return metrics

    semaphore = asyncio.Semaphore(getattr(args, "concurrency", 1))

    async def evaluate(case):
        async with semaphore:
            result = await run_cases([case], observe, score_case, repeat=args.repeat)
            actual = result[0]["actual"]
            directory = (getattr(args, "reports_dir", None) or Path("eval/reports/sales_agentic")) / "progress"
            directory.mkdir(parents=True, exist_ok=True)
            import json

            (directory / f"{case['case_id']}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                f"{case['case_id']}: {actual.get('status', actual.get('error', 'error'))} "
                f"{actual.get('reason_code') or ''} {actual.get('elapsed_seconds', 0):.1f}s",
                flush=True,
            )
            return result

    groups = await asyncio.gather(*[evaluate(case) for case in cases])
    results = [result for group in groups for result in group]
    config = {
        **index_config,
        "graph": "src.agents.copilot.graph.copilot_agent",
        "context_chunks": 8,
        "repeat": args.repeat,
        "selection_strategy": get_settings().copilot_evidence_selection_strategy,
        "selected_groups": args.group,
    }
    result_path, failed_path = write_component_reports(
        component="copilot",
        benchmark_version=dataset["benchmark_version"],
        per_case_results=results,
        execution_config=config,
        **(
            {
                "reports_dir": getattr(args, "reports_dir", None)
                or args.dataset.parent.parent / "reports" / "sales_agentic"
            }
            if dataset["benchmark_version"] != "gate3-v1"
            else {}
        ),
    )
    return str(result_path), str(failed_path), sum(not result["passed"] for result in results)


def main() -> int:
    parser = build_parser("Run Gate 3 Copilot evaluation against the real LangGraph agent")
    parser.add_argument("--concurrency", type=int, choices=(1, 2), default=1)
    parser.add_argument("--reports-dir", type=Path)
    parser.add_argument("--selection-strategy", choices=("rrf_context", "jev_context"))
    parser.set_defaults(dataset=Path(__file__).resolve().parents[1] / "datasets" / "copilot_benchmark.json")
    args = parser.parse_args()
    try:
        result_path, failed_path, failure_count = asyncio.run(execute(args))
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"Gate 3 Copilot evaluation stopped: {exc}\n")
    print(f"Copilot results: {result_path}")
    print(f"Failed cases: {failed_path}")
    print(f"Failed/not-observable runs: {failure_count}")
    return 1 if failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
