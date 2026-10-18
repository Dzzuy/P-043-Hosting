"""Evidence-stage regression, independent of historical benchmark answers."""

from eval.copilot_eval.benchmark_judge import stages


def test_published_context_uses_snapshot_not_last_repack():
    old = {"chunk_id": "old", "content": "Published source"}
    new = {"chunk_id": "new", "content": "Later repack"}
    nodes = [
        {
            "node": "build_context",
            "state": {"route": "generate_answer", "selected_evidence": [old], "evidence_registry": [old]},
        },
        {
            "node": "finalize_response",
            "state": {
                "selected_evidence": [new],
                "evidence_registry": [old, new],
                "verified_snapshot": {"evidence_fingerprints": {"old": "hash"}},
            },
        },
    ]
    s = stages(nodes, {"status": "answered"})
    assert [h["chunk_id"] for h in s["published"]] == ["old"]
    assert stages(nodes, {"status": "abstained"})["published"] == []


def test_raw_stage_retains_all_rounds_and_deduplicates_identity():
    a = {"chunk_id": "a", "content": "A"}
    b = {"chunk_id": "b", "content": "B"}
    nodes = [
        {"node": "retrieve_documents", "state": {"raw_search_results": [{"dense": [a], "bm25": [a]}]}},
        {"node": "retrieve_documents", "state": {"raw_search_results": [{"dense": [b], "bm25": []}]}},
    ]
    assert [h["chunk_id"] for h in stages(nodes, {})["raw"]] == ["a", "b"]
