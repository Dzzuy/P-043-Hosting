"""Compact source excerpts; never infer scope or rewrite applicability conditions."""

import hashlib
import re

from src.agents.copilot.state import ProductInsight
from src.knowledge.validity import parse_target_date, today_in_vietnam


def build_product_insights(state, answer_text="", existing_citations=None, filter_novelty=False):
    snapshot = state.get("verified_snapshot")
    citations = existing_citations if existing_citations is not None else getattr(snapshot, "citations", [])
    models = set(getattr(state.get("analysis"), "product_models", [])) - {"ALL"}
    lookup_date = parse_target_date(state.get("resolved_date")) or today_in_vietnam()
    cards, seen = [], set()
    for citation in citations:
        if models and citation.product_model not in models | {"ALL"}:
            continue
        # A shared price table is not a model-specific card. Its complete source
        # remains available through citations; never select rows by keyword.
        if citation.document_type == "price_list" and citation.product_model == "ALL":
            continue
        if citation.document_type == "battlecard":
            continue
        try:
            start, end = parse_target_date(citation.effective_from), parse_target_date(citation.effective_to)
        except ValueError:
            continue
        if (start and start > lookup_date) or (end and end < lookup_date):
            continue
        excerpt = (citation.excerpt or "").strip()
        # Cropping or picking attractive sentences can remove an exception.
        # Longer sources belong in the citation panel, not a lossy summary card.
        if not 2 <= len(excerpt) <= 500 or excerpt in seen:
            continue
        if filter_novelty and (
            f"[{citation.citation_id}]" in answer_text
            or " ".join(excerpt.split()).casefold() in " ".join(answer_text.split()).casefold()
        ):
            continue
        category = "policy" if citation.document_type in {"policy", "promotion", "price_list"} else "highlight"
        if sum(card.category == category for card in cards) >= 2:
            continue
        seen.add(excerpt)
        cards.append(ProductInsight(
            category=category, product_model=citation.product_model or "ALL",
            title=re.sub(r"\s+", " ", citation.section or citation.title)[:160],
            summary=excerpt, citation=citation.model_copy(deep=True),
            insight_id="ins-" + hashlib.sha256(citation.chunk_id.encode()).hexdigest()[:12],
            essential_conditions=excerpt if category == "policy" else None,
            applicability="conditional",
        ))
        if len(cards) == 4:
            break
    return cards


def build_complementary_insights(state, answer_text="", existing_citations=None):
    return build_product_insights(state, answer_text, existing_citations, filter_novelty=True)
