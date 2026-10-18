"""Cloud readback for persisted runs. Reconciliation never edits remote traces."""

import json
from collections import Counter
from uuid import NAMESPACE_URL, uuid5

from langsmith import Client
from urllib3.util.retry import Retry

from eval.copilot_eval.config import case_path, writable
from eval.copilot_eval.experiment import save
from src import observability as obs
from src.config import get_settings

NODE_NAMES = {
    "analyze_and_route",
    "plan_queries",
    "retrieve_documents",
    "select_evidence",
    "build_context",
    "generate_answer",
    "check_grounding",
    "finalize_response",
    "fallback_response",
}


class OfflineTelemetry(obs.TelemetryService):
    def __init__(self, settings, *, client=None):
        client = client or Client(
            api_url=settings.langsmith_endpoint,
            api_key=settings.langsmith_api_key.get_secret_value(),
            timeout_ms=(10000, 30000),
            retry_config=Retry(total=2, backoff_factor=0.2),
            auto_batch_tracing=True,
            hide_metadata=obs.safe_metadata,
            omit_traced_runtime_info=True,
            otel_enabled=False,
            disable_prompt_cache=True,
        )
        super().__init__(settings, client=client)


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from dictionaries(v)
    elif isinstance(value, list):
        for v in value:
            yield from dictionaries(v)


def reconcile_cloud(config):
    output = writable(config.run_dir)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((output / "results.json").read_text(encoding="utf-8"))
    service = OfflineTelemetry(
        get_settings().model_copy(
            update={
                "langsmith_tracing": True,
                "langsmith_project": manifest["project"],
            }
        )
    )
    if not service.enabled:
        service.close()
        raise RuntimeError("LangSmith tracing unavailable")
    results = []
    try:
        for row in rows:
            item = {"case_id": row["case_id"], "request_id": row["request_id"]}
            try:
                root = service.client.read_run(row["request_id"])
                children = [
                    c
                    for c in service.client.list_runs(project_id=manifest["project_id"], trace_id=root.trace_id)
                    if c.id != root.id
                ]
                log = case_path(output, row["case_id"], ".nodes.json")
                nodes = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
                expected = Counter(
                    e["node"]
                    for e in row.get("trace", [])
                    if not e.get("llm") and not e.get("decision") and e.get("node") in NODE_NAMES
                )
                if not expected:
                    expected = Counter(n["node"] for n in nodes)
                actual = Counter(c.name for c in children if c.name in NODE_NAMES)
                llms = [c for c in children if c.run_type == "llm" and not c.name.startswith("judge.")]
                usage = []
                for child in llms:
                    metadata = [
                        d["response_metadata"]
                        for d in dictionaries(child.outputs)
                        if isinstance(d.get("response_metadata"), dict)
                    ]
                    response = next((r for r in metadata if r.get("token_usage")), {})
                    tokens = response.get("token_usage", {})
                    usage.append(
                        {
                            "run_id": str(child.id),
                            "actual_model": response.get("model_name")
                            or child.extra.get("metadata", {}).get("ls_model_name"),
                            "input_tokens": tokens.get("prompt_tokens", child.prompt_tokens),
                            "output_tokens": tokens.get("completion_tokens", child.completion_tokens),
                            "provider_cost_usd": tokens.get("cost"),
                            "langsmith_cost_usd": float(child.total_cost) if child.total_cost is not None else None,
                        }
                    )
                feedback = list(service.client.list_feedback(run_ids=[row["request_id"]]))
                review_path = case_path(output / "evaluation", row["case_id"])
                review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
                expected_feedback = set(review.get("feedback_ids", []))
                item.update(
                    present=True,
                    closed=root.end_time is not None,
                    linked=str(root.reference_example_id)
                    == str(uuid5(NAMESPACE_URL, f"{manifest['dataset_id']}/{row['case_id']}")),
                    node_expected=dict(expected),
                    node_actual=dict(actual),
                    node_occurrences_complete=bool(expected) and actual == expected,
                    llm_attempts_expected=sum(bool(e.get("llm")) for e in row.get("trace", [])),
                    llm_attempts_readback=len(llms),
                    root_answer_matches=(root.outputs or {}).get("answer") == row.get("answer"),
                    truncated_child_payloads=sum(
                        "[TRUNCATED]" in json.dumps([c.outputs, c.inputs], default=str) for c in children
                    ),
                    runtime_usage=usage,
                    feedback_expected=len(expected_feedback),
                    feedback_read_back=sum(str(f.id) in expected_feedback for f in feedback),
                )
            except Exception as exc:
                item.update(present=False, error_type=type(exc).__name__)
            results.append(item)
            save(output / "cloud-deep-reconciliation.json", results)
        usage = [u for r in results for u in r.get("runtime_usage", [])]
        costs = [u["provider_cost_usd"] for u in usage if isinstance(u.get("provider_cost_usd"), (int, float))]
        save(
            output / "cloud-runtime-usage.json",
            {
                "runtime_llm_runs": len(usage),
                "provider_cost_known_runs": len(costs),
                "provider_cost_known_usd": sum(costs) if costs else None,
                "cost_complete": len(costs) == len(usage) and bool(usage),
                "limitation": "Embeddings and Jev excluded; LangSmith calculated cost is distinct from provider billing.",
            },
        )
    finally:
        service.close()
    ok = (
        len(results) == len(rows)
        and bool(rows)
        and all(
            r.get("present")
            and r.get("closed")
            and r.get("linked")
            and r.get("node_occurrences_complete")
            and r.get("root_answer_matches")
            and r.get("llm_attempts_expected") == r.get("llm_attempts_readback")
            and r.get("feedback_expected") == r.get("feedback_read_back")
            for r in results
        )
    )
    if not ok:
        raise RuntimeError("Cloud reconciliation incomplete; local outcomes preserved")
    return results
