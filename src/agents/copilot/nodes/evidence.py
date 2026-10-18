"""One source preparation path; Jev selects bundles, RRF supplies order and fallback."""

import hashlib
import json
from itertools import combinations, zip_longest

from src.agents.copilot.context import (
    context_fits,
    estimate_context_tokens,
    evidence_fingerprints,
    format_selected_context,
)
from src.agents.copilot.jev import assess_bundles
from src.agents.copilot.nodes._shared import (
    _lookup_date,
    _profile,
    _runtime,
    _valid_evidence_date,
    _valid_evidence_scope,
    can_search_corrective,
    observed,
    schedule_corrective,
)
from src.agents.copilot.runtime import CopilotDependencyError, bounded_io
from src.agents.copilot.tools import (
    build_evidence_context,
    get_bm25_search_engine,
    reciprocal_rank_fusion,
)
from src.config import get_settings
from src.observability import annotate, event, span


def _merge_evidence(state, hits):
    registry = {h["chunk_id"]: dict(h) for h in state.get("evidence_registry", [])}
    for hit in hits:
        if not _valid_evidence_date(hit, state) or not _valid_evidence_scope(hit, state):
            continue
        if state.get("snapshot") is not None:
            from src.agents.copilot.tools import _make_hit

            chunk = state["snapshot"].chunks.get(hit["chunk_id"])
            if chunk is None:
                raise CopilotDependencyError("retrieved chunk outside verified snapshot")
            expected = _make_hit(chunk, 0, 1, "bm25")
            keys = set(expected) - {"native_score", "rank", "retrieval_method"}
            if any(hit.get(key) != expected[key] for key in keys):
                raise CopilotDependencyError("retrieved content or metadata differs from snapshot")
        old = registry.get(hit["chunk_id"])
        if old:
            old["search_requirement_ids"] = list(
                dict.fromkeys([*old.get("search_requirement_ids", []), *hit.get("search_requirement_ids", [])])
            )
        else:
            registry[hit["chunk_id"]] = {**hit, "citation_id": f"C{len(registry) + 1}"}
    result = list(registry.values())
    return result


async def _prepare_sources(state, anchors):
    """Prepare the whole pool in one bounded local read, independently of output caps."""
    runtime = _runtime(state)
    cache = state.setdefault("parent_context_cache", {})
    date = _lookup_date(state)
    prepared, missing = {}, []
    for anchor in anchors:
        key = (anchor["chunk_id"], str(date), "dependencies-v3")
        if key in cache:
            prepared[anchor["chunk_id"]] = cache[key]
        elif not anchor.get("requires_context") and anchor.get("document_type") not in {"policy", "price_list"}:
            # context_prefix is already sent to Jev and the generator.
            prepared[anchor["chunk_id"]] = [anchor]
        else:
            missing.append(anchor)
    read_count = 0
    if missing and runtime.remaining() > 45:
        read_count = len(missing)

        def read_all():
            snapshot = state.get("snapshot")
            if snapshot is not None:
                from src.agents.copilot.tools import _make_hit
                from src.knowledge.source_context import source_context_chunks

                chunks = tuple(snapshot.chunks.values())
                return {
                    h["chunk_id"]: [
                        _make_hit(c, 0, i + 1, "bm25")
                        for i, c in enumerate(source_context_chunks(snapshot.chunks[h["chunk_id"]], chunks, date))
                    ]
                    for h in missing
                }
            engine = get_bm25_search_engine()
            return {h["chunk_id"]: engine.read_context(h["chunk_id"], date) for h in missing}

        try:
            with span("retrieval.prepare_bundles", branch="local"):
                prepared.update(await bounded_io(read_all, min(10.0, runtime.remaining() - 45)))
        except (TimeoutError, CopilotDependencyError):
            pass  # Keep standalone/cached sources; never invent missing dependencies.
    for anchor in missing:
        bundle = prepared.get(anchor["chunk_id"], [])
        if bundle:
            cache[(anchor["chunk_id"], str(date), "dependencies-v3")] = bundle
    return prepared, read_count


def _choose_bundles(bundles, assessments, unavailable, profile, recovery, provenance, use_jev, overview=()):
    """Continuous marginal utility, deduplicated cost, then bounded bundle swaps.

    These are selection heuristics, never verified requirement coverage. Mandatory
    dependencies are indivisible. No source gains priority merely by being cited
    in an earlier draft; that answer has its own immutable fallback snapshot.
    """
    injection = {
        h["chunk_id"]
        for anchor, bundle in bundles
        if assessments.get(anchor["chunk_id"], {}).get("reason") == "jev_injection"
        for h in bundle
    }
    blocked = {}
    for i, (anchor, bundle) in enumerate(bundles):
        decision = assessments.get(anchor["chunk_id"], {})
        if injection & {h["chunk_id"] for h in bundle}:
            blocked[i] = "jev_injection"
        elif anchor["chunk_id"] in unavailable:
            blocked[i] = "context_unavailable"
        elif decision.get("route") == "exclude":
            blocked[i] = decision["reason"]
    eligible = [i for i in range(len(bundles)) if i not in blocked]
    # Only standalone, complete blocks can alias. Prepared policy/price bundles
    # and anchors with dependencies stay indivisible, even if text is identical.
    # Compare all source metadata, retaining version, validity and scope exactly.
    aliases, representatives = {}, {}
    protected = {
        h["chunk_id"] for anchor, bundle in bundles
        if len(bundle) != 1 or anchor.get("requires_context")
        or anchor.get("document_type") in {"policy", "price_list"}
        for h in bundle
    }
    retrieval_keys = {
        "chunk_id", "citation_id", "rank", "native_score", "retrieval_method",
        "dense_score", "bm25_score", "rrf_score", "search_requirement_ids",
    }
    for i in eligible:
        anchor, bundle = bundles[i]
        if anchor["chunk_id"] in protected:
            continue
        key = (json.dumps({k: v for k, v in anchor.items() if k not in retrieval_keys}, sort_keys=True, default=str),
               assessments.get(anchor["chunk_id"], {}).get("route"))
        canonical = representatives.setdefault(key, anchor["chunk_id"])
        aliases[anchor["chunk_id"]] = canonical
    by_id = {h["chunk_id"]: h for _, bundle in bundles for h in bundle}

    def packed_bundle(bundle):
        return [by_id[aliases.get(h["chunk_id"], h["chunk_id"])] for h in bundle]

    scored = any(assessments.get(bundles[i][0]["chunk_id"], {}).get("scores") for i in eligible)
    cache = {}

    def evaluate(indices):
        key = tuple(sorted(indices))
        if key in cache:
            return cache[key]
        hits, conflicts, partial, direct, identities = {}, set(), {}, {}, set()
        scopes = {}
        generic, contradiction, fallback = 0.0, 0.0, 0.0
        for i in key:
            anchor, bundle = bundles[i]
            decision = assessments.get(anchor["chunk_id"], {})
            bundle = packed_bundle(bundle)
            hits.update((h["chunk_id"], h) for h in bundle)
            if decision.get("route") == "conflict":
                conflicts.update(h["chunk_id"] for h in bundle)
            identity = tuple(sorted(h["chunk_id"] for h in bundle))
            if identity in identities:
                continue
            identities.add(identity)
            for rid, score in decision.get("support", {}).items():
                partial.setdefault(rid, []).append(score)
                if rid in overview:
                    # A section leaf is a diversity hint, never verified variant
                    # coverage. Repeated summaries of the same leaf add no bonus.
                    leaf = (anchor.get("section") or anchor.get("title") or "").split(" > ")[-1]
                    scope = (anchor.get("product_model"), " ".join(leaf.casefold().split()))
                    values = scopes.setdefault(rid, {})
                    values[scope] = max(values.get(scope, 0), score)
            for rid, score in decision.get("direct_support", {}).items():
                direct[rid] = max(direct.get(rid, 0), score)
            scores = decision.get("scores", {})
            generic = max(generic, scores.get("contains_answer_evidence", 0))
            contradiction = max(contradiction, scores.get("contradicts_query_premise", 0))
            if not scores:
                fallback += 0.001 / (i + 1)
        utility = 0.05 * generic + 0.25 * contradiction + fallback
        for rid in partial.keys() | direct.keys():
            support = sorted(partial.get(rid, []), reverse=True)
            # Further sources can complement partial evidence. Diminishing
            # returns avoid treating repeated support as another complete goal.
            value = 2 * direct.get(rid, 0) ** 2
            if support:
                value += support[0] ** 2
                value += 0.15 * sum(score**2 / rank**2 for rank, score in enumerate(support[1:], 1))
            value += 0.75 * sum(
                score**2 / rank**0.5
                for rank, score in enumerate(sorted(scopes.get(rid, {}).values(), reverse=True), 1)
            )
            utility += value * (1.5 if rid in recovery else 1.0)
        selected = list(hits.values())
        context = format_selected_context(selected, conflicts)
        tokens = estimate_context_tokens(context)
        fits = (
            len(selected) <= profile.evidence_blocks
            and len(context) <= profile.context_characters
            and tokens <= getattr(profile, "context_tokens", profile.context_characters)
        )
        result = (utility, tokens, selected, conflicts, fits)
        cache[key] = result
        return result

    chosen = []
    if not scored:
        for i in eligible:
            if evaluate([*chosen, i])[4]:
                chosen.append(i)
    else:
        while True:
            before = evaluate(chosen)
            options = []
            for i in eligible:
                if i in chosen:
                    continue
                value, tokens, _, _, fits = evaluate([*chosen, i])
                gain = value - before[0]
                if fits and gain > 1e-9:
                    options.append((gain / max(1, tokens - before[1]) ** 0.5, i))
            if not options:
                break
            chosen.append(max(options, key=lambda item: item[0])[1])
        # One/two-for-one and one-for-two exchanges recover from early greedy
        # choices. Two passes cap CPU work even for a 40-anchor pool.
        for _ in range(2):
            best, best_value = chosen, evaluate(chosen)[0]
            pending = sorted((i for i in eligible if i not in chosen), key=lambda i: evaluate([i])[0], reverse=True)[
                :12
            ]
            removable = sorted(chosen, key=lambda i: best_value - evaluate([j for j in chosen if j != i])[0])[:8]
            for remove_count, add_count in ((1, 1), (2, 1), (1, 2)):
                for removed in combinations(removable, remove_count):
                    kept = [i for i in chosen if i not in removed]
                    for added in combinations(pending, add_count):
                        proposal = [*kept, *added]
                        value, _, _, _, fits = evaluate(proposal)
                        if fits and value > best_value + 1e-9:
                            best, best_value = proposal, value
            if best == chosen:
                break
            chosen = best
    _, _, selected, conflicts, _ = evaluate(chosen)
    selected_ids = {h["chunk_id"] for h in selected}
    diagnostics, rejected = [], []
    for i, (anchor, bundle) in enumerate(bundles):
        original_ids = [h["chunk_id"] for h in bundle]
        bundle = packed_bundle(bundle)
        included = bool(bundle) and {h["chunk_id"] for h in bundle} <= selected_ids
        reason = blocked.get(i) or (
            "selected"
            if included
            else ("context_budget" if not evaluate([*chosen, i])[4] else "lower_marginal_utility")
        )
        if i not in blocked and not included:
            rejected.append(anchor["chunk_id"])
        diagnostics.append(
            {
                "chunk_id": anchor["chunk_id"],
                "citation_id": anchor["citation_id"],
                "rank": anchor["rank"],
                "query_indices": provenance.get(anchor["chunk_id"], []),
                "search_requirement_ids": anchor.get("search_requirement_ids", []),
                "bundle_chunk_ids": [h["chunk_id"] for h in bundle],
                "original_bundle_chunk_ids": original_ids,
                "canonical_chunk_id": aliases.get(anchor["chunk_id"], anchor["chunk_id"]),
                "bundle_blocks": len(bundle),
                "bundle_characters": len(build_evidence_context(bundle)[0]),
                "reason": reason,
                **({"jev": assessments.get(anchor["chunk_id"], {})} if use_jev else {}),
            }
        )
    selected = [
        {**h, "search_requirement_ids": sorted({
            rid for anchor, _ in bundles
            if aliases.get(anchor["chunk_id"], anchor["chunk_id"]) == h["chunk_id"]
            for rid in anchor.get("search_requirement_ids", [])
        } | set(h.get("search_requirement_ids", [])))}
        for h in selected
    ]
    return selected, conflicts, diagnostics, rejected


@observed
async def select_evidence(state):
    profile = _profile(state)
    strategy = get_settings().copilot_evidence_selection_strategy
    use_jev = strategy == "jev_context"
    ranked = [
        [
            {**hit, "search_requirement_ids": result["requirement_ids"]}
            for hit in reciprocal_rank_fusion(
                result["dense"],
                result["bm25"],
                rrf_k=60,
                top_k=profile.candidate_pool,
                target_date=_lookup_date(state),
            )
        ]
        for result in state.get("raw_search_results", [])
    ]
    fair = [h for group in zip_longest(*ranked) for h in group if h]
    provenance, requirement_ids = {}, {}
    for query_index, hits in enumerate(ranked):
        for hit in hits:
            provenance.setdefault(hit["chunk_id"], []).append(query_index)
            requirement_ids.setdefault(hit["chunk_id"], set()).update(hit["search_requirement_ids"])

    recovery = set(state.get("recovery_requirement_ids", []))
    if recovery:
        # Retain old factual anchors as candidates, not pinned selections. A
        # fresh 24-hit search must not evict every previously verified price
        # before the selector can compare it with the new missing specifications.
        snapshot = state.get("verified_snapshot")
        verified = {c.citation_id for c in snapshot.citations} if snapshot else set()
        retained = sorted(state.get("candidate_evidence", []), key=lambda h: h.get("citation_id") not in verified)
        fair = [h for group in zip_longest(fair, retained) for h in group if h]
    previous = {h["chunk_id"]: h for h in state.get("evidence_registry", [])}
    rejected = [
        previous[cid]
        for cid in state.get("rejected_evidence_ids", [])
        if cid in previous and recovery & set(previous[cid].get("search_requirement_ids", []))
    ]
    first_targeted = [hits[0] for hits in ranked if hits] if recovery else []
    pool, seen = [], set()
    for hit in [
        *first_targeted,
        *rejected,
        *fair,
        *state.get("candidate_evidence", []),
        *state.get("selected_evidence", []),
    ]:
        if hit["chunk_id"] in seen or not _valid_evidence_date(hit, state) or not _valid_evidence_scope(hit, state):
            continue
        seen.add(hit["chunk_id"])
        pool.append(hit)
        if len(pool) == profile.candidate_pool:
            break
    registry = _merge_evidence(state, pool)
    # Duplicates beyond the global cap still contribute query linkage.
    for hit in registry:
        hit["search_requirement_ids"] = sorted(
            set(hit.get("search_requirement_ids", [])) | requirement_ids.get(hit["chunk_id"], set())
        )
    prepared, read_count = await _prepare_sources(state, pool)
    bundles, unavailable = [], set()
    for anchor in pool:
        expanded = prepared.get(anchor["chunk_id"], [])
        registry = _merge_evidence({**state, "evidence_registry": registry}, expanded)
        by_id = {h["chunk_id"]: h for h in registry}
        if (
            not expanded
            or anchor["chunk_id"] not in {h["chunk_id"] for h in expanded}
            or any(h["chunk_id"] not in by_id for h in expanded)
        ):
            unavailable.add(anchor["chunk_id"])
        bundles.append((by_id[anchor["chunk_id"]], [by_id[h["chunk_id"]] for h in expanded if h["chunk_id"] in by_id]))
    by_id = {h["chunk_id"]: h for h in registry}
    assessments, jev_cache = {}, {}
    if use_jev:
        assessments, jev_cache = await assess_bundles(
            state, [b for b in bundles if b[0]["chunk_id"] not in unavailable]
        )
    status = (
        (
            "degraded"
            if any(a["route"] == "unscored" for a in assessments.values()) or unavailable
            else "ok"
            if assessments
            else "no_candidates"
        )
        if use_jev
        else "disabled"
    )
    selected, conflict_ids, diagnostics, rejected = _choose_bundles(
        bundles, assessments, unavailable, profile, recovery, provenance, use_jev,
        overview={r.requirement_id for r in state.get("requirements", []) if r.kind == "fact" and r.variant is None},
    )
    for item in diagnostics:
        event(
            "retrieval.selection",
            selection_strategy=strategy,
            selection_reason=item["reason"],
            source_hash=hashlib.sha256(item["chunk_id"].encode()).hexdigest()[:16],
            citation_id=item["citation_id"],
            candidate_rank=item["rank"],
            bundle_blocks=item["bundle_blocks"],
            bundle_characters=item["bundle_characters"],
        )
    annotate(
        candidate_count=len(pool),
        selected_count=len(selected),
        profile=state.get("profile_name", "simple"),
        selection_strategy=strategy,
        parent_context_reads=read_count,
        decision_status=status,
    )
    route = "build_context"
    if state.get("repack_pending") and not (
        {h["chunk_id"] for h in selected} - {h["chunk_id"] for h in state.get("selected_evidence", [])}
    ):
        # No new evidence after local repacking: spend remaining search budget,
        # not another generation/check pair over identical sources.
        route = (
            "plan_queries"
            if can_search_corrective(state)
            else ("finalize_response" if state.get("verified_snapshot") else "build_context")
        )
    return {
        "repack_pending": False,
        "evidence_registry": registry,
        "candidate_evidence": [by_id[h["chunk_id"]] for h in pool],
        "selected_evidence": selected,
        "evidence_selection_diagnostics": diagnostics,
        "rejected_evidence_ids": rejected,
        "parent_context_cache": state.get("parent_context_cache", {}),
        "jev_assessment_cache": jev_cache,
        "jev_status": status,
        "jev_conflict_chunk_ids": sorted(conflict_ids),
        "route": route,
    }


@observed
async def build_context(state):
    selected = state.get("selected_evidence", [])
    if not selected:
        corrective = schedule_corrective(
            state,
            feedback="Không có context đủ ngữ cảnh; tìm nguồn cho requirements còn thiếu. Bỏ filter loại tài liệu/chính sách quá hẹp nếu không có hits.",
        )
        if corrective:
            return corrective
        return {
            "route": "finalize_response" if state.get("verified_snapshot") else "fallback_response",
            "fallback_reason": "insufficient_evidence",
        }
    context = format_selected_context(selected, state.get("jev_conflict_chunk_ids", []))
    profile = _profile(state)
    if not context_fits(selected, state.get("jev_conflict_chunk_ids", []), profile):
        raise CopilotDependencyError("selected evidence exceeds context budget")
    snapshot = state.get("verified_snapshot")
    current_sources = evidence_fingerprints(selected, state.get("jev_conflict_chunk_ids", []))
    if (
        snapshot is not None
        and state.get("corrective_retrieval_count", 0)
        and state.get("draft_answer") == snapshot.answer
        and current_sources.items() <= snapshot.evidence_fingerprints.items()
        and snapshot.resolved_date == str(state.get("resolved_date"))
        and not any(d.status == "missing" and d.evidence_status == "sufficient" for d in snapshot.requirement_diagnostics)
    ):
        # The new context only retains/removes previously checked source blocks.
        # Removal alone cannot answer missing goals. The snapshot owns its original
        # citations, including removed blocks, so it remains independently verifiable.
        # Changed/added blocks or answer omissions still require generation/checking.
        return {"answer_context": context, "route": "finalize_response"}
    annotate(context_characters=len(context), context_tokens_estimate=estimate_context_tokens(context))
    return {"answer_context": context, "route": "generate_answer"}
