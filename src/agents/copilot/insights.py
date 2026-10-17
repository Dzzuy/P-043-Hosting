"""Deterministic, snapshot-grounded Product Insights builder.

Builds complementary insight cards strictly from verified sources, without repeating
facts already stated in the main answer or deleting essential conditions/disclaimers.
"""

import hashlib
import re
from typing import Literal

from src.agents.copilot.state import Citation, ProductInsight
from src.knowledge.validity import is_document_retrievable, parse_target_date, today_in_vietnam


def _resolve_category(document_type: str | None) -> Literal["highlight", "policy"]:
    if not document_type:
        return "highlight"
    doc_type_lower = document_type.strip().lower()
    if doc_type_lower in {"policy", "promotion", "price_list"}:
        return "policy"
    return "highlight"


def _extract_sentences(raw_text: str) -> list[str]:
    """Split text into distinct, coherent sentences, protecting numbers, dates and acronyms."""
    normalized = re.sub(r"[\r\n]+", "\n", raw_text)
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    raw_sentences: list[str] = []

    for line in lines:
        if re.match(r"^[\s\|\-\:\+]+$", line):
            continue
        if re.search(
            r"^(?:Hợp đồng|Cộng hòa xã hội|Độc lập|Số:\s*\[|CCCD|Mã số doanh nghiệp|Các Bên thống nhất|ĐIỀU \d+|Mọi tranh chấp|Khi xảy ra sự kiện bất khả kháng|Điện thoại\s*\|)",
            line,
            re.I,
        ):
            continue

        # Protect numbers with decimal or comma separators (e.g. 3.858, 160.000, 7,5) and dates
        numbers = []

        def protect_number(match):
            numbers.append(match[0])
            return f"__NUM{len(numbers) - 1}__"

        protected = re.sub(r"\d+(?:[.,]\d+)+", protect_number, line)
        parts = re.split(r"(?<=[.!?])\s+", protected)
        for p in parts:
            restored = p.strip()
            for index, number in enumerate(numbers):
                restored = restored.replace(f"__NUM{index}__", number)
            restored = re.sub(r"^(?:[-•+*]\s+|o\s*[|]\s*|\d+[.)]\s+)", "", restored).strip()
            restored = re.sub(r"^\|\s*|\s*\|$", "", restored).strip()
            if len(restored) >= 10:
                raw_sentences.append(restored)

    return raw_sentences


def _score_sentence(s: str, category: str) -> float:
    """Score a sentence by its relevance to vehicle highlights or active commercial policies."""
    score = 0.0
    s_lower = s.lower()

    if category == "policy" and ("(*) lưu ý" in s_lower or "điều kiện" in s_lower or "chưa có sẵn" in s_lower):
        score += 3.5

    if re.search(
        r"\b\d+(?:[\.,]\d+)?\s*(?:triệu|tỷ|km|kwh|năm|tháng|%|hp|nm|kw|phút|giờ|vnđ|đồng)\b",
        s_lower,
    ):
        score += 2.5

    if category == "policy":
        policy_keywords = [
            "ưu đãi", "miễn phí", "áp dụng", "đơn giá", "sạc", "trụ sạc", "thuê pin",
            "bảo hành", "chi phí", "thời hạn", "hóa đơn", "biểu phí", "quy định", "hợp đồng"
        ]
        for kw in policy_keywords:
            if kw in s_lower:
                score += 1.0
    else:  # highlight
        highlight_keywords = [
            "công suất", "động cơ", "quãng đường", "pin", "adas", "an toàn",
            "tính năng", "trang bị", "thông minh", "thiết kế", "tiện nghi", "vận hành", "bảo hành"
        ]
        for kw in highlight_keywords:
            if kw in s_lower:
                score += 1.0

    return score


def _clean_summary(excerpt: str | None, title: str | None, category: str = "highlight") -> str:
    """Produce a concise 1-3 sentence summary focusing on highlights and active policies."""
    raw = (excerpt or "").strip()
    if not raw:
        raw = (title or "").strip()
    if not raw:
        return "Thông tin và chính sách đối chiếu theo tài liệu chính thức."

    # Remove marketing lead capture boilerplate only
    raw = re.sub(r"Vui lòng để lại thông tin[^\.\n]*[\.\n]?", "", raw, flags=re.I)
    raw = re.sub(r"Các thông tin sản phẩm có thể thay đổi[^\.\n]*[\.\n]?", "", raw, flags=re.I)
    raw = re.sub(r"Nguồn:\s*https?://\S+", "", raw, flags=re.I)

    # Website specs often put the label and value on separate lines.
    raw = re.sub(
        r"^((?:Quãng đường[^\n.!?:]{0,60}|Công suất[^\n.!?:]{0,60}|Mô[- ]?men[^\n.!?:]{0,60}|Dung lượng pin[^\n.!?:]{0,60}|"
        r"Thời gian nạp pin[^\n.!?:]{0,60}|Số ghế[^\n.!?:]{0,60}|Túi khí))\n+([^\n]+)",
        r"\1: \2.", raw, flags=re.I | re.M,
    )

    sentences = _extract_sentences(raw)
    if not sentences:
        cleaned = re.sub(r"[ \t]+", " ", raw).strip()
        if len(cleaned) > 280:
            cleaned = cleaned[:277] + "..."
        return cleaned if len(cleaned) >= 2 else "Thông tin và chính sách đối chiếu theo tài liệu chính thức."

    # Select between 1 and 3 concise sentences
    if len(sentences) <= 3:
        chosen = sentences
    else:
        scored = []
        for idx, s in enumerate(sentences):
            scored.append((_score_sentence(s, category), idx, s))
        top_scored = sorted(scored, key=lambda x: x[0], reverse=True)[:3]
        chosen = [s for _, _, s in sorted(top_scored, key=lambda x: x[1])]

    result = " ".join(chosen)
    if len(result) > 480:
        if len(chosen) > 1:
            result = " ".join(chosen[:2])
        if len(result) > 480:
            result = chosen[0][:477] + "..."

    result = re.sub(r"\s+", " ", result).strip()
    if not re.search(r"[.!?…]$", result):
        result += "."

    if len(result) < 2:
        return "Thông tin và chính sách đối chiếu theo tài liệu chính thức."
    return result


def _clean_title(section: str | None, title: str | None) -> str:
    raw = (section or title or "Thông tin & Chính sách").strip()
    cleaned = re.sub(r"\s+", " ", raw).strip()
    if len(cleaned) > 160:
        cleaned = cleaned[:157] + "..."
    if len(cleaned) < 2:
        cleaned = "Thông tin & Chính sách"
    return cleaned


def _clean_model(citation_model: str | None, state_models: list[str]) -> str:
    if citation_model and citation_model.strip():
        m = citation_model.strip()
        if m.upper() == "ALL":
            return "ALL"
        return m[:50]
    if state_models:
        for m in state_models:
            if m and m.upper() != "ALL":
                return m[:50]
    return "VinFast"


def _extract_essential_conditions(raw_text: str | None, category: str) -> str | None:
    if not raw_text:
        return None
    matches = [sentence for sentence in _extract_sentences(raw_text) if re.search(
        r"lưu ý|điều kiện|áp dụng cho|đối tượng áp dụng|xe biển vàng|chưa có sẵn|thời hạn|tùy điều kiện|tùy đối tượng", sentence, re.I
    )]
    if matches:
        return "; ".join(list(dict.fromkeys(m.strip() for m in matches))[:2])
    if category == "policy":
        return "Cần đối chiếu điều kiện áp dụng cho từng đối tượng khách hàng."
    return None


def _is_semantically_covered(candidate_text: str, answer_text: str) -> bool:
    """Check if the core factual information in candidate_text is already asserted in answer_text."""
    if not answer_text or not answer_text.strip() or not candidate_text:
        return False

    ans_norm = re.sub(r"\s+", " ", answer_text.lower())
    cand_norm = re.sub(r"\s+", " ", candidate_text.lower())

    # Check 1: Extract numeric facts (numbers + units) from candidate
    cand_numbers = re.findall(r"\b\d+(?:[\.,]\d+)?(?:\s*(?:triệu|tỷ|km|kwh|năm|tháng|%|hp|nm|kw))?\b", cand_norm)
    meaningful_numbers = [n for n in cand_numbers if len(n.strip()) > 1 and not n.strip().isdigit() or int(re.sub(r"\D", "", n) or 0) > 10]
    if meaningful_numbers:
        matched_numbers = [num for num in meaningful_numbers if num in ans_norm]
        # If all major numbers from candidate appear in the answer, check topic keywords
        if len(matched_numbers) >= 2 or (len(meaningful_numbers) == 1 and matched_numbers):
            # Check if key topic keywords also overlap
            topics = ["giá", "pin", "bảo hành", "sạc", "quãng đường", "thuê pin", "wltp", "nedc", "ưu đãi"]
            cand_topics = [t for t in topics if t in cand_norm]
            if any(t in ans_norm for t in cand_topics):
                return True

    # Check 2: Substantial n-gram overlap (sequences of 5+ words)
    words = cand_norm.split()
    for i in range(len(words) - 5):
        ngram = " ".join(words[i : i + 6])
        if len(ngram) > 20 and ngram in ans_norm:
            return True

    return False


def _models_in_text(text: str) -> set[str]:
    return {f"VF {number}" for number in re.findall(r"\bVF\s*([2-9])\b", text, re.I)}


def _scope_excerpt(citation: Citation, models: list[str]) -> str:
    raw = citation.excerpt or ""
    if not models:
        return raw
    mentioned = _models_in_text(raw)
    if not mentioned - set(models):
        return raw
    # A table spanning several cars is not a safe product card. Retain only
    # self-contained rows naming the chosen car, together with their headings.
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    selected = [line for line in lines if _models_in_text(line) and _models_in_text(line) <= set(models)]
    if citation.document_type in {"policy", "promotion"} and citation.product_model == "ALL":
        general_terms = [line for line in lines if "Các dòng xe khác:" in line]
        if general_terms:
            selected.extend(general_terms)
            # Keep the purchase-date cohort and flag customer-specific restrictions.
            selected.extend(line for line in lines if re.search(r"Đối tượng áp dụng: Các xe mua|Với Khách hàng xe biển vàng", line, re.I))
    if not selected:
        return ""
    headers = [line for line in lines if not _models_in_text(line) and re.search(
        r"MSRP|bao gồm VAT|đã gồm VAT|Điều kiện:|Thời gian áp dụng:|Áp dụng cho", line, re.I
    )]
    return "\n".join([*headers, *selected])


def _snapshot_citations(state: dict, models: list[str]) -> list[Citation]:
    """Read extra product facts from the same audited corpus, without another model call."""
    snapshot = state.get("snapshot")
    if not snapshot or not models:
        return []
    date = parse_target_date(state.get("resolved_date")) or today_in_vietnam()
    citations = []
    seen_documents = set()
    documents = {document.document_id: document for document in getattr(snapshot, "documents", [])}
    for chunk in getattr(snapshot, "chunks", {}).values():
        metadata = chunk.metadata
        if metadata.document_id in seen_documents:
            continue
        document = documents.get(metadata.document_id)
        content = document.content if document else chunk.content
        if metadata.document_type not in {"product_specs", "policy", "promotion"}:
            continue
        if metadata.product_model not in {*models, "ALL"}:
            continue
        if not is_document_retrievable(metadata, date):
            continue
        # A generic policy is useful only when its actual terms concern this car
        # or apply to cars generally. Exclude unrelated models and legal templates.
        if metadata.product_model == "ALL":
            mentioned = _models_in_text(content)
            if mentioned and not mentioned.intersection(models) and "Các dòng xe khác:" not in content:
                continue
            if re.search(r"mẫu hợp đồng|điều khoản.*dịch vụ phần mềm", metadata.title, re.I):
                continue
        seen_documents.add(metadata.document_id)
        citations.append(Citation(
            citation_id=f"C{len(citations) + 1}", chunk_id=chunk.chunk_id,
            document_id=metadata.document_id, title=metadata.title,
            section=None if document else metadata.section_title,
            effective_from=str(metadata.effective_date),
            effective_to=str(metadata.expiry_date) if metadata.expiry_date else None,
            source_uri=metadata.source, product_model=metadata.product_model,
            document_type=metadata.document_type, version=metadata.version,
            excerpt=content,
        ))
    return citations


def build_product_insights(
    state: dict,
    answer_text: str = "",
    existing_citations: list[Citation] | None = None,
    filter_novelty: bool = False,
) -> list[ProductInsight]:
    """Build insight cards with sources, optionally filtering out facts already in answer_text."""
    citations = list(existing_citations or [])
    if not citations:
        snapshot = state.get("verified_snapshot")
        if snapshot is not None and hasattr(snapshot, "citations"):
            citations = list(snapshot.citations)

    # Supplement candidate citations with selected_evidence if available
    selected_evidence = state.get("selected_evidence") or []
    existing_chunk_ids = {c.chunk_id for c in citations if c.chunk_id}
    cid_counter = len(citations) + 1
    for hit in selected_evidence:
        chunk_id = hit.get("chunk_id", "")
        if chunk_id and chunk_id not in existing_chunk_ids:
            citations.append(
                Citation(
                    citation_id=hit.get("citation_id") or f"C{cid_counter}",
                    chunk_id=chunk_id,
                    document_id=hit.get("document_id", "doc"),
                    title=hit.get("title", "Tài liệu sản phẩm"),
                    section=hit.get("section"),
                    page=hit.get("page"),
                    effective_from=hit.get("effective_from"),
                    effective_to=hit.get("effective_to"),
                    source_uri=hit.get("source_uri"),
                    product_model=hit.get("product_model"),
                    document_type=hit.get("document_type"),
                    version=hit.get("version"),
                    excerpt=hit.get("content"),
                )
            )
            existing_chunk_ids.add(chunk_id)
            cid_counter += 1

    state_models = [model for model in state.get("product_models", []) if model != "ALL"]
    if not state_models:
        state_models = list(dict.fromkeys(c.product_model for c in citations if c.product_model and c.product_model != "ALL"))
    for citation in _snapshot_citations(state, state_models):
        citations.append(citation.model_copy(update={"citation_id": f"C{len(citations) + 1}"}))
    # Prioritize useful specs and commercial terms over general document headings.
    citations.sort(key=lambda c: (
        c.document_type == "price_list",
        _resolve_category(c.document_type) == "policy",
        -_score_sentence(_scope_excerpt(c, state_models), _resolve_category(c.document_type)),
    ))
    seen_keys: set[str] = set()
    seen_summaries: set[str] = set()
    seen_policy_documents: set[str] = set()
    insights: list[ProductInsight] = []
    lookup_date = parse_target_date(state.get("resolved_date")) or today_in_vietnam()

    for c in citations:
        dedup_key = c.chunk_id or c.citation_id or c.title
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        if c.product_model and c.product_model not in {*state_models, "ALL", "VinFast"} and state_models:
            continue
        if c.document_type == "battlecard":
            continue
        try:
            start, end = parse_target_date(c.effective_from), parse_target_date(c.effective_to)
        except ValueError:
            continue
        if (start and start > lookup_date) or (end and end < lookup_date):
            continue
        excerpt = _scope_excerpt(c, state_models)
        if not excerpt.strip():
            continue

        category = _resolve_category(c.document_type)
        if category == "policy" and c.document_id in seen_policy_documents:
            continue
        title = _clean_title(c.section, c.title)
        summary_excerpt = excerpt
        if category == "highlight":
            # A product page can contain a marketing price unrelated to the current
            # price list. Keep commercial figures in policy cards only.
            summary_excerpt = "\n".join(line for line in excerpt.splitlines() if not re.search(r"VNĐ|VND|triệu đồng|giá bán", line, re.I))
        summary = _clean_summary(summary_excerpt, c.title, category=category)
        product_model = _clean_model(c.product_model, state_models)
        if product_model == "ALL" and len(state_models) == 1 and _models_in_text(excerpt) == set(state_models):
            product_model = state_models[0]
        if _score_sentence(summary, category) <= 0:
            continue
        normalized_summary = re.sub(r"\s+", " ", summary.casefold())
        if normalized_summary in seen_summaries:
            continue

        # Check semantic novelty against answer_text when requested: omit cards whose facts are already in answer
        if filter_novelty and answer_text and _is_semantically_covered(summary, answer_text):
            continue
        if sum(item.category == category for item in insights) >= 2:
            continue
        seen_summaries.add(normalized_summary)
        if category == "policy":
            seen_policy_documents.add(c.document_id)

        raw_source = excerpt + " " + summary
        conditions = _extract_essential_conditions(raw_source, category)
        applicability = "conditional" if category == "policy" or product_model == "ALL" else "confirmed"

        stable_id = f"ins-{hashlib.md5((dedup_key + title).encode()).hexdigest()[:8]}"

        insights.append(
            ProductInsight(
                category=category,
                product_model=product_model,
                title=title,
                summary=summary,
                citation=c,
                insight_id=stable_id,
                essential_conditions=conditions,
                applicability=applicability,
            )
        )
        if len(insights) >= 4:
            break

    return insights


def build_complementary_insights(
    state: dict,
    answer_text: str = "",
    existing_citations: list[Citation] | None = None,
) -> list[ProductInsight]:
    """Build complementary insight cards strictly filtering facts already in answer_text."""
    return build_product_insights(
        state=state,
        answer_text=answer_text,
        existing_citations=existing_citations,
        filter_novelty=True,
    )
