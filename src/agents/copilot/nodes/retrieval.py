"""Bounded hybrid retrieval with lazy, once-per-request readiness."""

import asyncio

from src.agents.copilot.nodes._shared import _lookup_date, _profile, _runtime, observed
from src.agents.copilot.nodes.planning import _signature, validate_plan
from src.agents.copilot.runtime import CopilotDependencyError, bounded_io
from src.agents.copilot.tools import get_bm25_search_engine, get_dense_search_engine
from src.config import get_settings
from src.knowledge.index_readiness import check_copilot_index
from src.observability import annotate, span


async def _ensure_snapshot(state):
    if state.get("snapshot") is not None:
        return state["snapshot"]
    with span("readiness"):
        snapshot = await bounded_io(
            state.get("readiness_loader") or check_copilot_index, _runtime(state).timeout(45, reserve_seconds=10)
        )
    annotate(corpus_hash=snapshot.fingerprint, document_count=len(snapshot.documents), chunk_count=len(snapshot.chunks))
    return snapshot


async def _search(search, state):
    kwargs = search.model_dump(exclude={"requirement_ids"})
    profile = _profile(state)
    timeout = _runtime(state).timeout(get_settings().retrieval_timeout_seconds, reserve_seconds=10)

    async def branch(factory, name, top_k):
        with span(
            "retrieval." + name,
            branch=name,
            top_k=top_k,
            retrieval_round=state.get("retrieval_rounds", 0) + 1,
            search_index=state.get("search_index", 0),
        ) as metadata:
            hits = await bounded_io(
                lambda: factory().search(**kwargs, top_k=top_k, target_date=_lookup_date(state)), timeout
            )
            metadata["result_count"] = len(hits)
            return hits

    results = await asyncio.gather(
        branch(get_dense_search_engine, "dense", profile.dense_top_k),
        branch(get_bm25_search_engine, "bm25", profile.bm25_top_k),
        return_exceptions=True,
    )
    errors = [name for name, result in zip(("dense", "bm25"), results) if isinstance(result, Exception)]
    if len(errors) == 2:
        raise CopilotDependencyError("both retrieval dependencies unavailable")
    return {
        "dense": [] if isinstance(results[0], Exception) else results[0],
        "bm25": [] if isinstance(results[1], Exception) else results[1],
        "requirement_ids": getattr(search, "requirement_ids", []),
        "errors": errors,
    }


@observed
async def retrieve_documents(state):
    snapshot = await _ensure_snapshot(state)
    current = {**state, "snapshot": snapshot}
    runtime = _runtime(state)
    if state.get("retrieval_mode") == "read_context":
        registry = {h["citation_id"]: h for h in state["evidence_registry"]}
        anchors = state.get("read_anchor_ids", [])
        if not anchors or len(anchors) > 2 or any(cid not in registry for cid in anchors):
            raise CopilotDependencyError("invalid read context anchor")
        with span("retrieval.read_context", branch="bm25") as metadata:
            hits = await bounded_io(
                lambda: [
                    h
                    for cid in anchors
                    for h in get_bm25_search_engine().read_context(
                        registry[cid]["chunk_id"], _lookup_date(state), include_header=True
                    )
                ],
                runtime.timeout(get_settings().retrieval_timeout_seconds, reserve_seconds=10),
            )
            metadata["result_count"] = len(hits)
        if any(not any(h["chunk_id"] == registry[cid]["chunk_id"] for h in hits) for cid in anchors):
            raise CopilotDependencyError("read context anchor missing")
        return {
            "snapshot": snapshot,
            "new_hits": hits,
            "raw_search_results": [],
            "route": "select_evidence",
        }
    if state.get("retrieval_rounds", 0) >= get_settings().copilot_max_retrieval_rounds:
        raise CopilotDependencyError("retrieval round limit")
    try:
        validate_plan(state["search_plan"], current)
    except ValueError as exc:
        raise CopilotDependencyError("retrieval plan no longer valid") from exc
    searches = state["search_plan"].searches
    if state.get("tool_calls", 0) + len(searches) > get_settings().copilot_max_search_calls:
        raise CopilotDependencyError("search call limit")
    results = await asyncio.gather(
        *[_search(s, {**current, "search_index": i}) for i, s in enumerate(searches)], return_exceptions=True
    )
    if any(isinstance(r, Exception) for r in results):
        raise CopilotDependencyError("retrieval query unavailable")
    return {
        "snapshot": snapshot,
        "raw_search_results": results,
        "new_hits": [],
        "retrieval_rounds": state.get("retrieval_rounds", 0) + 1,
        "tool_calls": state.get("tool_calls", 0) + len(searches),
        "search_signatures": [*state.get("search_signatures", []), *map(_signature, searches)],
        "retrieval_errors": state.get("retrieval_errors", 0) + sum(len(r["errors"]) for r in results),
        "route": "select_evidence",
    }
