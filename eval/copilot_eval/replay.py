"""Deterministic replay of per-query RRF, without executing retrieval again."""

import json
from datetime import date
from pathlib import Path

from eval.copilot_eval.experiment import digest, save
from src.agents.copilot.tools import reciprocal_rank_fusion


def execute(output):
    from eval.copilot_eval.benchmark_run import tree_hash
    from eval.copilot_eval.config import REPO, writable

    output = writable(output)
    frozen = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if frozen["runtime_hash"] != tree_hash(REPO / "src")[0]:
        raise RuntimeError("RRF replay requires the captured runtime source")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    cases = json.loads((output / "cases.json").read_text(encoding="utf-8"))
    records = []
    for case in cases:
        path = output / f"{case['case_id']}.nodes.json"
        nodes = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        rounds = []
        all_raw = {}
        all_fused = {}
        all_candidate = {}
        for node in nodes:
            if node["node"] != "select_evidence":
                continue
            s = node["state"]
            profile = s.get("profile_name", "simple")
            top = manifest["configuration"][f"copilot_{profile}_candidate_pool"]
            raw = {}
            fused = {}
            target = date.fromisoformat(s.get("target_date") or s["resolved_date"])
            for result in s.get("raw_search_results", []):
                raw.update((h["chunk_id"], h) for k in ("dense", "bm25") for h in result.get(k, []))
                hits = reciprocal_rank_fusion(
                    result.get("dense", []), result.get("bm25", []), rrf_k=60, top_k=top, target_date=target
                )
                fused.update((h["chunk_id"], h) for h in hits)
            candidate = {h["chunk_id"]: h for h in s.get("candidate_evidence", [])}
            rounds.append(
                {
                    "profile": profile,
                    "candidate_cap": top,
                    "raw_count": len(raw),
                    "per_query_rrf_union_count": len(fused),
                    "candidate_count": len(candidate),
                    "lost_by_per_query_rrf": sorted(raw.keys() - fused.keys()),
                    "lost_after_rrf_scope_interleave_global_cap": sorted(fused.keys() - candidate.keys()),
                    "retained_from_prior_rounds_or_repack": sorted(candidate.keys() - fused.keys()),
                    "raw_ids": sorted(raw),
                    "rrf_ids": sorted(fused),
                    "candidate_ids": sorted(candidate),
                }
            )
            all_raw.update(raw)
            all_fused.update(fused)
            all_candidate.update(candidate)
        gold = set(case["expected"]["supporting_document_ids"])
        coverage = {}
        for name, hits in [("raw", all_raw), ("rrf", all_fused), ("candidate", all_candidate)]:
            present = {h["document_id"] for h in hits.values()}
            coverage[name] = {
                "gold_document_count": len(gold),
                "retrieved_gold_documents": sorted(gold & present),
                "missing_gold_documents": sorted(gold - present),
                "document_recall": len(gold & present) / len(gold) if gold else None,
            }
        records.append({"case_id": case["case_id"], "rounds": rounds, "source_level_coverage": coverage})
    save(
        output / "rrf-replay.json",
        {
            "generator_hash": digest(Path(__file__)),
            "kind": "exact algorithm replay of persisted raw hits; no re-retrieval",
            "limitations": "Document recall is a provenance diagnostic, not semantic goal recall. Lost chunk IDs alone do not prove loss of a required fact. Custom evaluator supplies semantic raw/candidate/published goal support. Candidate filtering can reject a source scope even when its document is present.",
            "cases": records,
        },
    )
    print("RRF replay", len(records))
