"""Unit tests for background rolling conversation summarizer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.copilot.summarizer import (
    format_summary_for_context,
    maybe_trigger_background_summarization,
    summarize_dialogue_turns,
)


def test_format_summary_for_context():
    empty = format_summary_for_context({})
    assert empty == ""

    summary = {
        "target_models": ["VF 5 Plus"],
        "customer_profile": "Ngân sách 500 triệu, đi 50km/ngày",
        "confirmed_facts": "Giá lăn bánh khoảng 540 triệu",
        "pending_concerns": "Chính sách thuê pin",
    }
    res = format_summary_for_context(summary)
    assert "[Thông tin ngữ cảnh từ các lượt trao đổi trước:" in res
    assert "VF 5 Plus" in res
    assert "Ngân sách 500 triệu" in res
    assert "Chính sách thuê pin" in res
    # confirmed_facts must NOT be exposed as truth for price/specs
    assert "Giá lăn bánh" not in res


@pytest.mark.asyncio
async def test_summarize_dialogue_turns_parses_json():
    mock_resp = MagicMock()
    mock_resp.content = """```json
    {
      "target_models": ["VF 3"],
      "customer_profile": "Đi làm nội đô",
      "confirmed_facts": "Giá 240 triệu",
      "pending_concerns": "Trạm sạc chung cư"
    }
    ```"""
    with patch("src.agents.copilot.summarizer.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_resp)
        mock_get_llm.return_value = mock_llm

        turns = [
            {"role": "user", "content": "VF 3 giá bao nhiêu?"},
            {"role": "assistant", "content": "VF 3 có giá 240 triệu."},
        ]
        res = await summarize_dialogue_turns(turns)
        assert res["target_models"] == ["VF 3"]
        assert "Đi làm nội đô" in res["customer_profile"]


def test_maybe_trigger_background_summarization_threshold():
    bg_tasks = MagicMock()
    repo = MagicMock()
    repo.get_memory_summary.return_value = {"summarized_through_seq": 4}

    # Under threshold (< 14 messages): should not trigger
    maybe_trigger_background_summarization("s1", repo, bg_tasks, current_message_count=10)
    bg_tasks.add_task.assert_not_called()

    # Above threshold (16 messages, 16 - 4 = 12 >= 6): should trigger background task
    maybe_trigger_background_summarization("s1", repo, bg_tasks, current_message_count=16)
    bg_tasks.add_task.assert_called_once()


def test_save_memory_summary_prevents_version_and_watermark_regression(tmp_path):
    """Verify Đợt 4: conditional update with expected_version rejects stale/regressive summary writes."""
    from src.integrations.copilot_sessions import SQLCopilotSessionsRepository

    db_url = f"sqlite:///{tmp_path}/sessions.db"
    repo = SQLCopilotSessionsRepository(db_url)

    session_id = "test-session-concurrent"
    # Task 1 writes initial summary (seq=10, version=1)
    ok1 = repo.save_memory_summary(session_id, {"target_models": ["VF 5"]}, through_seq=10)
    assert ok1 is True

    mem1 = repo.get_memory_summary(session_id)
    assert mem1["version"] == 1
    assert mem1["summarized_through_seq"] == 10

    # Task 2 completes next, updating to version=2, through_seq=18
    ok2 = repo.save_memory_summary(
        session_id, {"target_models": ["VF 5", "VF 3"]}, through_seq=18, expected_version=1
    )
    assert ok2 is True

    mem2 = repo.get_memory_summary(session_id)
    assert mem2["version"] == 2
    assert mem2["summarized_through_seq"] == 18

    # Stale Task 1 finishes late and tries to write with expected_version=1 and through_seq=10
    ok_stale = repo.save_memory_summary(
        session_id, {"target_models": ["VF 5"]}, through_seq=10, expected_version=1
    )
    assert ok_stale is False  # Rejected!

    # Watermark regression attempt without version check also rejected
    ok_regress = repo.save_memory_summary(
        session_id, {"target_models": ["VF 5"]}, through_seq=12, expected_version=2
    )
    assert ok_regress is False  # Rejected because 12 < 18!

    # Current state preserved
    mem_final = repo.get_memory_summary(session_id)
    assert mem_final["version"] == 2
    assert mem_final["summarized_through_seq"] == 18
    assert mem_final["summary"]["target_models"] == ["VF 5", "VF 3"]


def test_planner_accepts_model_from_memory_summary():
    """Verify Đợt 4: model present only in memory_summary is accepted by planner validation."""
    from src.agents.copilot.nodes import planning
    from src.agents.copilot.state import GuardDecision, IntakeDecision, PlannedSearch, Requirement, SearchPlan

    req = Requirement(requirement_id="R1", description="Giá xe VF 6", kind="fact")
    decision = IntakeDecision(
        guard_decision=GuardDecision(decision="allow", reason="none"),
        task="knowledge",
        route="complex",
        requirements=[req],
        product_models=["VF 6"],
    )
    search = PlannedSearch(
        query="Giá niêm yết VF 6",
        product_model="VF 6",
        document_type="product_specs",
        requirement_ids=["R1"],
    )
    plan = SearchPlan(searches=[search])

    # Query only refers to 'xe đó', but memory_summary specifies VF 6!
    state = {
        "query": "Giá của xe đó bao nhiêu?",
        "customer_context": "",
        "memory_summary": "[Thông tin ngữ cảnh: Mẫu xe quan tâm: VF 6]",
        "history": [],
        "requirements": [req],
        "analysis": decision,
    }

    # Should not raise ValueError("model without input entity")
    planning.validate_plan(plan, state)

