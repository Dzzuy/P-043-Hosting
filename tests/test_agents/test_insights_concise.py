"""Tests for concise (1-3 sentences) product insights and source traceability."""

import pytest
import re

from src.agents.copilot.insights import (
    _clean_summary,
    _extract_sentences,
    build_complementary_insights,
    build_product_insights,
)
from src.agents.copilot.state import Citation


def count_sentences(text: str) -> int:
    """Helper to count sentences in concise summary."""
    # Temporarily protect numbers
    protected = re.sub(r"(\d+)[\.,](\d+)", r"\1__NUM__\2", text)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", protected) if p.strip()]
    return len(parts)


def test_clean_summary_returns_one_to_three_sentences():
    """Verify each insight summary is between 1 and 3 concise sentences."""
    # Case 1: Short 1-sentence highlight
    text_1 = "VF 5 Plus có công suất tối đa 100 kW và mô-men xoắn cực đại 135 Nm."
    s1 = _clean_summary(text_1, title="Thông số VF 5", category="highlight")
    assert 1 <= count_sentences(s1) <= 3
    assert "100 kW" in s1

    # Case 2: Multi-sentence paragraph (should be capped at 3 sentences)
    text_long = (
        "Trang dịch vụ pin ô tô điện của VinFast công bố đơn giá tại trạm sạc công cộng là 3.858 VNĐ/kWh, áp dụng từ ngày 19/03/2024. "
        "Tiền điện được tính theo kWh thực tế của phiên sạc; không dùng số km hoặc dung lượng pin danh định để khẳng định hóa đơn. "
        "Sau khi hoàn thành phiên sạc, xe chiếm trụ được miễn phí 10 phút đầu; phút 11–60 là 1.000 VNĐ/phút, phút 61–120 là 2.000 VNĐ/phút, từ phút 121 là 4.000 VNĐ/phút. "
        "VinFast thông báo dừng cung cấp dịch vụ thuê pin đối với ô tô điện từ ngày 01/03/2025; khách hàng đã thuê trước đó có thể tiếp tục sử dụng. "
        "Nguồn: https://vinfastauto.com/vn_vi/dich-vu-pin-oto-dien (đối chiếu ngày 04/10/2026)."
    )
    s_long = _clean_summary(text_long, title="Giá sạc công cộng", category="policy")
    cnt = count_sentences(s_long)
    assert 1 <= cnt <= 3
    assert len(s_long) <= 490
    assert "3.858 VNĐ/kWh" in s_long
    # Verify standalone URL was filtered out
    assert "https://" not in s_long


def test_clean_summary_protects_vietnamese_numbers_and_dates():
    """Verify decimal numbers and dates are NOT split into broken sentence fragments."""
    raw = "Đơn giá sạc là 3.858 VNĐ/kWh áp dụng từ ngày 19/03/2024 tại các trạm sạc V-Green."
    sentences = _extract_sentences(raw)
    assert len(sentences) == 1
    assert "3.858 VNĐ/kWh" in sentences[0]
    assert "19/03/2024" in sentences[0]


def test_clean_summary_filters_contract_and_legal_boilerplate():
    """Verify formal legal boilerplate from contracts is excluded from concise summaries."""
    boilerplate_raw = (
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
        "Độc lập - Tự do - Hạnh phúc\n"
        "HỢP ĐỒNG CHO THUÊ PIN XE ĐIỆN\n"
        "Số: [----]\n"
        "Các Bên thống nhất giao kết Hợp Đồng với các nội dung sau đây:\n"
        "ĐIỀU 1. GIẢI THÍCH TỪ NGỮ\n"
        "VinFast có trách nhiệm sửa chữa hoặc thay thế Pin cho Khách Hàng khi dung lượng Pin tối đa (SOH) dưới 70%.\n"
        "Mọi tranh chấp liên quan đến Hợp Đồng nếu không giải quyết qua thương lượng sẽ ra tòa án có thẩm quyền."
    )
    summary = _clean_summary(boilerplate_raw, title="Hợp đồng thuê pin", category="policy")
    assert 1 <= count_sentences(summary) <= 3
    assert "70%" in summary
    assert "CỘNG HÒA XÃ HỘI" not in summary
    assert "Độc lập - Tự do" not in summary
    assert "Mọi tranh chấp" not in summary


def test_build_insights_preserves_full_citation_provenance():
    """Verify that while summary is concise (1-3 sentences), citation retains full excerpt for provenance modal."""
    full_excerpt = (
        "VF 6 được trang bị gói hỗ trợ lái nâng cao ADAS với 8 tính năng an toàn. "
        "Bao gồm cảnh báo chệch làn, kiểm soát đi giữa làn, và phanh khẩn cấp tự động. "
        "Hệ thống pin LFP dung lượng 59,6 kWh cho quãng đường di chuyển 399 km theo chuẩn WLTP. "
        "Xe hỗ trợ sạc nhanh từ 10% đến 70% trong vòng 30 phút."
    )
    citation = Citation(
        citation_id="C1",
        chunk_id="vf6-adas-1",
        document_id="DOC_VF6_SPECS_2026",
        title="Thông số kỹ thuật VF 6",
        version="2026.09",
        effective_from="2026-09-01",
        source_uri="https://vinfastauto.com/vn_vi/vf6-specs",
        product_model="VF 6",
        document_type="highlight",
        excerpt=full_excerpt,
    )

    insights = build_product_insights(
        {"product_models": ["VF 6"]},
        answer_text="",
        existing_citations=[citation],
    )

    assert len(insights) == 1
    insight = insights[0]

    # 1. Summary on card must be concise (1-3 sentences)
    assert 1 <= count_sentences(insight.summary) <= 3
    assert len(insight.summary) < len(full_excerpt) or count_sentences(full_excerpt) <= 3

    # 2. Citation attached must have full provenance for the modal
    assert insight.citation is not None
    assert insight.citation.document_id == "DOC_VF6_SPECS_2026"
    assert insight.citation.version == "2026.09"
    assert insight.citation.title == "Thông số kỹ thuật VF 6"
    assert insight.citation.excerpt == full_excerpt


def test_complementary_insights_novelty_with_concise_summary():
    """Verify semantic novelty filter works accurately with concise 1-3 sentence summaries."""
    citation = Citation(
        citation_id="C1",
        chunk_id="vf5-warranty",
        document_id="DOC_WARRANTY",
        title="Chính sách bảo hành",
        product_model="VF 5",
        document_type="policy",
        excerpt="VF 5 được bảo hành chính hãng 7 năm hoặc 160.000 km tùy điều kiện nào đến trước.",
    )

    # When answer already mentions 7 năm và 160.000 km:
    answer_text = "Xe VF 5 được bảo hành chính hãng trong thời gian 7 năm hoặc 160.000 km."
    insights = build_complementary_insights(
        {"product_models": ["VF 5"]},
        answer_text=answer_text,
        existing_citations=[citation],
    )
    assert len(insights) == 0

    # When answer does NOT mention warranty:
    unrelated_answer = "Giá xe VF 5 Plus niêm yết là 496 triệu đồng."
    insights_fresh = build_complementary_insights(
        {"product_models": ["VF 5"]},
        answer_text=unrelated_answer,
        existing_citations=[citation],
    )
    assert len(insights_fresh) == 1
    assert "7 năm" in insights_fresh[0].summary
