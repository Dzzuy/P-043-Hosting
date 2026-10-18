"""Contracts and full graph regressions for structured Copilot generation/checking."""

import copy
import json
from types import SimpleNamespace

import pytest
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from src.agents.copilot import model_io
from src.agents.copilot.errors import CopilotModelOutputError
from src.agents.copilot.graph import copilot_agent
from src.agents.copilot.nodes import answer, guard, verification
from src.agents.copilot.runtime import CopilotDependencyError
from src.agents.copilot.state import (
    GeneratedAnswer,
    IntakeDecision,
    Requirement,
    StructuredGroundingReview,
)
from src.agents.copilot.validation.structured import (
    render_answer,
    summarize_grounding_review,
    validate_generated_answer,
    validate_grounding_review,
)
from tests.test_agents.test_copilot_agentic import checked, draft_state, generated, intake, offline  # noqa: F401


def review():
    return {
        "claim_verdicts": checked()["claim_verdicts"],
        "requirement_verdicts": checked()["requirement_verdicts"],
        "suggestions_safe": True,
    }


def structured_state():
    state = draft_state()
    state["generated_answer"] = GeneratedAnswer(**generated())
    state["draft_answer"] = render_answer(state["generated_answer"])
    return state


class ContractModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.payloads = []

    async def ainvoke(self, messages):
        self.payloads.append(json.loads(messages[-1].content))
        return SimpleNamespace(content=json.dumps(next(self.outputs), ensure_ascii=False))


def use_model(monkeypatch, outputs):
    model = ContractModel(outputs)
    monkeypatch.setattr(model_io, "get_llm", lambda **kwargs: model)
    return model


@pytest.mark.parametrize("schema", [IntakeDecision, GeneratedAnswer, StructuredGroundingReview])
def test_native_schema_requires_all_fields_and_forbids_extras_recursively(schema):
    model = ChatOpenAI(api_key="test", base_url="https://openrouter.ai/api/v1")
    wire = model_io._bind_schema(model, schema, "openrouter").kwargs["response_format"]["json_schema"]

    def inspect(value):
        if isinstance(value, dict):
            assert "default" not in value
            if "properties" in value:
                assert set(value["required"]) == set(value["properties"])
                assert value["additionalProperties"] is False
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    assert wire["strict"] is True
    assert "temperature" not in model_io._bind_schema(model, schema, "openrouter").bound._default_params
    inspect(wire["schema"])


@pytest.mark.asyncio
async def test_native_schema_is_bound_on_real_langchain_client(monkeypatch):
    seen = []
    model = ChatOpenAI(api_key="test", base_url="https://openrouter.ai/api/v1")

    async def invoke(self, messages, config=None, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace(content=json.dumps(generated()))

    monkeypatch.setattr(ChatOpenAI, "ainvoke", invoke)
    monkeypatch.setattr(model_io, "get_llm", lambda **kwargs: model)
    await model_io._invoke_json(draft_state(), "system", {}, GeneratedAnswer)
    assert seen[0]["response_format"]["type"] == "json_schema"
    assert seen[0]["extra_body"]["provider"]["require_parameters"] is True


@pytest.mark.asyncio
async def test_unsupported_native_provider_fails_without_calling_model(monkeypatch):
    model = ChatOpenAI(api_key="test", base_url="https://api.deepseek.com/v1")

    async def forbidden(*args, **kwargs):
        pytest.fail("unsupported strict adapter must not send a request")

    monkeypatch.setattr(ChatOpenAI, "ainvoke", forbidden)
    monkeypatch.setattr(model_io, "get_llm", lambda **kwargs: model)
    state = draft_state()
    with pytest.raises(CopilotDependencyError, match="configuration"):
        await model_io._invoke_json(state, "system", {}, GeneratedAnswer)
    assert state["runtime"].attempts == 1


@pytest.mark.asyncio
async def test_strict_output_does_not_repair_markdown_wrapped_json(monkeypatch):
    class FencedModel:
        async def ainvoke(self, messages):
            return SimpleNamespace(content="```json\n" + json.dumps(generated()) + "\n```")

    monkeypatch.setattr(model_io, "get_llm", lambda **kwargs: FencedModel())
    state = draft_state()
    with pytest.raises(CopilotModelOutputError):
        await model_io._invoke_json(state, "system", {}, GeneratedAnswer)
    assert state["runtime"].attempts == 1


@pytest.mark.parametrize(
    "change",
    [
        {"citation_ids": ["C999"]},
        {"requirement_ids": ["R99"]},
        {"text": "Một phát biểu với marker giả [C1]"},
        {"text": "Một phát biểu với marker sai [C-2]"},
    ],
)
def test_generation_cannot_forge_links_or_inline_citations(change):
    data = generated()
    data["claims"][0].update(change)
    with pytest.raises(ValueError):
        validate_generated_answer(GeneratedAnswer(**data), draft_state())


def test_factual_claim_cannot_omit_citations():
    data = generated()
    data["claims"][0]["citation_ids"] = []
    with pytest.raises(ValidationError):
        GeneratedAnswer(**data)


def test_typed_requirement_model_rejects_sources_for_another_vehicle():
    state = structured_state()
    state["requirements"][0].product_model = "VF 6"
    with pytest.raises(ValueError, match="outside requirement model"):
        validate_generated_answer(state["generated_answer"], state)


def test_empty_and_duplicate_generation_contracts_are_rejected():
    with pytest.raises(ValidationError):
        GeneratedAnswer(claims=[])
    data = generated()
    data["claims"][0]["requirement_ids"] = ["R1", "R1"]
    with pytest.raises(ValidationError):
        GeneratedAnswer(**data)


@pytest.mark.parametrize(
    "malformation",
    [
        "omitted_claim",
        "duplicate_claim",
        "unknown_claim",
        "omitted_requirement",
        "duplicate_requirement",
        "unknown_requirement",
        "wrong_link",
        "error_on_supported",
    ],
)
def test_checker_must_cover_exact_claims_and_requirements(malformation):
    state, data = structured_state(), review()
    if malformation == "omitted_claim":
        state["generated_answer"].claims.append(copy.deepcopy(state["generated_answer"].claims[0]))
    elif malformation == "duplicate_claim":
        data["claim_verdicts"] *= 2
    elif malformation == "unknown_claim":
        data["claim_verdicts"][0]["claim_index"] = 5
    elif malformation == "omitted_requirement":
        data["requirement_verdicts"] = []
    elif malformation == "duplicate_requirement":
        data["requirement_verdicts"] *= 2
    elif malformation == "unknown_requirement":
        data["requirement_verdicts"][0]["requirement_id"] = "R99"
    elif malformation == "wrong_link":
        data["requirement_verdicts"][0]["supporting_claim_indices"] = [5]
    else:
        data["claim_verdicts"][0]["error_codes"] = ["wrong_number"]
    with pytest.raises(ValueError):
        validate_grounding_review(StructuredGroundingReview(**data), state)


@pytest.mark.parametrize("kind", ["advice", "limitation"])
def test_nonfactual_block_cannot_establish_factual_coverage(kind):
    state = structured_state()
    state["generated_answer"].claims[0].kind = kind
    verdict = summarize_grounding_review(StructuredGroundingReview(**review()), state)
    assert verdict.answered_requirement_ids == [] and verdict.missing_requirement_ids == ["R1"]


def test_coverage_cannot_link_to_supported_but_unrelated_claim():
    state = structured_state()
    state["requirements"].append(Requirement(requirement_id="R2", description="Pin VF 5"))
    data = review()
    data["requirement_verdicts"].append(
        {
            "requirement_id": "R2",
            "status": "answered",
            "supporting_claim_indices": [0],
        }
    )
    verdict = summarize_grounding_review(StructuredGroundingReview(**data), state)
    assert verdict.answered_requirement_ids == ["R1"] and verdict.missing_requirement_ids == ["R2"]


def test_external_requirement_cannot_be_marked_answered_from_corpus():
    state = structured_state()
    state["requirements"][0].kind = "external"
    with pytest.raises(ValueError, match="external"):
        validate_grounding_review(StructuredGroundingReview(**review()), state)


def test_unsafe_suggestions_prevent_whole_answer_approval():
    data = review()
    data["suggestions_safe"] = False
    verdict = summarize_grounding_review(StructuredGroundingReview(**data), structured_state())
    assert verdict.grounded is False


def test_table_rendering_keeps_citations_inside_final_cell():
    data = generated("| Xe | Quãng đường |\n| --- | --- |\n| VF 5 | 326 km |")
    result = render_answer(GeneratedAnswer(**data))
    assert result.endswith("326 km [C1] |")


@pytest.mark.asyncio
@pytest.mark.usefixtures("offline")
async def test_structured_simple_graph_uses_three_schema_calls(monkeypatch):
    model = use_model(monkeypatch, [intake(), generated(), review()])
    state = await copilot_agent.ainvoke({"query": "VF 5 đi được bao xa?"})
    assert state["final_response"].status == "answered"
    assert state["final_response"].answer.endswith("[C1]")
    assert state["grounding_review"].requirement_verdicts[0].supporting_claim_indices == [0]
    assert [p["output_contract"] for p in model.payloads] == [
        "IntakeDecision",
        "GeneratedAnswer",
        "StructuredGroundingReview",
    ]


@pytest.mark.asyncio
@pytest.mark.usefixtures("offline")
async def test_coaching_without_sources_has_structured_review(monkeypatch):
    decision = intake()
    decision.update(answer_kind="coaching", simple_search=None)
    decision["requirements"] = [{"requirement_id": "R1", "kind": "advice", "description": "Soạn lời chào"}]
    content = {
        "claims": [
            {
                "text": "Chào anh/chị, mình có thể hỗ trợ nhu cầu nào?",
                "kind": "advice",
                "requirement_ids": ["R1"],
                "citation_ids": [],
            }
        ]
    }
    use_model(monkeypatch, [decision, content, checked(scope=None)])
    state = await copilot_agent.ainvoke({"query": "Soạn lời chào cho khách"})
    assert state["final_response"].status == "answered"
    assert state["final_response"].citations == []
    assert state["tool_calls"] == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("offline")
async def test_empty_coaching_requirements_get_verbatim_goal(monkeypatch):
    decision = intake()
    decision.update(answer_kind="coaching", requirements=[], simple_search=None)
    use_model(monkeypatch, [decision])
    query = "Soạn lời mở đầu cho cuộc gọi khách hàng"
    state = await guard.analyze_and_route({"query": query})
    assert state["requirements"][0].description == query
    assert state["requirements"][0].kind == "advice"
    assert state["route"] == "generate_answer"


@pytest.mark.asyncio
@pytest.mark.usefixtures("offline")
async def test_partial_snapshot_survives_failed_second_generation(monkeypatch):
    decision = intake()
    decision["requirements"].append({"requirement_id": "R2", "description": "Dung lượng pin VF 5"})
    first = review()
    first["requirement_verdicts"].append({"requirement_id": "R2", "status": "missing"})
    first["recovery"] = "regenerate"
    use_model(monkeypatch, [decision, generated(), first, {"bad": "output"}])
    state = await copilot_agent.ainvoke({"query": "VF 5 đi được bao xa và dung lượng pin?"})
    assert state["final_response"].status == "partial"
    assert "326" in state["final_response"].answer
    assert state["final_response"].missing_information
    assert state["generation_count"] == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("offline")
async def test_intake_uses_typed_metric_without_regex_rewriting(monkeypatch):
    decision = intake()
    decision["requirements"][0].update(metric="range", product_model="VF 5", variant="Plus", qualifiers=["NEDC"])

    use_model(monkeypatch, [decision])
    result = await guard.analyze_and_route({"query": "VF 5 nạp đầy đi được bao xa?"})
    assert result["requirements"][0].metric == "range"
    assert result["requirements"][0].qualifiers == ["NEDC"]


@pytest.mark.asyncio
async def test_draft_cannot_change_after_structured_generation(monkeypatch):
    state = structured_state()
    state["draft_answer"] += " Còn được miễn phí sạc mãi mãi."
    model = use_model(monkeypatch, [])
    result = await verification.check_grounding(state)
    assert result["route"] == "fallback_response"
    assert not model.payloads


@pytest.mark.asyncio
async def test_checker_contract_error_never_publishes_unverified_answer(monkeypatch):
    state = structured_state()
    state["generation_count"] = 2
    use_model(monkeypatch, [{"grounded": True}])
    result = await verification.check_grounding(state)
    assert result["route"] == "check_grounding"
    assert result.get("verified_snapshot") is None


@pytest.mark.asyncio
async def test_generation_rejects_unknown_citation_before_checker(monkeypatch):
    use_model(monkeypatch, [generated(cid="C999")])
    result = await answer.generate_answer(draft_state())
    assert result["draft_answer"] is None
    assert result["generated_answer"] is None
