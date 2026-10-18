"""Sequential frozen graph capture; failed and interrupted attempts are outcomes."""

import asyncio
import hashlib
import json
import platform
import time
import traceback
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from eval.copilot_eval.config import REPO, RunConfig, case_path, writable
from eval.copilot_eval.experiment import digest, experiment, reconcile, save
from eval.copilot_eval.telemetry import graph_case, serial, snapshot


def tree_hash(root):
    root = Path(root).resolve()
    files = {p.relative_to(REPO).as_posix(): digest(p) for p in sorted(root.rglob("*.py"))}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), files


def runtime_configuration():
    from src.config import get_settings

    settings = get_settings().model_dump()
    return {
        k: v
        for k, v in settings.items()
        if k.startswith("copilot_")
        or k
        in {
            "llm_provider",
            "model_name",
            "openrouter_model_name",
            "embedding_model_name",
            "embedding_provider",
            "vector_store_type",
                "llm_temperature",
                "chroma_collection_name",
                "chroma_persist_dir",
                "knowledge_manifest_dir",
        }
    }


def identity(config: RunConfig):
    return {
        "runtime_hash": tree_hash(REPO / "src")[0],
        "evaluator_hash": tree_hash(REPO / "eval/copilot_eval")[0],
        "benchmark_hash": digest(config.dataset),
        "corpus_hash": digest(config.corpus),
        "rubric_hash": digest(config.rubric),
        "calibration_hash": digest(config.calibration),
        "configuration": runtime_configuration(),
        "judge_model": config.judge_model,
    }


def validate_inputs(config: RunConfig, audit_path: Path):
    from eval.runner import (
        load_corpus_by_id,
        load_dataset,
        validate_gate3_benchmark_composition,
        validate_ground_truth,
    )

    dataset = load_dataset(config.dataset)
    validate_ground_truth(dataset, load_corpus_by_id(config.corpus))
    if config.suite == "benchmark":
        validate_gate3_benchmark_composition(dataset)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if not (
        audit.get("provenance_pass")
        and audit.get("content_review_complete")
        and audit.get("benchmark_after") == digest(config.dataset)
        and audit.get("corpus") == digest(config.corpus)
    ):
        raise RuntimeError("Source audit is absent, incomplete or belongs to different data")
    import re
    if not re.fullmatch(r"[0-9a-f]{64}", str(audit.get("benchmark_before", ""))):
        raise RuntimeError("Source audit requires the original benchmark SHA-256")
    if any(c.get("audit_status") not in {"valid", "invalid", "unresolved"} for c in dataset["cases"]):
        raise RuntimeError("Every case requires explicit source-audit status")
    for case in dataset["cases"]:
        case_path(config.run_dir, case["case_id"])
    return dataset, audit


def preserved_attempt(output, case):
    """Completed failures remain failures; started-without-outcome becomes interrupted."""
    path = case_path(output, case["case_id"])
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    marker = case_path(output, case["case_id"], ".started.json")
    if marker.exists():
        row = {
            **json.loads(marker.read_text(encoding="utf-8")),
            "error_type": "InterruptedAttempt",
            "elapsed_seconds": None,
        }
        save(path, row)
        return row
    return None


def capture_hashes(output, cases):
    paths = [output / "cases.json", output / "results.json"]
    paths += [case_path(output, c["case_id"], ".nodes.json") for c in cases]
    paths += [case_path(output, c["case_id"]) for c in cases]
    return {p.name: digest(p) if p.exists() else None for p in paths}


async def execute(config: RunConfig):
    import psutil

    from src.agents.copilot.graph import copilot_agent
    from src.agents.copilot.runtime import RuntimeBudget
    from src.config import get_settings
    from src.knowledge.index_readiness import check_copilot_index
    from src.observability import TelemetryService, graph_config

    output = writable(config.run_dir)
    dataset, audit = validate_inputs(config, output / "preflight/audit-validation.json")
    current = identity(config)
    preflight_path = output / "preflight/preflight.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if not preflight.get("passed") or preflight.get("identity") != current:
        raise RuntimeError("Preflight does not match current runtime/evaluator/data/configuration")
    if digest(output / "preflight/audit-validation.json") != preflight["audit_hash"]:
        raise RuntimeError("Audit changed after preflight")
    cases = dataset["cases"]
    index = await asyncio.to_thread(check_copilot_index)
    if index.fingerprint != digest(config.corpus):
        raise RuntimeError("Runtime index differs from requested corpus; no ingestion performed")
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(manifest.get(k) != v for k, v in current.items()):
            raise RuntimeError("Frozen inputs changed; cannot resume")
        if manifest["project"] != config.project or manifest["suite"] != config.suite:
            raise RuntimeError("Project/suite changed; cannot resume")
        stored = json.loads((output / "cases.json").read_text(encoding="utf-8"))
        if stored != cases:
            raise RuntimeError("Persisted case snapshot changed")
        service = TelemetryService(
            get_settings().model_copy(
                update={
                    "app_env": "development",
                    "langsmith_project": manifest["project"],
                    "langsmith_tracing": True,
                    "langsmith_sampling_rate": 1.0,
                    "langsmith_capture_content": True,
                }
            )
        )
        if not service.enabled:
            service.close()
            raise RuntimeError("LangSmith tracing unavailable")
        examples = {c["case_id"]: uuid5(NAMESPACE_URL, f"{manifest['dataset_id']}/{c['case_id']}") for c in cases}
    else:
        service, examples, manifest = experiment(
            cases,
            config.project,
            output,
            {
                **config.paths(),
                **current,
                "suite": config.suite,
                "transport": "graph",
                "candidate": "v9-evidence-review",
                "concurrency": 1,
                "benchmark_before_hash": audit["benchmark_before"],
                "preflight_hash": digest(preflight_path),
                "python": platform.python_version(),
                "runtime_files": tree_hash(REPO / "src")[1],
                "evaluator_files": tree_hash(REPO / "eval/copilot_eval")[1],
                "valid_cases": sum(c.get("audit_status") == "valid" for c in cases),
                "invalid_cases": sum(c.get("audit_status") != "valid" for c in cases),
            },
        )
        with zipfile.ZipFile(output / "evaluation-snapshot.zip", "x", zipfile.ZIP_DEFLATED) as archive:
            for folder in (REPO / "src", REPO / "eval/copilot_eval"):
                for p in folder.rglob("*.py"):
                    archive.write(p, p.relative_to(REPO).as_posix())
            for name, p in (
                ("dataset.json", config.dataset),
                ("corpus.json", config.corpus),
                ("rubric.md", config.rubric),
                ("calibration.json", config.calibration),
            ):
                archive.write(p, "inputs/" + name)
    records = []
    try:
        save(
            output / "index-identity.json",
            {"corpus_hash": index.fingerprint, "documents": len(index.documents), "chunks": len(index.chunks)},
        )
        for case in cases:
            cid = case["case_id"]
            if identity(config) != current:
                raise RuntimeError("Frozen inputs changed during execution")
            preserved = preserved_attempt(output, case)
            if preserved is not None:
                records.append(preserved)
                save(output / "results.json", records)
                continue
            updates = []
            started = time.monotonic()

            def observe(name, state):
                updates.append({"node": name, "elapsed_seconds": time.monotonic() - started, "state": snapshot(state)})
                save(case_path(output, cid, ".nodes.json"), updates)

            runtime = RuntimeBudget.create(get_settings())
            rss = []
            stop = asyncio.Event()

            async def memory():
                while not stop.is_set():
                    rss.append(
                        {"rss": psutil.Process().memory_info().rss, "available": psutil.virtual_memory().available}
                    )
                    try:
                        await asyncio.wait_for(stop.wait(), 1)
                    except TimeoutError:
                        pass

            with graph_case(service, case, output.name, examples[cid], observe) as scope:
                row = {
                    "case_id": cid,
                    "request_id": scope.request_id,
                    "started_at": datetime.now(UTC).isoformat(),
                    "audit_status": case["audit_status"],
                    "original_case_id": case.get("original_case_id"),
                }
                save(case_path(output, cid, ".started.json"), row)
                monitor = asyncio.create_task(memory())
                try:
                    # Deliberately whitelist inputs: gold/expected never enters the agent.
                    state = await asyncio.wait_for(
                        copilot_agent.ainvoke(
                            {
                                "query": case["query"],
                                "target_date": case.get("target_date"),
                                "history": [],
                                "snapshot": index,
                                "runtime": runtime,
                                "request_id": scope.request_id,
                            },
                            config={"recursion_limit": 80, **graph_config()},
                        ),
                        get_settings().copilot_request_timeout_seconds,
                    )
                    row.update(serial(state["final_response"]))
                except Exception as exc:
                    row.update(
                        error_type=type(exc).__name__,
                        cause_type=type(exc.__cause__).__name__ if exc.__cause__ else None,
                        error_frames=[
                            {"file": f.filename, "line": f.lineno, "function": f.name}
                            for f in traceback.extract_tb(exc.__traceback__)
                        ],
                    )
                    if scope.root:
                        scope.root.error = type(exc).__name__
                finally:
                    stop.set()
                    await monitor
                row.update(
                    elapsed_seconds=time.monotonic() - started,
                    trace=runtime.events,
                    provider_retries=runtime.provider_retries,
                    memory={
                        "peak_rss_bytes": max((x["rss"] for x in rss), default=None),
                        "minimum_available_bytes": min((x["available"] for x in rss), default=None),
                        "samples": len(rss),
                    },
                )
                if scope.root:
                    scope.root.outputs = {k: v for k, v in row.items() if k not in {"trace", "error_frames"}}
            save(case_path(output, cid), row)
            records.append(row)
            save(output / "results.json", records)
            print(cid, row.get("status", row.get("error_type")), flush=True)
        save(
            output / "integrity.json",
            {
                "unchanged": identity(config) == current,
                "outcomes": len(records),
                "expected": len(cases),
                "identity": current,
                "capture_hashes": capture_hashes(output, cases),
            },
        )
        if not reconcile(service, records, output):
            raise RuntimeError("Capture saved; Cloud trace reconciliation incomplete")
    finally:
        service.close()
    return records
