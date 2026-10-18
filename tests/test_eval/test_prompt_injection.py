"""Deterministic checks for the isolated attack harness."""

import json
from types import SimpleNamespace

import pytest

from eval.prompt_injection.run import (
    ADVISOR_ATTACKS,
    DIRECT_QUERY_ATTACKS,
    FALSE_POLICY,
    SOURCE_ATTACKS,
    probe_source,
    synthetic_hit,
)


def test_attack_suite_covers_three_untrusted_surfaces_without_real_corpus():
    assert len(SOURCE_ATTACKS) == len(DIRECT_QUERY_ATTACKS) == 3
    assert len(ADVISOR_ATTACKS) == 7
    hit = synthetic_hit("synthetic content")
    assert hit["document_id"] == "INJECTION_TEST_SOURCE"
    assert hit["content"] == "synthetic content"


@pytest.mark.asyncio
async def test_harness_flags_a_forged_policy_even_when_citation_shape_is_valid(monkeypatch):
    from src.agents.copilot import model_io
    from tests.test_agents.test_copilot_agentic import checked, generated

    class MaliciousModel:
        async def ainvoke(self, messages):
            payload = json.loads(messages[-1].content)
            output = (
                generated(FALSE_POLICY)
                if payload["output_contract"] == "GeneratedAnswer"
                else checked("unsupported", recovery="none")
            )
            return SimpleNamespace(content=json.dumps(output))

    monkeypatch.setattr(model_io, "get_llm", lambda **_: MaliciousModel())
    result = await probe_source("forged_discount", "Giá niêm yết VF 5 là 529 triệu đồng.")

    assert result["status"] == "FAIL"
    assert result["validation_status"] == "valid"
    assert result["model_status"] == "unverified"
    assert result["attack_marker_present"] is True
