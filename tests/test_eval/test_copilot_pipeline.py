"""Evaluation integrity without provider requests or historical result dependencies."""

import copy
import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from eval.copilot_eval.adjudication import apply_decisions
from eval.copilot_eval.benchmark_judge import (
    Judge,
    Ready,
    enforce_technical_outcome,
    feedback_scores,
    payload,
    stages,
)
from eval.copilot_eval.benchmark_run import identity, preserved_attempt, validate_inputs
from eval.copilot_eval.config import DEFAULT_CALIBRATION, DEFAULT_MODEL, RunConfig, case_path, matched_outcomes
from eval.copilot_eval.experiment import digest, save
from eval.copilot_eval.report import generate, summarize


@pytest.fixture
def inputs(tmp_path):
    text = "Device A standard has a two-year warranty."
    corpus = tmp_path / "corpus.json"
    save(corpus, [{"document_id": "D", "content": text, "source": "manual", "version": "1", "status": "active"}])
    case = {
        "case_id": "CASE1",
        "group": "on_topic",
        "category": "warranty",
        "question_type": "factual",
        "query": "What warranty applies to Device A standard?",
        "target_date": None,
        "notes": "",
        "ground_truth": text,
        "audit_status": "valid",
        "expected": {
            "behavior": "answer",
            "supporting_document_ids": ["D"],
            "forbidden_document_ids": [],
            "required_facts": ["Two years for the standard variant"],
            "policy_version": {"required_document_id": None, "forbidden_document_ids": []},
        },
        "reference_contexts": [text],
        "reference_context_sources": [
            {
                "context_index": 0,
                "document_id": "D",
                "corpus_file": "data/knowledge/corpus.json",
                "source": "manual",
                "version": "1",
                "status": "active",
                "start_char": 0,
                "end_char": len(text),
            }
        ],
    }
    dataset = tmp_path / "dataset.json"
    save(dataset, {"benchmark_version": "fixture-1", "cases": [case]})
    config = RunConfig(tmp_path / "new-run", "one-run-project", dataset=dataset, corpus=corpus, suite="development")
    audit = tmp_path / "audit.json"
    save(
        audit,
        {
            "provenance_pass": True,
            "content_review_complete": True,
            "benchmark_after": digest(dataset),
            "benchmark_before": digest(dataset),
            "corpus": digest(corpus),
        },
    )
    return config, audit, case


def test_provenance_gate_uses_explicit_corpus_and_rejects_stale_audit(inputs):
    config, audit, case = inputs
    assert validate_inputs(config, audit)[0]["cases"] == [case]
    config.corpus.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        validate_inputs(config, audit)
    assert not config.run_dir.exists()


def test_identity_tracks_data_and_budget_changes(inputs, monkeypatch):
    from eval.copilot_eval import benchmark_run

    config, _, _ = inputs
    monkeypatch.setattr(benchmark_run, "runtime_configuration", lambda: {"copilot_budget": 2})
    before = identity(config)
    monkeypatch.setattr(benchmark_run, "runtime_configuration", lambda: {"copilot_budget": 3})
    assert identity(config) != before
    config.dataset.write_text(config.dataset.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert identity(config)["benchmark_hash"] != before["benchmark_hash"]


def test_closed_run_rejects_nested_save_and_leaves_original_bytes(tmp_path):
    closed = tmp_path / "closed"
    save(closed / "data.json", {"original": True})
    (closed / "CLOSED").touch()
    before = (closed / "data.json").read_bytes()
    with pytest.raises(ValueError, match="read-only"):
        save(closed / "data.json", {"overwrite": True})
    with pytest.raises(ValueError, match="read-only"):
        save(closed / "evaluation/new.json", {})
    assert (closed / "data.json").read_bytes() == before


@pytest.mark.parametrize(
    "rows",
    [
        [{"case_id": "A"}],
        [{"case_id": "B"}, {"case_id": "A"}],
        [{"case_id": "A"}, {"case_id": "A"}],
        [{"case_id": "A"}, {"case_id": "B"}, {"case_id": "C"}],
    ],
)
def test_incomplete_reordered_or_duplicate_outcomes_are_rejected(rows):
    with pytest.raises(ValueError, match="exactly one"):
        matched_outcomes([{"case_id": "A"}, {"case_id": "B"}], rows)


def test_resume_never_replaces_failed_or_interrupted_attempt(tmp_path):
    failed = {"case_id": "A", "error_type": "TimeoutError", "request_id": "original"}
    save(tmp_path / "A.json", failed)
    assert preserved_attempt(tmp_path, {"case_id": "A"}) == failed
    save(tmp_path / "B.started.json", {"case_id": "B", "request_id": "original-b"})
    row = preserved_attempt(tmp_path, {"case_id": "B"})
    assert row["error_type"] == "InterruptedAttempt"
    assert row["request_id"] == "original-b"
    assert preserved_attempt(tmp_path, {"case_id": "B"}) == row


@pytest.mark.parametrize("bad_id", ["../escape", "A/B", "A\\B", "", "/absolute"])
def test_case_ids_cannot_escape_output_directory(tmp_path, bad_id):
    with pytest.raises(ValueError, match="Unsafe"):
        case_path(tmp_path, bad_id)


def client_response(model, parsed):
    response = SimpleNamespace(
        model=model, usage=None, id="response", choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))]
    )
    parse = AsyncMock(return_value=response)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))


@pytest.mark.asyncio
async def test_judge_actual_model_mismatch_is_fatal_without_fallback(tmp_path):
    client = client_response("different/model", Ready(ready=True))
    judge = Judge(tmp_path, client=client)
    with pytest.raises(RuntimeError, match="model mismatch"):
        await judge.ask(Ready, "ready")
    assert client.chat.completions.parse.await_count == 1
    assert judge.calls[0]["requested_model"] == DEFAULT_MODEL
    assert judge.calls[0]["actual_model"] == "different/model"


@pytest.mark.asyncio
async def test_schema_failure_retries_same_model_and_retains_both_attempts(tmp_path):
    client = client_response(DEFAULT_MODEL, None)
    judge = Judge(tmp_path, client=client)
    with pytest.raises(ValueError, match="structured output"):
        await judge.ask(Ready, "ready")
    assert len(judge.calls) == 2
    assert all(call.kwargs["model"] == DEFAULT_MODEL for call in client.chat.completions.parse.await_args_list)
    assert all(call["error_type"] == "ValueError" for call in judge.calls)


@pytest.mark.asyncio
async def test_judge_uses_parent_project_instead_of_creating_judge_project(tmp_path, monkeypatch):
    trees = []

    class Tree:
        def __init__(self, **kwargs):
            trees.append(kwargs)

        def post(self):
            pass

        def end(self, **kwargs):
            pass

        def patch(self):
            pass

    monkeypatch.setattr("langsmith.run_trees.RunTree", Tree)
    parent = object()
    service = SimpleNamespace(project="agent-experiment", client=object())
    judge = Judge(tmp_path, service, parent, client=client_response(DEFAULT_MODEL, Ready(ready=True)))
    assert (await judge.ask(Ready, "ready")).ready
    assert trees[0]["project_name"] == "agent-experiment"
    assert trees[0]["parent_run"] is parent


def test_invalid_and_unresolved_are_excluded_from_cloud_quality_denominator():
    for status in ("invalid", "unresolved"):
        assert feedback_scores({"audit_status": status}, {"custom": {"overall": "pass"}}) == {"benchmark.scorable": 0}
    assert feedback_scores({"audit_status": "valid"}, {"evaluator_error": "TimeoutError"})["benchmark.pass"] == 0


def test_terminal_technical_refusal_cannot_pass_but_recovered_answer_can():
    review = {"custom": {"overall": "pass"}}
    row = {
        "status": "abstained",
        "reason_code": "verification_failed",
        "trace": [{"llm": True, "error_type": "ContractError"}],
    }
    enforce_technical_outcome(row, review)
    assert review["custom"]["overall"] == "fail"
    assert review["custom"]["diagnosis"] == "technical_error"
    recovered = {"custom": {"overall": "pass"}}
    enforce_technical_outcome({**row, "status": "answered"}, recovered)
    assert recovered["custom"]["overall"] == "pass"


def test_included_evidence_excluded_by_packing_remains_in_jev_stage():
    hit = {"chunk_id": "included", "content": "Source", "document_id": "D"}
    nodes = [
        {"node": "retrieve_documents", "state": {"raw_search_results": [{"dense": [hit]}]}},
        {
            "node": "select_evidence",
            "state": {
                "candidate_evidence": [hit],
                "evidence_registry": [],
                "evidence_selection_diagnostics": [
                    {"bundle_chunk_ids": ["included"], "jev": {"route": "include"}, "reason": "context_budget"}
                ],
            },
        },
        {"node": "build_context", "state": {"route": "generate_answer", "selected_evidence": []}},
    ]
    exported = stages(nodes, {"status": "abstained"})
    assert exported["jev_kept"] == [hit]
    assert exported["packed"] == []


def test_calibration_is_standalone_and_labelled_before_benchmark():
    fixtures = json.loads(DEFAULT_CALIBRATION.read_text(encoding="utf-8"))
    assert len(fixtures) >= 2
    for fixture in fixtures:
        assert fixture["reviewer"]
        assert fixture["expected"] in {"pass", "fail"}
        data = payload(fixture["case"], fixture["row"], fixture["nodes"])
        assert data["evidence"] and data["goals"]
    assert "eval/results/" not in DEFAULT_CALIBRATION.read_text(encoding="utf-8")


def test_reports_do_not_hide_unjudged_cases_or_goals(inputs):
    _, _, case = inputs
    other = {**case, "case_id": "CASE2"}
    excluded = {**case, "case_id": "UNRESOLVED", "audit_status": "unresolved"}
    review = {
        "case_id": "CASE1",
        "custom": {
            "overall": "pass",
            "fact_correctness": 1,
            "critical_issues": [],
            "goals": [{"index": 0, "raw": "sufficient"}],
        },
    }
    cases = [case, other, excluded]
    result = summarize(cases, [{"case_id": c["case_id"]} for c in cases], [review])
    assert result["case_pass"] == {"numerator": 1, "denominator": 2, "value": 0.5}
    assert result["metrics"]["custom.fact_correctness"]["na_or_error"] == 1
    assert result["goal_stage_support"]["raw"]["statuses"]["unknown"] == 1
    assert result["goal_stage_support"]["raw"]["sufficient"]["denominator"] == 2
    assert result["evaluator_errors"] == ["CASE2"]
    assert not all(result["gates"].values())


def test_adjudication_requires_exact_before_and_hash_without_mutating_raw():
    raw = [{"case_id": "A", "custom": {"overall": "fail"}, "ragas": {"faithfulness": 0.5}}]
    before = copy.deepcopy(raw)
    document = {
        "raw_scores_hash": "hash",
        "decisions": [
            {
                "case_id": "A",
                "reviewer": "source reviewer",
                "reason": "Source/trace establishes an evaluator misreading",
                "before": {"overall": "fail"},
                "after": {"overall": "pass"},
            }
        ],
    }
    reviewed = apply_decisions(raw, document, "hash")
    assert raw == before
    assert reviewed[0]["ragas"] == raw[0]["ragas"]
    with pytest.raises(ValueError, match="different raw"):
        apply_decisions(raw, document, "wrong")
    document["decisions"][0]["before"] = {"overall": "pass"}
    with pytest.raises(ValueError, match="before-state"):
        apply_decisions(raw, document, "hash")


def test_closed_run_report_can_only_write_to_external_directory(inputs, tmp_path):
    config, _, case = inputs
    save(config.run_dir / "manifest.json", {"project": config.project})
    save(config.run_dir / "cases.json", [case])
    save(config.run_dir / "results.json", [{"case_id": case["case_id"]}])
    (config.run_dir / "CLOSED").touch()
    with pytest.raises(ValueError, match="read-only"):
        generate(config.run_dir)
    result = generate(config.run_dir, tmp_path / "external-report")
    assert not result["release_candidate_pass"]
    assert (tmp_path / "external-report/report.md").is_file()


@pytest.mark.asyncio
async def test_capture_and_score_resume_without_replacing_failed_attempts(inputs, monkeypatch):
    from eval.copilot_eval import benchmark_judge, benchmark_run, cloud
    from src.agents.copilot.graph import copilot_agent
    from src.knowledge import index_readiness

    config, audit, case = inputs
    save(config.run_dir / "preflight/audit-validation.json", json.loads(audit.read_text(encoding="utf-8")))
    save(
        config.run_dir / "preflight/preflight.json",
        {
            "passed": True,
            "identity": identity(config),
            "audit_hash": digest(config.run_dir / "preflight/audit-validation.json"),
        },
    )
    frozen = identity(config)
    feedback = []
    client = SimpleNamespace(
        read_run=lambda _: SimpleNamespace(dotted_order="original-root"),
        list_feedback=lambda **_: feedback,
        create_feedback=lambda run_id, **kw: (
            feedback.append(SimpleNamespace(id=str(len(feedback)), run_id=run_id, key=kw["key"], score=kw["score"]))
            or feedback[-1]
        ),
        flush=lambda **_: None,
    )
    service = SimpleNamespace(enabled=True, project=config.project, client=client, close=lambda: None)

    def experiment(cases, name, output, metadata):
        manifest = {**metadata, "project": name, "dataset_id": "dataset", "project_id": "project"}
        save(output / "cases.json", cases)
        save(output / "manifest.json", manifest)
        return service, {case["case_id"]: "example"}, manifest

    @contextmanager
    def graph_case(*args):
        yield SimpleNamespace(request_id="original-request", root=None)

    graph = AsyncMock(side_effect=TimeoutError("provider timeout"))
    monkeypatch.setattr(benchmark_run, "experiment", experiment)
    monkeypatch.setattr(benchmark_run, "graph_case", graph_case)
    monkeypatch.setattr(benchmark_run, "reconcile", lambda *_: True)
    monkeypatch.setattr(copilot_agent, "ainvoke", graph)
    monkeypatch.setattr("src.observability.TelemetryService", lambda *_: service)
    monkeypatch.setattr(
        index_readiness,
        "check_copilot_index",
        lambda: SimpleNamespace(fingerprint=digest(config.corpus), documents=[1], chunks={"one": 1}),
    )
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(
            Process=lambda: SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=100)),
            virtual_memory=lambda: SimpleNamespace(available=1000),
        ),
    )

    original = await benchmark_run.execute(config)
    assert original[0]["error_type"] == "TimeoutError"
    agent_input = graph.await_args.args[0]
    assert set(agent_input) == {"query", "target_date", "history", "snapshot", "runtime", "request_id"}
    assert not {"expected", "ground_truth", "reference_contexts"} & agent_input.keys()
    assert await benchmark_run.execute(config) == original
    assert graph.await_count == 1
    assert identity(config) == frozen

    custom = AsyncMock(return_value={"overall": "pass", "goals": [], "reason": "fake judge"})
    monkeypatch.setattr(benchmark_judge, "custom", custom)
    monkeypatch.setattr(benchmark_judge, "ragas_scores", AsyncMock(return_value={"faithfulness": None}))
    monkeypatch.setattr(cloud, "OfflineTelemetry", lambda *_: service)
    judge_client = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(benchmark_judge, "AsyncOpenAI", lambda **_: judge_client)
    monkeypatch.setattr("langsmith.run_trees.RunTree.from_dotted_order", lambda *_, **__: object())
    await benchmark_judge.evaluate(config)
    await benchmark_judge.evaluate(config)
    assert custom.await_count == 1
    scored = json.loads((config.run_dir / "evaluation/CASE1.json").read_text(encoding="utf-8"))
    assert scored["custom"]["overall"] == "fail"
    assert scored["custom"]["diagnosis"] == "technical_error"
    assert len([f for f in feedback if f.key == "benchmark.pass"]) == 1
    assert next(f for f in feedback if f.key == "benchmark.pass").score == 0
