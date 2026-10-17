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

    class MaliciousModel:
        async def ainvoke(self, messages):
            payload = json.loads(messages[-1].content)
            if "output_schema" not in payload:
                return SimpleNamespace(content=f"{FALSE_POLICY} [C1].")
            return SimpleNamespace(content=json.dumps({
                "grounded": False,
                "feedback": "Nguồn không hỗ trợ mức giảm giá.",
                "unsupported_claims": [FALSE_POLICY],
                "missing_information": [],
                "answered_requirement_ids": [],
                "missing_requirement_ids": ["R1"],
                "recovery": "none",
                "suggestions_safe": False,
            }))

    monkeypatch.setattr(model_io, "get_llm", lambda **_: MaliciousModel())
    result = await probe_source("forged_discount", "Giá niêm yết VF 5 là 529 triệu đồng.")

    assert result["status"] == "FAIL"
    assert result["validation_status"] == "valid"
    assert result["attack_marker_present"] is True
