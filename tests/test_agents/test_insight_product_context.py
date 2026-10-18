"""Product cards stay scoped to the car and policy date being discussed."""

from types import SimpleNamespace

from src.agents.copilot.insights import build_complementary_insights, build_product_insights
from src.agents.copilot.state import Citation
from src.knowledge.chunking import chunk_document
from src.knowledge.schemas import KnowledgeDocument


def document(identifier, model, kind, content, **overrides):
    return KnowledgeDocument(
        document_id=identifier, title=f"Thông tin {model}", product_model=model,
        document_type=kind, content=content, effective_date="2026-09-01",
        source="https://example.com/source", **overrides,
    )


def test_insights_never_import_unselected_corpus_facts_after_grounding():
    documents = [
        document("specs", "VF 5", "product_specs", "Công suất tối đa\n134 hp\nDung lượng pin khả dụng\n37,23 kWh"),
        document("wrong-car", "VF 9", "product_specs", "VF 9 có công suất 300 kW."),
        document("current", "VF 5", "promotion", "VF 5 được miễn phí sạc đến hết năm 2027. Điều kiện: Áp dụng cho xe cá nhân."),
        document("expired", "VF 5", "promotion", "VF 5 được giảm giá 90%.", expiry_date="2026-09-30", status="expired"),
    ]
    chunks = [chunk for doc in documents for chunk in chunk_document(doc)]
    snapshot = SimpleNamespace(documents=documents, chunks={chunk.chunk_id: chunk for chunk in chunks})
    cards = build_complementary_insights(
        {"snapshot": snapshot, "product_models": ["VF 5"], "resolved_date": "2026-10-14"},
        "VF 5 Plus có giá 496 triệu đồng.",
    )
    assert cards == []  # No verified citations: no independent corpus scan.



def test_shared_price_table_never_publishes_other_cars_as_the_products_highlight():
    citation = Citation(
        citation_id="C1", chunk_id="prices", document_id="price-list", title="Bảng giá",
        product_model="ALL", document_type="price_list",
        excerpt="MSRP kèm pin (bao gồm VAT)\nVF 2 | 188.000.000 VNĐ\nVF 5 | Plus | 496.000.000 VNĐ",
    )
    cards = build_product_insights({"product_models": ["VF 5"]}, existing_citations=[citation])
    assert cards == []  # Keep complete shared tables in the citation panel, never infer rows.


def test_policy_conditions_keep_the_complete_numeric_limit():
    citation = Citation(
        citation_id="C1", chunk_id="warranty", document_id="warranty", title="Bảo hành VF 5",
        product_model="VF 5", document_type="policy",
        excerpt="VF 5 được bảo hành 7 năm hoặc 160.000 km, tùy điều kiện nào đến trước.",
    )
    card = build_product_insights({"product_models": ["VF 5"]}, existing_citations=[citation])[0]
    assert "160.000 km" in card.essential_conditions
