"""Versioned LangSmith datasets/experiments with an auditable local manifest."""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from eval.copilot_eval.config import DEFAULT_MODEL, writable
from src.config import get_settings
from src.observability import TelemetryService


def save(path, data):
    path = writable(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, default=str)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_hash():
    value = hashlib.sha256()
    for root in ("src", "eval/copilot_eval"):
        for path in sorted(Path(root).rglob("*.py")):
            value.update(str(path).encode())
            value.update(path.read_bytes())
    return value.hexdigest()


def experiment(cases, name, output, metadata=None):
    output = writable(output)
    settings = get_settings().model_copy(
        update={
            "app_env": "development",
            "langsmith_project": name,
            "langsmith_tracing": True,
            "langsmith_sampling_rate": 1.0,
            "langsmith_capture_content": True,
        }
    )
    service = TelemetryService(settings)
    if not service.enabled:
        service.close()
        raise RuntimeError("LangSmith tracing unavailable; no untraced benchmark execution")
    client = service.client
    cases_hash = hashlib.sha256(json.dumps(cases, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    dataset_name = "p043-" + (metadata or {}).get("suite", "development") + "-" + cases_hash[:12]
    dataset = (
        client.read_dataset(dataset_name=dataset_name)
        if client.has_dataset(dataset_name=dataset_name)
        else client.create_dataset(
            dataset_name,
            description="Versioned Copilot regression cases; references never passed to the agent.",
            metadata={"cases_hash": cases_hash},
        )
    )
    existing = {str(e.id) for e in client.list_examples(dataset_id=dataset.id)}
    examples = {}
    for case in cases:
        eid = uuid5(NAMESPACE_URL, f"{dataset.id}/{case['case_id']}")
        examples[case["case_id"]] = eid
        if str(eid) not in existing:
            client.create_example(
                dataset_id=dataset.id,
                example_id=eid,
                inputs={k: case[k] for k in ("query", "target_date", "history", "customer_context") if k in case},
                outputs={
                    k: v
                    for k, v in case.items()
                    if k in {"ground_truth", "expected", "reference_contexts", "goals", "audit_status"}
                },
                metadata={"case_id": case["case_id"], "cases_hash": cases_hash},
            )
    manifest = {
        "started_at": datetime.now(UTC).isoformat(),
        "project": name,
        "dataset_id": str(dataset.id),
        "cases_hash": cases_hash,
        "corpus_hash": digest("data/knowledge/corpus.json"),
        "code_hash": code_hash(),
        "judge_model": DEFAULT_MODEL,
        "model": settings.model_name,
        "configuration": {k: v for k, v in settings.model_dump().items() if k.startswith("copilot_")},
        **(metadata or {}),
    }
    project = client.create_project(
        name, reference_dataset_id=dataset.id, num_examples=len(cases), num_repetitions=1, metadata=manifest
    )
    manifest.update(project_id=str(project.id), project_url=project.url)
    save(output / "manifest.json", manifest)
    save(output / "cases.json", cases)
    return service, examples, manifest


def reconcile(service, records, output):
    service.client.flush(timeout=30)
    results = []
    for row in records:
        result = {"case_id": row["case_id"], "present": False}
        log = output / f"{row['case_id']}.nodes.json"
        if not log.exists():
            log = output.parent / log.name
        expected_nodes = {n["node"] for n in json.loads(log.read_text(encoding="utf-8"))} if log.exists() else set()
        for attempt in range(3):
            try:
                run = service.client.read_run(row["request_id"], load_child_runs=True)
                descendants = []
                pending = list(run.child_runs or [])
                while pending:
                    child = pending.pop()
                    descendants.append(child)
                    pending.extend(child.child_runs or [])
                result = {
                    "case_id": row["case_id"],
                    "run_id": str(run.id),
                    "present": True,
                    "closed": run.end_time is not None,
                    "child_count": len(run.child_runs or []),
                    "descendant_count": len(descendants),
                    "node_names": sorted(
                        {
                            r.name
                            for r in descendants
                            if r.name
                            in {
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
                        }
                    ),
                    "example_linked": bool(run.reference_example_id),
                }
                result["node_coverage"] = bool(expected_nodes) and expected_nodes <= set(result["node_names"])
                if result["closed"] and result["example_linked"] and result["node_coverage"]:
                    break
            except Exception as exc:
                result = {"case_id": row["case_id"], "present": False, "error_type": type(exc).__name__}
            if attempt < 2:
                time.sleep(2)
        results.append(result)
    save(output / "langsmith_reconciliation.json", results)
    return all(
        r.get("present") and r.get("closed") and r.get("example_linked") and r.get("node_coverage") for r in results
    )
