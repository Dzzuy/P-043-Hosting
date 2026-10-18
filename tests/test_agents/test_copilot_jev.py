"""Provider contract, negative gating, coverage selection, budgets and degradation."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from src.agents.copilot import jev
from src.agents.copilot.nodes import evidence
from src.agents.copilot.state import Requirement
from src.config import get_settings


def hit(cid, **extra):
    return {
        "chunk_id": cid,
        "document_id": "doc",
        "content": f"Giá mẫu xe A: 500 triệu đồng. {cid}",
        "title": "Giá thử nghiệm",
        "section": "Giá",
        "page": None,
        "source_uri": "test",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "status": "active",
        "version": "1",
        "product_model": "ALL",
        "document_type": "product_specs",
        "policy_type": None,
        "competitor_model": None,
        "native_score": 1.0,
        "rank": 1,
        "retrieval_method": "dense",
        **extra,
    }


def state(hits):
    return {
        "query": "So sánh giá và bảo hành mẫu xe A",
        "resolved_date": "2026-10-17",
        "raw_search_results": [{"dense": hits, "bm25": [], "requirement_ids": ["R1"]}],
        "requirements": [
            Requirement(requirement_id="R1", description="Giá xe A"),
            Requirement(requirement_id="R2", description="Bảo hành xe A"),
        ],
        "customer_context": "PRIVATE_CRM",
        "history": [{"content": "PRIVATE_HISTORY"}],
    }


def mock_provider(monkeypatch, callback):
    original = httpx.AsyncClient
    monkeypatch.setattr(jev.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(callback), **kw))


def response(request, **overrides):
    import json

    body = json.loads(request.content)
    scores = {
        k: 0.9 if k in {"is_relevant", "contains_answer_evidence", "supports_R1"} else 0.1 for k in body["questions"]
    }
    scores.update(overrides)
    return httpx.Response(
        200,
        json={
            "model": "typesafe/jev-1.14-20261014",
            "provider": "TypeSafe",
            "answers": {k: {"type": "noul", "noul": v} for k, v in scores.items()},
            "usage": {"input_tokens": 100, "output_tokens": 20, "cost": 0.0000042},
        },
    )


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "copilot_evidence_selection_strategy", "jev_context")
    monkeypatch.setattr(settings, "openrouter_api_key", "fake-key")
    monkeypatch.setattr(settings, "copilot_jev_concurrency", 2)


@pytest.mark.asyncio
async def test_native_endpoint_parallel_limit_cache_and_no_crm(monkeypatch):
    import json

    calls, active, peak = [], 0, 0

    async def provider(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        calls.append(request)
        await asyncio.sleep(0.005)
        active -= 1
        return response(request)

    mock_provider(monkeypatch, provider)
    current = state([hit(str(i)) for i in range(4)])
    bundles = [(h, [h]) for h in current["raw_search_results"][0]["dense"]]
    results, cache = await jev.assess_bundles(current, bundles)
    assert len(calls) == 4 and peak == 2
    assert all(r["route"] == "include" for r in results.values())
    assert all(str(r.url) == jev.DECISIONS_URL for r in calls)
    body = json.loads(calls[0].content)
    assert body["model"] == "typesafe/jev-1.14"
    assert "supports_R1" in body["questions"] and "supports_R2" in body["questions"]
    assert "PRIVATE" not in calls[0].content.decode()
    await jev.assess_bundles({**current, "jev_assessment_cache": cache}, bundles)
    assert len(calls) == 4
    # A changed source or question must not reuse an old decision.
    await jev.assess_bundles({**current, "query": "Khác", "jev_assessment_cache": cache}, bundles[:1])
    assert len(calls) == 5


@pytest.mark.asyncio
async def test_selects_requirement_diversity_and_preserves_full_context(monkeypatch):
    anchors = [hit("price"), hit("price2"), hit("warranty", requires_context=True)]
    monkeypatch.setattr(
        evidence, "_profile", lambda _: SimpleNamespace(candidate_pool=3, evidence_blocks=3, context_characters=6000)
    )
    monkeypatch.setattr(
        evidence,
        "get_bm25_search_engine",
        lambda: SimpleNamespace(read_context=lambda *args, **kwargs: [anchors[2], hit("condition")]),
    )

    def provider(request):
        import json

        bundle = json.loads(request.content)["state"]["source_bundle"]
        if any(h["chunk_id"] == "warranty" for h in bundle):
            assert len(bundle) == 2
            return response(request, supports_R1=0.1, supports_R2=0.95)
        return response(request)

    mock_provider(monkeypatch, provider)
    result = await evidence.select_evidence(state(anchors))
    assert {h["chunk_id"] for h in result["selected_evidence"]} == {"price", "warranty", "condition"}
    supports = {rid for d in result["evidence_selection_diagnostics"] if d["reason"] == "selected" for rid in d["jev"]["support"]}
    assert supports == {"R1", "R2"}
    built = await evidence.build_context({**state(anchors), **result, "generation_count": 1})
    assert built["route"] == "generate_answer" and "Giá mẫu xe" in built["answer_context"]


@pytest.mark.asyncio
async def test_negative_judgments_never_fall_back_and_request_targeted_search(monkeypatch):
    mock_provider(monkeypatch, lambda r: response(r, is_relevant=0.1, contains_answer_evidence=0.1, supports_R1=0.1))
    current = state([hit("irrelevant")])
    result = await evidence.select_evidence(current)
    assert result["jev_status"] == "ok" and not result["selected_evidence"]
    assert result["evidence_selection_diagnostics"][0]["reason"] == "jev_irrelevant"
    correction = await evidence.build_context({**current, **result})
    assert correction["route"] == "plan_queries"
    assert correction["corrective_retrieval_count"] == 1


@pytest.mark.asyncio
async def test_partial_bundle_coverage_does_not_force_search_before_grounding(monkeypatch):
    # Two prices can jointly answer a difference even if no individual bundle
    # supports the whole calculation. The checker must make that decision.
    mock_provider(monkeypatch, lambda r: response(r, supports_R1=0.95, supports_R2=0.1))
    current = state([hit("price")])
    result = await evidence.select_evidence(current)
    built = await evidence.build_context({**current, **result, "overflow_anchor_ids": ["C1"]})
    assert built["route"] == "generate_answer"
    assert not built.get("corrective_retrieval_count")


@pytest.mark.asyncio
async def test_one_failed_bundle_does_not_restore_successfully_excluded_bundle(monkeypatch):
    def provider(request):
        import json

        cid = json.loads(request.content)["state"]["source_bundle"][0]["chunk_id"]
        return httpx.Response(429) if cid == "outage" else response(request, contains_prompt_injection=0.99)

    mock_provider(monkeypatch, provider)
    result = await evidence.select_evidence(state([hit("injected"), hit("outage")]))
    assert result["jev_status"] == "degraded"
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["outage"]


@pytest.mark.asyncio
async def test_conflicting_premise_is_retained_separately_and_budgeted(monkeypatch):
    mock_provider(monkeypatch, lambda r: response(r, contradicts_query_premise=0.99))
    current = state([hit("refutation")])
    result = await evidence.select_evidence(current)
    assert result["jev_conflict_chunk_ids"] == ["refutation"]
    built = await evidence.build_context({**current, **result, "generation_count": 1})
    assert "BÁC BỎ GIẢ ĐỊNH" in built["answer_context"] and "[C1]" in built["answer_context"]
    assert len(built["answer_context"]) <= 6000
    monkeypatch.setattr(
        evidence, "_profile", lambda _: SimpleNamespace(candidate_pool=2, evidence_blocks=1, context_characters=100)
    )
    result = await evidence.select_evidence(current)
    assert not result["selected_evidence"]
    assert result["evidence_selection_diagnostics"][0]["reason"] == "context_budget"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["missing", "malformed", "nan", "timeout", "http", "usage"])
async def test_provider_failures_fall_back_in_rrf_order_without_guessing_scores(monkeypatch, mode):
    async def provider(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("test")
        if mode == "http":
            return httpx.Response(401)
        if mode == "usage":
            data = response(request).json()
            data["usage"] = None
            return httpx.Response(200, json=data)
        if mode == "nan":
            return httpx.Response(
                200, content=b'{"model":"typesafe/jev-1.14","answers":{"is_relevant":{"type":"noul","noul":NaN}}}'
            )
        return httpx.Response(200, json={"answers": {}})

    mock_provider(monkeypatch, provider)
    if mode == "missing":
        monkeypatch.setattr(get_settings(), "openrouter_api_key", "")
    result = await evidence.select_evidence(state([hit("first"), hit("second")]))
    assert result["jev_status"] == "degraded"
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["first", "second"]
    assert all(not d["jev"]["scores"] for d in result["evidence_selection_diagnostics"])


@pytest.mark.parametrize("value", [True, "0.9", float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_probabilities_are_rejected(value):
    with pytest.raises(ValueError):
        jev.NoulAnswer(type="noul", noul=value)


def test_selection_cache_identity_changes_with_strategy_model_and_thresholds(monkeypatch):
    settings = get_settings()
    identities = [jev.selection_identity(settings)]
    monkeypatch.setattr(settings, "copilot_jev_model", "typesafe/jev-1.13")
    identities.append(jev.selection_identity(settings))
    monkeypatch.setattr(settings, "copilot_jev_evidence_min", 0.8)
    identities.append(jev.selection_identity(settings))
    monkeypatch.setattr(settings, "copilot_evidence_selection_strategy", "rrf_context")
    identities.append(jev.selection_identity(settings))
    assert len(set(identities)) == 4
