"""Regressions for late candidates, shared decisions and source-condition integrity."""

import json
import time
from datetime import date
from types import SimpleNamespace

import pytest

from src.agents.copilot import jev
from src.agents.copilot.context import format_selected_context
from src.agents.copilot.nodes import evidence
from src.agents.copilot.runtime import CopilotDependencyError, RuntimeBudget
from src.agents.copilot.tools import _make_hit
from src.config import get_settings
from src.knowledge.index_readiness import load_snapshot
from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk
from src.knowledge.source_context import source_context_chunks
from tests.test_agents.test_copilot_jev import hit, mock_provider, response, state


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setattr(get_settings(), "copilot_evidence_selection_strategy", "jev_context")
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "fake-key")


@pytest.mark.asyncio
async def test_late_policy_candidate_reaches_jev_and_can_win(monkeypatch):
    anchors = [hit(str(i), document_type="policy") for i in range(8)]
    reads, judged = [], []

    def read(cid, lookup):
        reads.append(cid)
        return [anchors[int(cid)], hit("scope", content="Applies to the new car only.")]

    monkeypatch.setattr(evidence, "get_bm25_search_engine", lambda: SimpleNamespace(read_context=read))

    def provider(request):
        ids = {h["chunk_id"] for h in json.loads(request.content)["state"]["source_bundle"]}
        judged.append(ids)
        return response(request, supports_R2=0.99 if "7" in ids else 0.1)

    mock_provider(monkeypatch, provider)
    current = state(anchors)
    result = await evidence.select_evidence(current)
    assert len(reads) == 8 and len(judged) == 8
    assert "7" in {h["chunk_id"] for h in result["selected_evidence"]}
    assert all(d["reason"] != "context_unavailable" for d in result["evidence_selection_diagnostics"])
    assert len(result["selected_evidence"]) <= 4
    reads.clear()
    await evidence.select_evidence({**current, **result})
    assert not reads  # Local preparation is request-cached, separately from Jev.


@pytest.mark.asyncio
async def test_standalone_prefix_is_used_without_reading_parent(monkeypatch):
    def forbidden():
        raise AssertionError("A complete spec row already has its header")

    monkeypatch.setattr(evidence, "get_bm25_search_engine", forbidden)

    def provider(request):
        assert json.loads(request.content)["state"]["source_bundle"][0]["context_prefix"] == "Giá kèm pin, gồm VAT"
        return response(request)

    mock_provider(monkeypatch, provider)
    current = state([hit("complete", context_prefix="Giá kèm pin, gồm VAT")])
    result = await evidence.select_evidence(current)
    built = await evidence.build_context({**current, **result})
    assert built["route"] == "generate_answer" and "Giá kèm pin, gồm VAT" in built["answer_context"]


@pytest.mark.asyncio
async def test_preparation_timeout_does_not_expose_incomplete_policy(monkeypatch):
    async def timeout(*args):
        raise TimeoutError

    monkeypatch.setattr(evidence, "bounded_io", timeout)
    bodies = []

    def provider(request):
        bodies.append(json.loads(request.content))
        return response(request)

    mock_provider(monkeypatch, provider)
    result = await evidence.select_evidence(state([hit("policy", document_type="policy"), hit("complete")]))
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["complete"]
    assert len(bodies) == 1 and bodies[0]["state"]["source_bundle"][0]["chunk_id"] == "complete"


@pytest.mark.asyncio
async def test_shared_full_bundle_is_billed_once_and_mapped_to_all_anchors(monkeypatch):
    calls = []

    def provider(request):
        calls.append(json.loads(request.content))
        return response(request, contains_prompt_injection=0.99)

    mock_provider(monkeypatch, provider)
    a, b, c = hit("a"), hit("b"), hit("c")
    current = state([a, b, c])
    decisions, cache = await jev.assess_bundles(current, [(a, [a, b]), (b, [b, a])])
    assert len(calls) == 1 and len(cache) == 1
    assert decisions["a"]["route"] == decisions["b"]["route"] == "exclude"
    assert decisions["b"]["shared_decision"]
    events = [e for e in current["runtime"].events if e.get("decision")]
    assert len(events) == 1 and events[0]["anchor_count"] == 2 and events[0]["cost"] == 0.0000042
    await jev.assess_bundles({**current, "jev_assessment_cache": cache}, [(b, [b, a])])
    assert len(calls) == 1  # Canonical order also applies to the request cache.
    await jev.assess_bundles(current, [(a, [a, b]), (c, [b, c])])
    assert len(calls) == 3  # Partial overlap is not an equivalent bundle.


@pytest.mark.asyncio
async def test_changed_source_content_or_date_invalidates_shared_decision(monkeypatch):
    calls = []

    def provider(request):
        calls.append(request)
        return response(request)

    mock_provider(monkeypatch, provider)
    a, b = hit("a"), hit("b")
    current = state([a, b])
    _, cache = await jev.assess_bundles(current, [(a, [a, b])])
    await jev.assess_bundles({**current, "jev_assessment_cache": cache}, [(b, [hit("a", content="Different"), b])])
    await jev.assess_bundles({**current, "jev_assessment_cache": cache, "target_date": "2026-10-16"}, [(b, [b, a])])
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_real_policy_snapshot_preserves_scope_and_deduplicates_calls(monkeypatch):
    snapshot = load_snapshot()
    ids = ["POLICY_CHARGING_VINFAST_20260919_" + str(i) for i in (2, 3)]
    anchors = [_make_hit(snapshot.chunks[cid], 1, i + 1, "dense") for i, cid in enumerate(ids)]
    calls = []

    def provider(request):
        calls.append(json.loads(request.content))
        return response(request)

    def forbidden():
        raise AssertionError("Use the verified snapshot, not a second corpus load")

    monkeypatch.setattr(evidence, "get_bm25_search_engine", forbidden)
    mock_provider(monkeypatch, provider)
    result = await evidence.select_evidence({**state(anchors), "snapshot": snapshot})
    assert len(calls) == 1
    expected = {"POLICY_CHARGING_VINFAST_20260919_" + str(i) for i in (1, 2, 3, 4)}
    assert {h["chunk_id"] for h in result["selected_evidence"]} == expected
    assert "10 ngày" in format_selected_context(result["selected_evidence"])
    assert all(d["jev"]["route"] == "include" for d in result["evidence_selection_diagnostics"])


@pytest.mark.asyncio
async def test_build_context_never_reselects_even_when_jev_degraded(monkeypatch):
    def forbidden(*args):
        raise AssertionError("Packaging must not trigger another evidence decision")

    monkeypatch.setattr(evidence, "schedule_corrective", forbidden)
    source = hit("same", citation_id="C1")
    current = {
        **state([]),
        "selected_evidence": [source, source],
        "jev_status": "degraded",
        "overflow_anchor_ids": ["C2"],
    }
    built = await evidence.build_context(current)
    assert built["route"] == "generate_answer" and built["answer_context"].count("[C1]") == 1
    monkeypatch.setattr(evidence, "_profile", lambda _: SimpleNamespace(evidence_blocks=4, context_characters=10))
    with pytest.raises(CopilotDependencyError, match="context budget"):
        await evidence.build_context(current)  # Reject corrupt over-budget state, never truncate facts.


def chunk(cid, index, section, content, document_type="price_list", effective_date="2026-01-01", **extra):
    return KnowledgeChunk(
        chunk_id=cid,
        document_id="doc",
        content=content,
        metadata=ChunkMetadata(
            chunk_id=cid,
            document_id="doc",
            title="Policy",
            document_type=document_type,
            product_model="ALL",
            source="test",
            effective_date=effective_date,
            chunk_index=index,
            section_id=section,
            section_title=section,
            **extra,
        ),
    )


def test_split_table_keeps_distant_header_without_unrelated_neighbors():
    title = chunk("title", 0, "Colours", "Colour options")
    header = chunk("header", 1, "Colours", "| Model | Price |\n| --- | --- |\n| A | 100 |")
    anchor = chunk("anchor", 9, "Colours", "| VF 5 | 10.000.000 VNĐ |", requires_context=True)
    unrelated = chunk("other", 10, "Another section", "Unrelated value")
    result = source_context_chunks(anchor, [title, header, anchor, unrelated], date(2026, 10, 17))
    assert {c.chunk_id for c in result} == {"title", "header", "anchor"}


def test_overview_keeps_distinct_source_branches_ahead_of_repeated_summary():
    sources = [
        hit("a", section="Specs > Alpha", citation_id="C1"),
        hit("b", section="Beta", citation_id="C2"),
        hit("b2", section="Specs > Beta", citation_id="C3"),
        hit("c", section="Specs > Gamma", citation_id="C4"),
    ]
    decisions = {s["chunk_id"]: {
        "route": "include", "support": {"R1": 0.96},
        "direct_support": {"R1": 0.8 if s["chunk_id"] in {"b", "b2"} else 0},
        "scores": {"contains_answer_evidence": 0.9},
    } for s in sources}
    profile = SimpleNamespace(evidence_blocks=3, context_characters=20000, context_tokens=20000)
    selected, *_ = evidence._choose_bundles(
        [(s, [s]) for s in sources], decisions, set(), profile, set(), {}, True, overview={"R1"},
    )
    ids = {s["chunk_id"] for s in selected}
    assert {"a", "c"} <= ids
    assert len(ids & {"b", "b2"}) == 1
    decisions["c"]["route"] = "exclude"
    decisions["c"]["reason"] = "jev_injection"
    selected, *_ = evidence._choose_bundles(
        [(s, [s]) for s in sources], decisions, set(), profile, set(), {}, True, overview={"R1"},
    )
    assert "c" not in {s["chunk_id"] for s in selected}


def test_complete_price_row_reuses_prefix_without_first_model_row():
    first = chunk("first", 0, "Prices", "VF 3: 296 triệu")
    anchor = chunk("anchor", 4, "Prices", "VF 5: 496 triệu", context_prefix="Giá kèm pin, gồm VAT")
    result = source_context_chunks(anchor, [first, anchor], date(2026, 10, 17))
    assert [c.chunk_id for c in result] == ["anchor"]


@pytest.mark.parametrize("anchor_section", ["Policy > Đối tượng áp dụng: mua mới", "Policy > Funding"])
def test_policy_does_not_import_another_audience_exception(anchor_section):
    anchor = chunk("new", 1, anchor_section, "New policy", document_type="policy")
    other = chunk("old", 2, "Policy > Đối tượng áp dụng: mua cũ > Điều kiện", "Old buyer only", document_type="policy")
    stale = chunk("stale", 3, anchor_section, "Old version", version="old", document_type="policy")
    future = chunk("future", 4, anchor_section, "Future", effective_date="2027-01-01", document_type="policy")
    result = source_context_chunks(anchor, [anchor, other, stale, future], date(2026, 10, 17))
    assert [c.chunk_id for c in result] == ["new"]


@pytest.mark.asyncio
async def test_exhausted_preparation_budget_keeps_standalone_sources(monkeypatch):
    mock_provider(monkeypatch, response)
    current = state([hit("policy", document_type="policy"), hit("standalone")])
    current["runtime"] = RuntimeBudget(time.monotonic() + 44)
    result = await evidence.select_evidence(current)
    assert [h["chunk_id"] for h in result["selected_evidence"]] == ["standalone"]
    assert result["jev_status"] == "degraded"
