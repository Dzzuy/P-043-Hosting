"""Offline acceptance tests: immutable versions, approvals and fail-closed PII."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import insert, select

from src.config import get_settings
from src.integrations.customer_intelligence_store import IntelligenceStore
from src.integrations.intelligence_migration import migrate_appointment_stages
from src.integrations.sales_copilot_repository import SQLSalesCopilotRepository
from src.models.customer_intelligence import Event, Extraction, HistoryAnswer, Recap
from src.models.sales_copilot import LeadStage, LeadStatus
from src.services.customer_pii import CustomerPII, PIIUnavailableError
from src.services.intelligence_engine import IntelligenceEngine, stage_for
from src.services.sales_agenda_service import SalesAgendaService
from src.services.sales_conversation_service import SalesConversationService


@pytest.fixture
def crm(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "sales_pii_key", SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(get_settings(), "sales_intelligence_v2_enabled", True)
    repo = SQLSalesCopilotRepository(f"sqlite:///{tmp_path / 'intelligence.db'}")
    cid = repo.create_customer(name="An", advisor_id="sales")
    conv = repo.get_or_create_conversation(cid)
    msg = repo.add_message(conv, "customer", "Tôi so sánh VF 6 và VF 7. SĐT: 0912 345 678. Ngày sinh: 01/02/1990.")
    yield repo, cid, conv, msg
    repo.engine.dispose()


def event(kind, message, **kwargs):
    return Event(
        event_type=kind,
        action="Khách đang cân nhắc",
        actor="customer",
        evidence=[{"message_id": message.id, "quote": "Tôi so sánh VF 6 và VF 7."}],
        **kwargs,
    )


def mock_analysis(monkeypatch, extraction):
    async def ask(self, system, payload, schema):
        # Emulate the privacy boundary even though no external model is called.
        self.mask(json.dumps(payload, ensure_ascii=False, default=str))
        return extraction if schema is Extraction else Recap(text="Khách đang so sánh hai dòng xe.")

    monkeypatch.setattr(CustomerPII, "ask", ask)


@pytest.mark.parametrize(
    "text,kind",
    [
        ("0912 345 678", "SDT"),
        ("+1 (415) 555-2671", "SDT"),
        ('{"phone": "442079460958"}', "SDT"),
        ("SĐT: (415)5552671", "SDT"),
        ("Ngày sinh: 01/02/1990", "NGAY_SINH"),
        ("DOB: 1990-02-01", "NGAY_SINH"),
        ("sinh năm 1990", "NGAY_SINH"),
        ("sinh tháng 2", "NGAY_SINH"),
        ("sinh nhật 01/02", "NGAY_SINH"),
        ("sinh ngày 1 tháng 2 năm 1990", "NGAY_SINH"),
        ('{"birth_year": 1990}', "NGAY_SINH"),
        ("CCCD: 012345678901", "CCCD"),
        ('{"cccd_number": "012345678901"}', "CCCD"),
    ],
)
def test_pii_local_detection(crm, text, kind):
    pii = CustomerPII()
    masked = pii.mask(text)
    assert f"[{kind}_1]" in masked
    assert pii.restore(masked) == text
    assert pii.mapping
    assert all(value not in pii.encrypt() for value in pii.mapping.values())
    assert CustomerPII(pii.encrypt()).mask(text) == masked


def test_mask_scope_preserves_appointment_money_and_contact_name(crm):
    pii = CustomerPII()
    text = "An, an@example.com, 12 Nguyễn Trãi; lái thử 01/02/2026; ký 03/02/2026; giá 700000000; vay 300000000; mã 123456789012"
    assert pii.mask(text) == text
    assert pii.mask("CCCD 012345678901; lặp 012345678901").count("[CCCD_1]") == 2
    assert pii.mask("sinh năm 1990; năm sinh 1990").count("[NGAY_SINH_1]") == 2
    assert pii.mask("Lái thử 01/02/1990, giá 1990000000") == "Lái thử 01/02/1990, giá 1990000000"
    with pytest.raises(ValueError):
        pii.restore("[CCCD_999]")
    with pytest.raises(ValueError):
        CustomerPII().restore("[CCCD_1]")


def test_phone_tokens_stable_across_vietnamese_formats(crm):
    pii = CustomerPII()
    assert pii.mask("0912 345 678") == "[SDT_1]"
    assert pii.mask("+84 912 345 678") == "[SDT_1]"
    assert pii.mask("0044 20 7946 0958") == "[SDT_2]"


@pytest.mark.asyncio
async def test_pii_missing_key_blocks_before_model(crm, monkeypatch):
    factory = AsyncMock()
    monkeypatch.setattr("src.services.customer_pii.get_llm", factory)
    monkeypatch.setattr(get_settings(), "sales_pii_key", SecretStr(""))
    with pytest.raises(PIIUnavailableError):
        CustomerPII()
    factory.assert_not_called()


@pytest.mark.parametrize("stage", ["negotiating", "considering"])
@pytest.mark.parametrize("kind", ["appointment", "test_drive_completed", "quote_sent"])
def test_activities_never_select_stage(crm, stage, kind):
    _, _, _, msg = crm
    prior = {"stage": stage, "rationale": "Sales/customer evidence"}
    assert stage_for(prior, [event(kind, msg).model_dump()], {}, []) == prior


def test_regression_requires_changed_decision_and_closed_stage_is_confirmed(crm):
    _, _, _, msg = crm
    prior = {"stage": "negotiating", "rationale": "Thương lượng"}
    assert stage_for(prior, [event("evaluating", msg).model_dump()], {}, [])["stage"] == "negotiating"
    assert (
        stage_for(prior, [event("evaluating", msg, decision_changed=True).model_dump()], {}, [])["stage"]
        == "considering"
    )
    for kind in ("contract_signed", "closed_lost", "deposit_received"):
        assert stage_for(prior, [event(kind, msg).model_dump()], {}, [])["stage"] == "negotiating"


@pytest.mark.asyncio
async def test_incremental_keeps_confirmation_and_rejects_bad_quote(crm, monkeypatch):
    repo, cid, conv, msg = crm
    mock_analysis(monkeypatch, Extraction(events=[event("evaluating", msg)]))
    engine = IntelligenceEngine(repo)
    first = await engine.analyze(conv, "sales")
    assert first["lead_status"]["stage"] == "considering"
    store = IntelligenceStore(repo)
    snapshot = store.analysis(cid)
    assert snapshot["messages"][0]["content"] == msg.content
    assert "messages" not in store.status(cid)["intelligence"]
    repo.save_profile_override(conv, "budget_vnd", 500000000, "sales")
    repo.add_message(conv, "sales", "Đã ghi nhận nhu cầu của anh.")
    mock_analysis(monkeypatch, Extraction())
    second = await engine.analyze(conv, "sales")
    assert second["profile"]["budget_vnd"] == 500000000
    assert second["lead_status"]["stage"] == "considering"
    assert store.analysis(cid, first["analysis_id"]) == snapshot
    repo.add_message(conv, "customer", "Cảm ơn.")
    invalid = event("negotiating", msg)
    invalid.evidence[0].quote = "Không tồn tại"
    mock_analysis(monkeypatch, Extraction(events=[invalid]))
    with pytest.raises(ValueError, match="Bằng chứng"):
        await engine.analyze(conv, "sales")
    assert store.analysis(cid)["analysis_id"] == second["analysis_id"]


@pytest.mark.asyncio
async def test_cutoff_all_conversations_chat_ignores_new_and_cannot_cross_customer(crm, monkeypatch):
    repo, cid, conv, msg = crm
    other = repo.create_customer(name="Other", advisor_id="other")
    other_conv = repo.get_or_create_conversation(other)
    repo.add_message(other_conv, "customer", "Bí mật khách khác.")
    extraction = Extraction(events=[event("evaluating", msg)])
    seen = []

    async def ask(self, system, payload, schema):
        self.mask(json.dumps(payload, ensure_ascii=False, default=str))
        if schema is Extraction:
            repo.add_message(conv, "customer", "TIN MỚI CHƯA PHÂN TÍCH")
            return extraction
        if schema is Recap:
            return Recap(text="Khách so sánh xe.")
        seen.append(payload)
        return HistoryAnswer(
            answer="Khách so sánh VF 6 và VF 7.",
            evidence=[{"message_id": msg.id, "quote": "Tôi so sánh VF 6 và VF 7."}],
        )

    monkeypatch.setattr(CustomerPII, "ask", ask)
    engine = IntelligenceEngine(repo)
    result = await engine.analyze(conv, "sales")
    assert engine.store.status(cid)["pending_message_count"] == 1
    answer = await engine.chat(cid, "sales", result["analysis_id"], "Khách so sánh gì?")
    assert "VF 6" in answer["answer"]
    assert "TIN MỚI" not in json.dumps(seen)
    assert "Bí mật" not in json.dumps(seen, ensure_ascii=False)
    assert len(engine.store.chats(cid)) == 1
    with pytest.raises(LookupError):
        await engine.chat(cid, "other", result["analysis_id"], "Q")
    with pytest.raises(LookupError):
        await engine.chat(other, "other", result["analysis_id"], "Q")


@pytest.mark.asyncio
async def test_proposals_approval_is_explicit_and_rejection_survives_reanalysis(crm, monkeypatch):
    repo, cid, conv, msg = crm
    sales = repo.add_message(conv, "sales", "Em sẽ gửi phương án vay riêng vào chiều mai.")
    commitment = Event(
        event_type="follow_up",
        action="Chuẩn bị phương án vay",
        actor="sales",
        accepted=True,
        deferred=True,
        evidence=[{"message_id": sales.id, "quote": sales.content}],
    )
    mock_analysis(monkeypatch, Extraction(events=[commitment]))
    engine = IntelligenceEngine(repo)
    await engine.analyze(conv, "sales")
    assert repo.list_tasks_for_customer(cid) == []
    p = engine.store.proposals(cid)[0]
    engine.store.review(cid, "sales", p["id"], False, {})
    repo.add_message(conv, "customer", "Đồng ý.")
    commitment.action = "Gửi phương án tài chính riêng"  # Paraphrase is not new evidence.
    mock_analysis(monkeypatch, Extraction(events=[commitment]))
    await engine.analyze(conv, "sales")
    assert len(engine.store.proposals(cid)) == 1
    assert engine.store.proposals(cid)[0]["status"] == "rejected"
    new_sales = repo.add_message(conv, "sales", "Em sẽ gọi lại sáng mai.")
    commitment.evidence[0].message_id = new_sales.id
    commitment.evidence[0].quote = new_sales.content
    mock_analysis(monkeypatch, Extraction(events=[commitment]))
    await engine.analyze(conv, "sales")
    fresh = next(p for p in engine.store.proposals(cid) if p["status"] == "pending")
    engine.store.review(cid, "sales", fresh["id"], True, {})
    tasks = repo.list_tasks_for_customer(cid)
    assert len(tasks) == 1 and tasks[0]["starts_at"] is None
    with pytest.raises(ValueError):
        engine.store.review(cid, "sales", fresh["id"], True, {})


def test_legacy_appointment_migration_preserves_tasks_and_unknown(crm):
    repo, cid, conv, _ = crm
    with repo.engine.begin() as conn:
        conn.execute(
            insert(repo.lead_scores).values(
                customer_id=cid,
                stage="appointment",
                score=80,
                rationale="Old",
                action_priority="high",
                breakdown_json="[]",
                updated_at=datetime.now(UTC),
            )
        )
    migrate_appointment_stages(repo)
    assert repo.get_lead_score(cid)["stage"] is None
    assert SalesConversationService(repo).get_conversation_details(conv).lead_status["stage"] is None
    assert SalesAgendaService(repo).dashboard("sales")["stage_distribution"] == [
        {"stage": "needs_confirmation", "count": 1}
    ]
    with repo.engine.connect() as conn:
        assert conn.execute(
            select(repo.recommendations.c.payload_json).where(repo.recommendations.c.type == "pipeline_migration")
        ).scalar()


@pytest.mark.asyncio
async def test_publication_race_and_provider_failure_preserve_previous(crm, monkeypatch):
    repo, cid, conv, msg = crm
    mock_analysis(monkeypatch, Extraction(events=[event("evaluating", msg)]))
    engine = IntelligenceEngine(repo)
    first = await engine.analyze(conv, "sales")
    repo.add_message(conv, "customer", "Tôi quan tâm màu đỏ.")
    original = CustomerPII.ask

    async def racing(self, system, payload, schema):
        if schema is Recap:
            repo.save_profile_override(conv, "budget_vnd", 600000000, "sales")
        return await original(self, system, payload, schema)

    monkeypatch.setattr(CustomerPII, "ask", racing)
    with pytest.raises(ValueError, match="Dữ liệu đã thay đổi"):
        await engine.analyze(conv, "sales")
    assert engine.store.analysis(cid)["analysis_id"] == first["analysis_id"]


def test_encrypted_mapping_is_bound_to_customer_even_if_copied(crm):
    pii = CustomerPII(customer_id="customer-a")
    pii.mask("0912345678")
    with pytest.raises(PIIUnavailableError):
        CustomerPII(pii.encrypt(), customer_id="customer-b")
    assert CustomerPII(pii.encrypt(), customer_id="customer-a").restore("[SDT_1]") == "0912345678"


@pytest.mark.asyncio
async def test_provider_receives_only_masked_data_and_no_callbacks(crm, monkeypatch, caplog):
    from types import SimpleNamespace

    seen = []

    async def invoke(messages, config):
        from langsmith import get_tracing_context

        from src.observability import graph_config

        assert get_tracing_context()["enabled"] is False
        assert config["callbacks"] == [] and graph_config() == {}
        seen.append(messages)
        return Recap(text="Đã ghi nhận.")

    model = SimpleNamespace(with_structured_output=lambda *args, **kwargs: SimpleNamespace(ainvoke=invoke))
    monkeypatch.setattr("src.services.customer_pii.get_llm", lambda **kwargs: model)
    pii = CustomerPII()
    await pii.ask(
        "Summarize",
        {
            "messages": ["SĐT 0912345678; sinh năm 1990; CCCD 012345678901"],
            "budget": 1990000000,
            "appointment": "01/02/1990",
        },
        Recap,
    )
    content = seen[0][1]["content"]
    assert "0912345678" not in content and "012345678901" not in content
    assert "[SDT_1]" in content and "[CCCD_1]" in content and "[NGAY_SINH_1]" in content
    assert '"budget": 1990000000' in content and "01/02/1990" in content
    assert not caplog.text


@pytest.mark.asyncio
async def test_provider_failure_has_no_plaintext_error_or_logs(crm, monkeypatch, caplog):
    from types import SimpleNamespace

    async def fail(*args, **kwargs):
        raise RuntimeError("CUSTOMER SECRET 0912345678")

    model = SimpleNamespace(with_structured_output=lambda *args, **kwargs: SimpleNamespace(ainvoke=fail))
    monkeypatch.setattr("src.services.customer_pii.get_llm", lambda **kwargs: model)
    with pytest.raises(ValueError) as error:
        await CustomerPII().ask("Summarize", {"content": "0912345678"}, Recap)
    assert "0912345678" not in str(error.value) + caplog.text
    assert "CUSTOMER SECRET" not in str(error.value) + caplog.text


@pytest.mark.asyncio
async def test_routine_reply_request_and_conditional_promise_create_no_proposal(crm, monkeypatch):
    repo, cid, conv, msg = crm
    answer = repo.add_message(conv, "sales", "Giá đang niêm yết là 700 triệu.")
    ordinary = Event(
        event_type="follow_up",
        action="Trả lời giá",
        actor="sales",
        accepted=True,
        deferred=False,
        evidence=[{"message_id": answer.id, "quote": answer.content}],
    )
    request = event("appointment", msg, accepted=False, deferred=True)
    condition = Event(
        event_type="follow_up",
        action="Nếu có hồ sơ sẽ xin duyệt vay",
        actor="sales",
        accepted=True,
        deferred=True,
        conditional=True,
        evidence=[{"message_id": answer.id, "quote": answer.content}],
    )
    mock_analysis(monkeypatch, Extraction(events=[ordinary, request, condition]))
    await IntelligenceEngine(repo).analyze(conv, "sales")
    assert not IntelligenceStore(repo).proposals(cid)
    assert not repo.list_tasks_for_customer(cid)


@pytest.mark.asyncio
async def test_sales_stage_override_survives_analysis_and_reset_restores_rule_stage(crm, monkeypatch):
    repo, cid, conv, msg = crm
    service = SalesConversationService(repo)
    mock_analysis(monkeypatch, Extraction(events=[event("evaluating", msg)]))
    service.update_lead_stage(
        conv,
        "sales",
        LeadStage.NEGOTIATING,
        "Đã thương lượng",
    )
    await IntelligenceEngine(repo).analyze(conv, "sales")
    assert service.get_conversation_details(conv).lead_status["stage"] == "negotiating"
    reset = service.update_lead_stage(conv, "sales", None)
    assert reset["stage"] == "considering"


def test_completed_activity_has_one_milestone_and_reopen_revokes_it(crm):
    repo, cid, conv, _ = crm
    agenda = SalesAgendaService(repo)
    task = agenda.create("sales", {"title": "Chuẩn bị báo giá riêng"}, conversation_id=conv)
    assert not IntelligenceStore(repo).milestone_history(cid)
    agenda.edit("sales", task["id"], {"status": "completed"})
    agenda.edit("sales", task["id"], {"status": "completed"})
    assert len(IntelligenceStore(repo).milestone_history(cid)) == 1
    agenda.edit("sales", task["id"], {"status": "pending"})
    history = IntelligenceStore(repo).milestone_history(cid)
    assert len(history) == 2 and history[-1]["revoked"] is True


@pytest.mark.asyncio
async def test_modified_old_message_requires_full_rebuild(crm, monkeypatch):
    repo, cid, conv, msg = crm
    mock_analysis(monkeypatch, Extraction(events=[event("evaluating", msg)]))
    engine = IntelligenceEngine(repo)
    first = await engine.analyze(conv, "sales")
    from sqlalchemy import update

    with repo.engine.begin() as conn:
        conn.execute(update(repo.messages).where(repo.messages.c.id == msg.id).values(content="Chưa rõ nhu cầu."))
    assert engine.store.status(cid)["requires_reanalysis"]
    assert engine.store.analysis(cid, first["analysis_id"])["messages"][0]["content"] == msg.content
    mock_analysis(monkeypatch, Extraction())
    second = await engine.analyze(conv, "sales")
    assert second["lead_status"]["stage"] == "new"
    assert not engine.store.status(cid)["pending_message_count"]


@pytest.mark.asyncio
async def test_test_drive_approval_completion_and_cancellation_never_move_pipeline(crm, monkeypatch):
    repo, cid, conv, _ = crm
    repo.save_lead_score(LeadStatus(customer_id=cid, stage="negotiating"))
    sales = repo.add_message(conv, "sales", "Em sắp xếp lái thử lần hai lúc 9 giờ ngày 16/10 tại showroom.")
    appointment = Event(
        event_type="appointment",
        activity_kind="test_drive",
        action="Lái thử lần hai",
        actor="sales",
        accepted=True,
        deferred=True,
        evidence=[{"message_id": sales.id, "quote": sales.content}],
    )
    mock_analysis(monkeypatch, Extraction(events=[appointment]))
    engine = IntelligenceEngine(repo)
    await engine.analyze(conv, "sales")
    p = engine.store.proposals(cid)[0]
    with pytest.raises(ValueError):
        engine.store.review(cid, "sales", p["id"], True, {})
    assert not repo.list_tasks_for_customer(cid)
    engine.store.review(
        cid,
        "sales",
        p["id"],
        True,
        {"starts_at": "2026-10-16T09:00:00+07:00", "ends_at": "2026-10-16T10:00:00+07:00", "location": "Showroom"},
    )
    official = repo.list_tasks_for_customer(cid)[0]
    assert official["location"] == "Showroom" and official["task_type"] == "test_drive"
    agenda = SalesAgendaService(repo)
    agenda.dashboard("sales", now=datetime(2026, 10, 18, tzinfo=UTC))
    assert not engine.store.milestone_history(cid)
    assert repo.get_lead_score(cid)["stage"] == "negotiating"
    agenda.edit("sales", official["id"], {"status": "completed"})
    assert engine.store.milestone_history(cid)[0]["event_type"] == "test_drive_completed"
    detail = SalesConversationService(repo).get_conversation_details(conv)
    assert len(detail.milestones) == len(detail.memory["timeline"]) == 1
    assert len(agenda.dashboard("sales")["milestones"]) == 1
    assert repo.get_lead_score(cid)["stage"] == "negotiating"
    agenda.edit("sales", official["id"], {"status": "cancelled"})
    assert engine.store.milestone_history(cid)[-1]["revoked"]
    assert not SalesConversationService(repo).get_conversation_details(conv).milestones
    assert not agenda.dashboard("sales")["milestones"]
    assert repo.get_lead_score(cid)["stage"] == "negotiating"


def test_migration_restores_verified_history_and_keeps_obsolete_score(crm):
    repo, cid, conv, _ = crm
    repo.save_lead_score(LeadStatus(customer_id=cid, stage="considering"))
    repo.save_recommendation_or_draft(conv, "lead_stage_override", {"stage": "negotiating", "advisor_id": "sales"})
    from sqlalchemy import update

    with repo.engine.begin() as conn:
        conn.execute(update(repo.lead_scores).values(stage="appointment", score=73))
    migrate_appointment_stages(repo)
    migrate_appointment_stages(repo)
    assert repo.get_lead_score(cid)["stage"] == "negotiating"
    with repo.engine.connect() as conn:
        assert conn.execute(select(repo.lead_scores.c.score)).scalar() == 73
        assert (
            len(
                conn.execute(
                    select(repo.recommendations).where(repo.recommendations.c.type == "pipeline_migration")
                ).all()
            )
            == 1
        )


@pytest.mark.asyncio
async def test_concurrent_chat_without_new_pii_does_not_abort_publish_and_multichunk_chat_synthesizes(crm, monkeypatch):
    repo, cid, conv, msg = crm
    for i in range(61):
        repo.add_message(conv, "customer", f"Tin nhắn thêm thứ {i}")
    mock_analysis(monkeypatch, Extraction(events=[event("evaluating", msg)]))
    engine = IntelligenceEngine(repo)
    first = await engine.analyze(conv, "sales")
    repo.add_message(conv, "customer", "Tôi muốn xem thêm màu trắng.")

    async def ask_during_analysis(self, system, payload, schema):
        self.mask(json.dumps(payload, ensure_ascii=False, default=str))
        if schema is Recap:
            # Simulate a concurrent history-chat or draft lookup that introduces no new PII tokens.
            head = engine.store.head(cid)
            concurrent_pii = CustomerPII(head["pii_mapping"], customer_id=cid)
            concurrent_pii.mask("Câu hỏi không có PII mới")
            engine.store.save_mapping(cid, concurrent_pii, head)
            return Recap(text="Khách đang cân nhắc thêm màu trắng.")
        if schema is Extraction:
            return Extraction()
        return HistoryAnswer(
            answer="Khách so sánh VF 6 và VF 7.",
            evidence=[{"message_id": msg.id, "quote": "Tôi so sánh VF 6 và VF 7."}],
        )

    monkeypatch.setattr(CustomerPII, "ask", ask_during_analysis)
    second = await engine.analyze(conv, "sales")
    assert second["analysis_id"] != first["analysis_id"]
    chat_res = await engine.chat(cid, "sales", second["analysis_id"], "Khách so sánh xe nào?")
    assert "VF 6" in chat_res["answer"]
    assert chat_res["evidence"][0]["message_id"] == msg.id

