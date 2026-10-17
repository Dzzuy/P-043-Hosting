from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from src.agents.roleplay.contracts import PolicyExpectation
from src.integrations.practice_policy import ScenarioPolicyResolver, application_window
from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk


def policy_scenario():
    return SimpleNamespace(
        policy_expectations=[
            PolicyExpectation(
                policy_id="vtlx2",
                level="expected",
                topic="Ưu đãi chuyển đổi xe xăng",
                lookup={
                    "query": "Vì Tương Lai Xanh",
                    "product_model": "VF 6",
                    "document_type": "promotion",
                    "policy_type": "general",
                },
            )
        ]
    )


def chunk(*, content="Ưu đãi", expiry=None, version="1", effective="2026-01-01", policy_type="general"):
    return KnowledgeChunk(
        chunk_id="p",
        document_id="promotion",
        content=content,
        metadata=ChunkMetadata(
            chunk_id="p",
            document_id="promotion",
            title="Ưu đãi",
            document_type="promotion",
            product_model="ALL",
            policy_type=policy_type,
            effective_date=effective,
            expiry_date=expiry,
            version=version,
            source="local",
        ),
    )


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def retrieve(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.chunks


def test_found_and_lookup_date_forwarded():
    retriever = FakeRetriever([chunk()])
    result = ScenarioPolicyResolver(retriever).resolve(policy_scenario(), date(2026, 10, 17))[0]
    assert result.status == "found"
    assert result.sources[0].version == "1"
    assert retriever.calls[0][1] == dict(
        product_model="VF 6", document_type="promotion", policy_type="general", top_k=3, target_date=date(2026, 10, 17)
    )


@pytest.mark.parametrize(
    "source",
    [
        chunk(expiry="2026-10-16"),
        chunk(content="Thời gian áp dụng: Từ ngày 19/09/2026 đến hết ngày 19/12/2026"),
        chunk(policy_type="charging"),
    ],
)
def test_invalid_sources_not_applicable(source):
    assert (
        ScenarioPolicyResolver(FakeRetriever([source])).resolve(policy_scenario(), date(2026, 12, 20))[0].status
        == "not_applicable"
    )


def test_historical_date_picks_valid_version():
    resolver = ScenarioPolicyResolver(
        FakeRetriever(
            [
                chunk(version="old", expiry="2026-09-30"),
                chunk(version="new", effective="2026-10-01"),
            ]
        )
    )
    assert resolver.resolve(policy_scenario(), date(2026, 9, 20))[0].sources[0].version == "old"
    assert resolver.resolve(policy_scenario(), date(2026, 10, 17))[0].sources[0].version == "new"


def test_window_end_inclusive_and_reported():
    source = chunk(content="Thời gian áp dụng: Từ ngày 19/09/2026 đến hết ngày 19/12/2026")
    result = ScenarioPolicyResolver(FakeRetriever([source])).resolve(policy_scenario(), date(2026, 12, 19))[0]
    assert result.sources[0].valid_until == date(2026, 12, 19)
    assert application_window("Thời gian áp dụng: 19/09/2026 – 19/12/2026")[1] == date(2026, 12, 19)


def test_session_date_uses_vietnam_timezone():
    from src.agents.roleplay.state import RoleplayState

    state = RoleplayState.model_construct(created_at=datetime(2026, 10, 16, 18, tzinfo=UTC))
    assert state.target_date == date(2026, 10, 17)
    restored = RoleplayState.model_construct(created_at=state.created_at)
    assert restored.target_date == state.target_date


MIXED_PROGRAMMES = """1. | Chính sách “Vì Tương Lai Xanh 2”:
Ưu đãi chuyển đổi xe xăng.
Thời gian áp dụng: Từ ngày 19/09/2026 đến hết ngày 19/12/2026.

7. | Chính sách “Mua xe 0 Đồng”:
Hỗ trợ vay mua xe.
Thời gian áp dụng: Từ ngày 04/01/2026 đến ngày 31/12/2026.

8. | Chương trình khác:
Nội dung khác.
"""


def test_mixed_document_resolves_each_programme_window_and_quote():
    scenario = policy_scenario()
    scenario.policy_expectations[0].lookup.query = "Vì Tương Lai Xanh 2"
    scenario.policy_expectations.append(
        PolicyExpectation(
            policy_id="zero_down",
            level="bonus",
            topic="Chương trình hỗ trợ vay mua xe",
            lookup={
                "query": "Mua xe 0 Đồng",
                "product_model": "VF 6",
                "document_type": "promotion",
                "policy_type": "general",
            },
        )
    )
    resolver = ScenarioPolicyResolver(FakeRetriever([chunk(content=MIXED_PROGRAMMES)]))
    expired, active = resolver.resolve(scenario, date(2026, 12, 20))
    assert expired.status == "not_applicable"
    assert active.status == "found"
    assert active.sources[0].valid_until == date(2026, 12, 31)
    assert active.sources[0].quote.startswith("7. |")
    assert "Vì Tương Lai Xanh 2" not in active.sources[0].quote
    assert "8. |" not in active.sources[0].quote


def test_mixed_chunk_without_anchor_is_not_expired_by_another_programme():
    from src.integrations.practice_policy import valid_policy_chunk

    assert application_window(MIXED_PROGRAMMES) == (None, None)
    assert application_window(MIXED_PROGRAMMES, "missing programme") == (None, None)
    assert valid_policy_chunk(chunk(content=MIXED_PROGRAMMES), date(2026, 12, 20))


def test_anchor_matching_is_case_insensitive_and_missing_anchor_falls_back():
    assert application_window(MIXED_PROGRAMMES, "mua xe 0 đồng")[1] == date(2026, 12, 31)
    text = "Thời gian áp dụng: 19/09/2026 – 19/12/2026"
    assert application_window(text, "missing programme")[1] == date(2026, 12, 19)


def real_promotion_chunks():
    from src.knowledge.chunking import load_and_chunk_corpus

    return [item for item in load_and_chunk_corpus() if item.document_id == "PROMOTION_SALES_VINFAST_20260921"]


def test_real_chunks_use_full_programme_windows():
    import json
    from pathlib import Path

    from src.integrations.practice_policy import get_policy_window_index, valid_policy_chunk

    chunks = real_promotion_chunks()
    document = next(
        doc
        for doc in json.loads(Path("data/knowledge/corpus.json").read_text())
        if doc["document_id"] == chunks[0].document_id
    )
    index = get_policy_window_index()
    vtlx = [item for item in chunks if "1. | Chính sách “Vì Tương Lai Xanh 2”:" in (item.metadata.section_title or "")]
    assert len(vtlx) >= 5
    for item in vtlx:
        assert document["content"][item.metadata.start_char : item.metadata.end_char] == item.content
        assert valid_policy_chunk(item, date(2026, 10, 17))
        assert not valid_policy_chunk(item, date(2026, 12, 20))
        assert index.window_for_chunk(item)[1] == date(2026, 12, 19)
        # Older indexes may have section paths without source offsets.
        without_offset = item.model_copy(update={"metadata": item.metadata.model_copy(update={"start_char": None})})
        assert index.window_for_chunk(without_offset)[1] == date(2026, 12, 19)
    zero_down = next(item for item in chunks if "7. |" in (item.metadata.section_title or ""))
    assert valid_policy_chunk(zero_down, date(2026, 12, 20))
    scenario = policy_scenario()
    scenario.policy_expectations[0].lookup.query = "Mua xe 0 Đồng"
    result = ScenarioPolicyResolver(FakeRetriever([zero_down])).resolve(scenario, date(2026, 12, 20))[0]
    assert result.sources[0].valid_until == date(2026, 12, 31)
    tri_an = [item for item in chunks if "6. |" in (item.metadata.section_title or "")]
    assert tri_an
    for item in tri_an:
        assert index.window_for_chunk(item) == (None, None)
        assert valid_policy_chunk(item, date(2026, 12, 20))
    resolver = ScenarioPolicyResolver(FakeRetriever(vtlx))
    assert resolver.resolve(policy_scenario(), date(2026, 12, 20))[0].status == "not_applicable"


def test_new_and_legacy_session_dates(caplog):
    from src.agents.roleplay.scenario_loader import ScenarioRepository
    from src.agents.roleplay.state import RoleplayState
    from src.knowledge.validity import today_in_vietnam

    repository = ScenarioRepository()
    scenario = repository.get(repository.list_public()[0].scenario_id)
    state = RoleplayState.from_scenario("new", scenario)
    assert state.created_at is not None
    payload = state.model_dump()
    payload.pop("created_at")
    payload["session_id"] = "legacy"
    legacy = RoleplayState.model_validate(payload)
    assert legacy.created_at is None
    assert legacy.target_date == today_in_vietnam()
    assert "session_id=legacy" in caplog.text
    state.created_at = datetime(2026, 10, 17, 23, 30, tzinfo=UTC)
    assert state.target_date == date(2026, 10, 18)
