"""Source cards preserve complete excerpts instead of selecting sentences by keywords."""

from src.agents.copilot.insights import build_complementary_insights, build_product_insights
from src.agents.copilot.state import Citation


def citation(text):
    return Citation(citation_id="C1", chunk_id="c1", document_id="d1", title="Quy tắc Orion",
                    product_model="Orion", document_type="policy", excerpt=text)


def test_conditions_and_decimal_values_are_preserved_verbatim():
    text = "Hỗ trợ 160.000 đơn vị. Chỉ áp dụng nhóm A; ngoại trừ ngày nghỉ. Điều kiện bổ sung: đăng ký trước."
    source = citation(text)
    card = build_product_insights({}, existing_citations=[source])[0]
    assert card.summary == text and card.essential_conditions == text
    assert card.citation == source and card.citation is not source
    assert card.applicability == "conditional"


def test_long_sources_are_not_cropped_or_summarized_into_unconditional_promises():
    source = citation("Được hỗ trợ. " * 60 + "Ngoại lệ bắt buộc ở cuối.")
    assert build_product_insights({}, existing_citations=[source]) == []
    assert source.excerpt.endswith("Ngoại lệ bắt buộc ở cuối.")


def test_complementary_cards_use_citation_binding_instead_of_numeric_similarity():
    source = citation("Hỗ trợ 7 năm hoặc 160.000 km, tùy điều kiện nào đến trước.")
    assert not build_complementary_insights({}, "Quyền lợi được giải thích ở đây [C1].", [source])
    # The same numbers can describe different entities/conditions; don't infer equivalence.
    assert len(build_complementary_insights({}, "Đối tượng khác: 7 năm hoặc 160.000 km.", [source])) == 1


def test_no_corpus_scan_and_no_cards_from_expired_sources():
    assert build_product_insights({"snapshot": object()}) == []
    source = citation("Orion được hỗ trợ 7 ngày.")
    source.effective_to = "2025-01-01"
    assert build_product_insights({"resolved_date": "2026-10-17"}, existing_citations=[source]) == []
