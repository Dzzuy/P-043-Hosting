"""Copilot validation excerpts."""


def _normalize(text):
    return " ".join(text.split())


def _quote_part_errors(quote, source, path):
    if source is None:
        return [{"field": [*path, "citation_id"], "error": "unknown_citation_id"}]
    content = _normalize(source["content"])
    return [
        {
            "field": [*path, "quote_parts", index],
            "citation_id": quote.citation_id,
            "error": "quote_part_not_in_content",
            "repair": "Copy this part verbatim from the cited source's content. "
            "Use separate quote_parts for non-contiguous passages; do not paraphrase or quote metadata.",
        }
        for index, part in enumerate(quote.quote_parts)
        if _normalize(part) not in content
    ]
