from datetime import date
from pathlib import Path

import pytest

from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import AdvisorFactualClaim, RoleplayState
from src.integrations.practice_knowledge import RetrievalKnowledgeEvidenceProvider
from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk

SCENARIOS = Path("data/scenarios/scenarios.json")


def knowledge_chunk(chunk_id: str, content: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        document_id="FAQ_VF5" if chunk_id == "chunk-shared" else "PROMOTION_SALES_VINFAST_test",
        content=content,
        metadata=ChunkMetadata(
            chunk_id=chunk_id,
            document_id="FAQ_VF5" if chunk_id == "chunk-shared" else "PROMOTION_SALES_VINFAST_test",
            title="Nguồn VinFast",
            document_type="policy",
            product_model="VF 5",
            effective_date=date(2026, 1, 1),
            source="https://example.test/vinfast",
            version="2026.1",
        ),
    )


class RecordingRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, str | None, str | None]] = []

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 4,
        product_model: str | None = None,
        document_type: str | None = None,
        target_date: date | None = None,
    ) -> list[KnowledgeChunk]:
        self.calls.append((query, top_k, product_model, document_type))
        return [
            knowledge_chunk("chunk-shared", "Nội dung chính sách đã phê duyệt."),
            knowledge_chunk(f"chunk-{len(self.calls)}", f"Evidence cho {query}"),
        ]


# Routing tests disable the general supplement to observe the routed call alone.


def scenario_and_state():
    scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI")
    state = RoleplayState.from_scenario("session-1", scenario)
    state.factual_claims = [
        AdvisorFactualClaim(message_id="m1", text="VF 5 có chính sách bảo hành", category="warranty"),
        AdvisorFactualClaim(message_id="m2", text="VF 5 có ưu đãi", category="promotion"),
        AdvisorFactualClaim(message_id="m3", text="VF 5 có ưu đãi", category="promotion"),
    ]
    return scenario, state


@pytest.mark.asyncio
async def test_provider_retrieves_each_unique_claim_and_deduplicates_chunks():
    scenario, state = scenario_and_state()
    retriever = RecordingRetriever()
    provider = RetrievalKnowledgeEvidenceProvider(retriever, top_k_per_claim=2, general_top_k=0)

    evidence = await provider.for_session(scenario, state)

    assert retriever.calls == [
        ("VF 5 có chính sách bảo hành", 24, "VF 5", None),
        ("VF 5 có ưu đãi", 24, "VF 5", "promotion"),
    ]
    assert [item.source_id for item in evidence] == ["chunk-shared", "chunk-2"]
    assert all(item.version == "2026.1" for item in evidence)


@pytest.mark.asyncio
async def test_provider_returns_no_evidence_when_advisor_made_no_factual_claims():
    scenario, state = scenario_and_state()
    state.factual_claims = []
    retriever = RecordingRetriever()

    evidence = await RetrievalKnowledgeEvidenceProvider(retriever, general_top_k=0).for_session(scenario, state)

    assert evidence == []
    assert retriever.calls == []


@pytest.mark.asyncio
async def test_provider_uses_model_and_msrp_table_for_price_claim():
    scenario, state = scenario_and_state()
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text="VF 5 Plus giá 100 triệu", category="price")]

    class PriceRetriever(RecordingRetriever):
        def retrieve(self, query, *, top_k=4, product_model=None, document_type=None, target_date=None):
            self.calls.append((query, top_k, product_model, document_type))
            return [
                knowledge_chunk("charger", "VF 5 bộ sạc 11.000.000 VNĐ"),
                knowledge_chunk("msrp", "Giá bán bán lẻ đề xuất\nVF 5 | Plus | 496.000.000 VNĐ"),
            ]

    retriever = PriceRetriever()
    evidence = await RetrievalKnowledgeEvidenceProvider(retriever, general_top_k=0).for_session(scenario, state)

    assert retriever.calls == [("VF 5 Plus giá 100 triệu", 24, "VF 5", "price_list")]
    assert [item.source_id for item in evidence] == ["msrp"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,category",
    [
        ("đi được 1.000 km mỗi lần sạc", "battery_charging"),
        ("VF 5 Plus chạy 326km mỗi lần sạc", "battery_charging"),
        # Battery capacity in kWh is a spec, not a charging tariff.
        ("VF 5 Plus có pin 37,23 kWh, đi được 326,4 km/lần sạc", "battery_charging"),
        ("VF 5 Plus có pin 37,23 kWh", "product"),
        ("VF 5 Plus có pin 37,23 kWh", "battery_charging"),
    ],
)
async def test_range_and_battery_capacity_claims_use_product_specs(text, category):
    scenario, state = scenario_and_state()
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=text, category=category)]
    retriever = RecordingRetriever()

    await RetrievalKnowledgeEvidenceProvider(retriever, general_top_k=0).for_session(scenario, state)

    assert retriever.calls == [(text, 3, "VF 5", "product_specs")]


@pytest.mark.asyncio
async def test_provider_rejects_mismatched_scenario():
    _, state = scenario_and_state()
    other_scenario = ScenarioRepository(SCENARIOS).get("SCENARIO_02_VF7_VS_CX5")

    with pytest.raises(ValueError, match="identifiers do not match"):
        await RetrievalKnowledgeEvidenceProvider(RecordingRetriever(), general_top_k=0).for_session(
            other_scenario, state
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,category,expected",
    [
        ("VF 7 bảo hành 10 năm/200.000 km", "warranty", "FAQ_VF7_20260922"),
        ("VF 7 ưu đãi 9%", "promotion", "PROMOTION_SALES_VINFAST_20260921"),
        ("VF 6 Plus có 7 túi khí", "product", "PRODUCT_VF6_plus"),
    ],
)
async def test_authoritative_routing_and_trim(text, category, expected):
    scenario, state = scenario_and_state()
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=text, category=category)]

    class Retriever:
        def retrieve(self, *args, **kwargs):
            result = []
            for document, content in [
                ("PRODUCT_VF7_20260922", "VF 7 bảo hành 7 năm"),
                ("PRODUCT_VF6_eco", "VF 6 Eco"),
                ("PRODUCT_VF6_plus", "VF 6 Plus có 7 túi khí"),
                ("FAQ_VF7_20260922", "VF 7 bảo hành 10 năm/200.000 km"),
                ("PROMOTION_SALES_VINFAST_20260921", "VF 7 ưu đãi 9%"),
            ]:
                chunk = knowledge_chunk(document, content)
                chunk.document_id = document
                if category != "product" or document.startswith("PRODUCT_"):
                    result.append(chunk)
            return result

    evidence = await RetrievalKnowledgeEvidenceProvider(Retriever(), top_k_per_claim=1, general_top_k=0).for_session(
        scenario, state
    )
    assert evidence[0].source_id == expected


@pytest.mark.asyncio
async def test_claim_cap_warns(caplog):
    scenario, state = scenario_and_state()
    state.factual_claims = [
        AdvisorFactualClaim(message_id=f"m{i}", text=f"claim {i}", category="other") for i in range(19)
    ]
    retriever = RecordingRetriever()
    await RetrievalKnowledgeEvidenceProvider(retriever, general_top_k=0).for_session(scenario, state)
    assert len(retriever.calls) == 16
    assert "dropped 3 claims" in caplog.text


@pytest.mark.asyncio
async def test_discounted_price_keeps_both_promotion_and_price_sources():
    scenario, state = scenario_and_state()
    state.factual_claims = [
        AdvisorFactualClaim(message_id="m1", text="VF 6 Eco giá sau ưu đãi 9% là 587,86 triệu", category="price")
    ]

    class Retriever:
        def retrieve(self, query, **kwargs):
            if kwargs["document_type"] == "price_list":
                chunk = knowledge_chunk("msrp", "Giá bán bán lẻ đề xuất VF 6 Eco 646 triệu")
                chunk.document_id = "PRICE_LIST_VINFAST_test"
                return [chunk]
            result = []
            for i in range(4):
                chunk = knowledge_chunk(f"promotion-{i}", "VF 6 Eco ưu đãi 9%")
                chunk.document_id = "PROMOTION_SALES_VINFAST_test"
                result.append(chunk)
            return result

    evidence = await RetrievalKnowledgeEvidenceProvider(Retriever(), general_top_k=0).for_session(scenario, state)
    assert "msrp" in {item.source_id for item in evidence}
    assert "promotion-0" in {item.source_id for item in evidence}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,category",
    [("VF 6 sạc từ 10% lên 70% trong 25 phút", "battery_charging"), ("VF 6 có giảm xóc tốt", "product")],
)
async def test_spec_claims_do_not_route_to_promotion(text, category):
    scenario, state = scenario_and_state()
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=text, category=category)]

    class SpecRetriever(RecordingRetriever):
        def retrieve(self, query, *, top_k=4, product_model=None, document_type=None, target_date=None):
            self.calls.append((query, top_k, product_model, document_type))
            chunk = knowledge_chunk("spec", text)
            chunk.document_id = "FAQ_VF6_test"
            return [chunk]

    retriever = SpecRetriever()
    evidence = await RetrievalKnowledgeEvidenceProvider(retriever, general_top_k=0).for_session(scenario, state)
    assert all(call[3] != "promotion" for call in retriever.calls)
    assert [item.content for item in evidence] == [text]


@pytest.mark.asyncio
@pytest.mark.parametrize("text,category", [("VF 5 bảo hành 10 năm", "warranty"), ("VF 5 ưu đãi 9%", "promotion")])
async def test_preferred_policy_source_miss_falls_back_to_general(text, category):
    scenario, state = scenario_and_state()
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=text, category=category)]

    class Retriever(RecordingRetriever):
        def retrieve(self, query, *, top_k=4, product_model=None, document_type=None, target_date=None):
            self.calls.append((query, top_k, product_model, document_type))
            chunk = knowledge_chunk("spec", text)
            chunk.document_id = "PRODUCT_VF5_test"
            return [chunk]

    retriever = Retriever()
    evidence = await RetrievalKnowledgeEvidenceProvider(retriever, general_top_k=0).for_session(scenario, state)
    assert [item.source_id for item in evidence] == ["spec"]
    assert len(retriever.calls) == 2
    assert retriever.calls[-1][3] is None


@pytest.mark.asyncio
async def test_claim_evidence_uses_session_date_and_drops_expired_windows():
    from datetime import UTC, datetime

    scenario, state = scenario_and_state()
    state.created_at = datetime(2026, 12, 19, 18, tzinfo=UTC)
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text="VF 5 ưu đãi", category="promotion")]
    calls = []

    class Retriever:
        def retrieve(self, query, **kwargs):
            calls.append(kwargs)
            source = knowledge_chunk("expired", "Thời gian áp dụng: Từ ngày 19/09/2026 đến hết ngày 19/12/2026")
            return [source]

    # The general supplement is filtered by the same session-date validity window.
    assert await RetrievalKnowledgeEvidenceProvider(Retriever()).for_session(scenario, state) == []
    assert all(call["target_date"] == date(2026, 12, 20) for call in calls)


def charging_chunk(chunk_id: str, document_id: str, content: str, document_type: str, policy_type: str | None):
    chunk = knowledge_chunk(chunk_id, content)
    chunk.document_id = document_id
    chunk.metadata.document_id = document_id
    chunk.metadata.document_type = document_type
    chunk.metadata.policy_type = policy_type
    return chunk


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,category",
    [
        ("Ở trạm sạc công cộng VinFast, đơn giá sạc là 3.858 VNĐ/kWh anh ạ.", "price"),
        ("Tiền điện được tính theo kWh thực tế của phiên sạc.", "battery_charging"),
        ("Sạc tại VinFast chỉ 3.858 đồng/kWh.", "price"),
        ("VF 5 sạc hết 3.858 đồng cho mỗi kWh.", "price"),
        ("VF 5 được miễn tiền sạc 1.000 kWh đầu tiên.", "promotion"),
        ("Theo chính sách ngày 19/09/2026, với xe biển vàng, ưu đãi sạc chỉ áp dụng khung 23:00–06:00.", "promotion"),
    ],
)
async def test_charging_tariff_and_policy_claims_use_charging_policy_sources(text, category):
    scenario, state = scenario_and_state()
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=text, category=category)]

    class Retriever(RecordingRetriever):
        def retrieve(self, query, *, top_k=4, product_model=None, document_type=None, target_date=None):
            self.calls.append((query, top_k, product_model, document_type))
            chunks = [
                charging_chunk("deposit", "POLICY_DEPOSIT_test", "Điều khoản đặt cọc", "policy", "general"),
                charging_chunk("tariff", "CHARGING_TARIFF_test", "đơn giá 3.858 VNĐ/kWh", "policy", "charging"),
                charging_chunk("yellow", "POLICY_CHARGING_test", "xe biển vàng 23:00–06:00", "policy", "charging"),
            ]
            return [chunk for chunk in chunks if document_type in (None, chunk.metadata.document_type)]

    retriever = Retriever()
    evidence = await RetrievalKnowledgeEvidenceProvider(retriever, general_top_k=0).for_session(scenario, state)

    assert retriever.calls == [(text, 24, "VF 5", "policy")]
    assert [item.source_id for item in evidence] == ["tariff", "yellow"]


@pytest.mark.asyncio
async def test_charging_claim_without_charging_sources_falls_back_to_general():
    scenario, state = scenario_and_state()
    text = "Đơn giá sạc là 3.858 VNĐ/kWh"
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=text, category="battery_charging")]

    class Retriever(RecordingRetriever):
        def retrieve(self, query, *, top_k=4, product_model=None, document_type=None, target_date=None):
            self.calls.append((query, top_k, product_model, document_type))
            return [charging_chunk("faq", "FAQ_VF5_test", text, "product_specs", None)]

    retriever = Retriever()
    evidence = await RetrievalKnowledgeEvidenceProvider(retriever, general_top_k=0).for_session(scenario, state)

    assert [call[3] for call in retriever.calls] == ["policy", None]
    assert [item.source_id for item in evidence] == ["faq"]


@pytest.mark.asyncio
async def test_promotion_claim_prefers_section_naming_the_same_program():
    scenario, state = scenario_and_state()
    text = "Chương trình Vì Tương Lai Xanh 2 đang giảm 15% giá niêm yết cho VF 6 chị ạ."
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=text, category="promotion")]

    class Retriever:
        def retrieve(self, query, **kwargs):
            # Vector order puts the named program's rate section fourth.
            sections = [
                ("summer", "3. | Chương trình Mùa Hè Rực Rỡ - Vinfascination:\n\no | 2% MSRP với các dòng xe còn lại."),
                ("gratitude", "6. | Chương trình Tri ân Khách hàng xe xăng VinFast chuyển đổi Xanh:"),
                ("voucher", "- | Voucher có giá trị sử dụng khi Khách hàng hoặc người thân"),
                ("vtlx2", "1. | Chính sách “Vì Tương Lai Xanh 2”:\n\n• | Các dòng xe còn lại: Ưu đãi 9% MSRP."),
            ]
            result = []
            for chunk_id, content in sections:
                chunk = knowledge_chunk(chunk_id, content)
                chunk.document_id = "PROMOTION_SALES_VINFAST_test"
                result.append(chunk)
            return result

    evidence = await RetrievalKnowledgeEvidenceProvider(Retriever(), general_top_k=0).for_session(scenario, state)

    assert evidence[0].source_id == "vtlx2"
    assert len(evidence) == 3


@pytest.mark.asyncio
async def test_misrouted_claim_still_gets_general_matches():
    scenario, state = scenario_and_state()
    text = "Phí chiếm trụ từ phút 11 tính 1.000 VNĐ/phút"
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text=text, category="price")]

    class Retriever(RecordingRetriever):
        def retrieve(self, query, *, top_k=4, product_model=None, document_type=None, target_date=None):
            self.calls.append((query, top_k, product_model, document_type))
            if document_type == "price_list":
                return [charging_chunk("msrp", "PRICE_LIST_test", "Giá bán bán lẻ đề xuất VF 5", "price_list", None)]
            return [
                charging_chunk("msrp", "PRICE_LIST_test", "Giá bán bán lẻ đề xuất VF 5", "price_list", None),
                charging_chunk("idle", "CHARGING_TARIFF_test", "phút 11–60 là 1.000 VNĐ/phút", "policy", "charging"),
            ]

    retriever = Retriever()
    evidence = await RetrievalKnowledgeEvidenceProvider(retriever).for_session(scenario, state)

    assert retriever.calls == [(text, 24, "VF 5", "price_list"), (text, 3, "VF 5", None)]
    # Routed evidence stays first and a chunk found by both searches appears once.
    assert [item.source_id for item in evidence] == ["msrp", "idle"]


@pytest.mark.asyncio
async def test_unrouted_claim_does_not_repeat_general_retrieval():
    scenario, state = scenario_and_state()
    state.factual_claims = [AdvisorFactualClaim(message_id="m1", text="VF 5 chở được 5 người", category="other")]
    retriever = RecordingRetriever()

    await RetrievalKnowledgeEvidenceProvider(retriever).for_session(scenario, state)

    assert retriever.calls == [("VF 5 chở được 5 người", 3, "VF 5", None)]
