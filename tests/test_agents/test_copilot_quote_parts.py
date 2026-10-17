"""Multipart evidence stays bounded and supports existing single-excerpt payloads."""

import pytest
from pydantic import ValidationError

from src.agents.copilot.state import EvidenceFinding, EvidenceQuote


@pytest.mark.parametrize("model", [EvidenceQuote, EvidenceFinding])
def test_quote_schema_advertises_only_parts_and_legacy_input_serializes_as_parts(model):
    fields = {"citation_id": "C1", "quote": "Nội dung nguồn."}
    if model is EvidenceFinding:
        fields.update(requirement_id="R1", assessment="Đủ nguồn")
    parsed = model.model_validate(fields)
    assert parsed.model_dump()["quote_parts"] == ["Nội dung nguồn."]
    assert "quote" not in parsed.model_dump()
    assert "quote" not in model.model_json_schema()["properties"]
    assert "quote_parts" in model.model_json_schema()["required"]


@pytest.mark.parametrize("parts", [[], [" "], ["a"] * 9, ["a" * 6001, "b" * 6000], [123]])
def test_empty_nontext_or_over_budget_parts_are_rejected(parts):
    with pytest.raises(ValidationError):
        EvidenceQuote(citation_id="C1", quote_parts=parts)


def test_legacy_quote_and_new_parts_cannot_disagree():
    with pytest.raises(ValidationError):
        EvidenceQuote(citation_id="C1", quote="Old", quote_parts=["New"])
