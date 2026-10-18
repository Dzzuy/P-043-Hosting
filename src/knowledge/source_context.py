"""Deterministic source dependencies; no relevance scoring or generated text."""

import re

from src.knowledge.validity import is_document_retrievable


def source_context_chunks(anchor, chunks, target_date):
    """Keep scope/conditions together, using existing headers for standalone rows.

    Policy sections are atomic: scope, eligibility and exceptions can be split
    across chunks even when no individual chunk has requires_context set.
    Price/spec rows can reuse context_prefix without importing the first row.
    """
    chunks = sorted(
        (
            c
            for c in chunks
            if c.document_id == anchor.document_id
            and c.metadata.version == anchor.metadata.version
            and is_document_retrievable(c.metadata, target_date)
        ),
        key=lambda c: (c.metadata.chunk_index, c.chunk_id),
    )
    if not any(c.chunk_id == anchor.chunk_id for c in chunks):
        return []
    meta = anchor.metadata
    section = meta.section_title or ""
    parts = section.split(" > ") if section else []
    scope_levels = [i for i, part in enumerate(parts) if re.search(r"đối tượng áp dụng|phạm vi áp dụng", part, re.I)]
    # A policy audience is a boundary: don't import exceptions for another audience.
    root = " > ".join(parts[: scope_levels[-1] + 1]) if scope_levels else (parts[0] if parts else "")
    chosen = {anchor.chunk_id: anchor}
    same = [c for c in chunks if c.metadata.section_id == meta.section_id]
    if meta.document_type == "policy":
        chosen.update((c.chunk_id, c) for c in same)
    elif meta.requires_context:
        if same:
            chosen[same[0].chunk_id] = same[0]
        if not meta.context_prefix:
            header = next((c for c in same if re.search(r"\|\s*:?-{3,}:?\s*\|", c.content)), None)
            if header is not None:
                chosen[header.chunk_id] = header
        chosen.update((c.chunk_id, c) for c in same if abs(c.metadata.chunk_index - meta.chunk_index) <= 1)
    for chunk in chunks:
        title = chunk.metadata.section_title or ""
        global_scope = (
            meta.document_type in {"policy", "price_list"}
            and " > " not in title
            and re.search(r"đối tượng áp dụng|phạm vi áp dụng", title, re.I)
        )
        # Global price scope is shared. A different dated policy audience is not.
        if (
            meta.document_type == "policy"
            and scope_levels
            and title != root
            and title.strip().casefold() not in {"đối tượng áp dụng", "phạm vi áp dụng"}
        ):
            global_scope = False
        condition = (
            root
            and (title == root or title.startswith(root + " > "))
            and re.search(r"lưu ý|ghi chú|điều kiện|ngoại lệ", title.split(" > ")[-1], re.I)
        )
        # A condition inside a different audience subtree never becomes global.
        candidate_parts = title.split(" > ")
        candidate_scopes = [
            " > ".join(candidate_parts[: i + 1])
            for i, part in enumerate(candidate_parts)
            if re.search(r"đối tượng áp dụng|phạm vi áp dụng", part, re.I)
        ]
        if any(section != scope and not section.startswith(scope + " > ") for scope in candidate_scopes):
            condition = False
        if global_scope or condition:
            chosen[chunk.chunk_id] = chunk
    return list(chosen.values())
