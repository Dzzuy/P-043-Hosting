"""Deterministic context packaging, independent of the evidence judge."""

import hashlib

from src.agents.copilot.tools import build_evidence_context


def evidence_fingerprints(selected, conflict_ids=()):
    """Bind source content, citation labels and conflict role, independent of order."""
    conflicts = set(conflict_ids)
    return {
        hit["chunk_id"]: hashlib.sha256(
            (str(hit["chunk_id"] in conflicts) + "\n" + format_selected_context([hit])).encode("utf-8")
        ).hexdigest()
        for hit in selected
    }


def estimate_context_tokens(text):
    """Conservative UTF-8 estimate, not a provider-specific tokenizer.

    Two bytes per token budgets Vietnamese more cautiously than chars/4. Keep
    the character ceiling too; no tokenizer downloads in the request path.
    """
    return (len(text.encode("utf-8")) + 1) // 2


def context_fits(selected, conflicts, profile):
    context = format_selected_context(selected, conflicts)
    return (
        len({h["chunk_id"] for h in selected}) <= profile.evidence_blocks
        and len(context) <= profile.context_characters
        and estimate_context_tokens(context) <= getattr(profile, "context_tokens", profile.context_characters)
    )


def format_selected_context(selected, conflict_ids=()):
    # Preserve selection order and citation IDs, without repeating shared parents.
    selected = list({h["chunk_id"]: h for h in selected}.values())
    conflicts = set(conflict_ids)
    if not conflicts:
        return build_evidence_context(selected)[0]
    accepted = [h for h in selected if h["chunk_id"] not in conflicts]
    disputed = [h for h in selected if h["chunk_id"] in conflicts]
    return (
        "EVIDENCE ĐƯỢC CHỌN (vẫn cần kiểm chứng):\n"
        + (build_evidence_context(accepted)[0] if accepted else "(không có)")
        + "\n\nEVIDENCE BÁC BỎ GIẢ ĐỊNH CÂU HỎI (không tự suy ra mâu thuẫn giữa các nguồn):\n"
        + build_evidence_context(disputed)[0]
    )
