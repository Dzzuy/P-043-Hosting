from pathlib import Path

import pytest

from src.agents.roleplay.evaluator import (
    EvaluationDraft,
    EvaluationError,
    KnowledgeEvidence,
    RoleplayEvaluator,
)
from src.agents.roleplay.prompts import EVALUATOR_PROMPT_VERSION, EVALUATOR_SYSTEM_PROMPT
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import AdvisorFactualClaim, RoleplayMessage, RoleplayState, TerminationStatus
from src.models.evaluation import CriterionType, ReviewStatus

SCENARIOS = Path("data/scenarios/scenarios.json")


class CapturingEvaluationModel:
    def __init__(self, output):
        self.output = output
        self.calls = []

    async def evaluate(self, *, system_prompt, context):
        self.calls.append({"system_prompt": system_prompt, "context": context})
        return self.output


@pytest.fixture
def scenario():
    return ScenarioRepository(SCENARIOS).get("SCENARIO_01_VF5_TAXI").model_copy(update={"policy_expectations": []})


@pytest.fixture
def completed_state(scenario):
    state = RoleplayState.from_scenario("session-1", scenario)
    state.messages = [
        RoleplayMessage(message_id="customer-1", role="customer", content="Anh lo chi phí sử dụng."),
        RoleplayMessage(
            message_id="advisor-1",
            role="advisor",
            content="Mỗi ngày anh thường chạy khoảng bao nhiêu km?",
        ),
        RoleplayMessage(message_id="customer-2", role="customer", content="Khoảng 180 km mỗi ngày."),
        RoleplayMessage(
            message_id="advisor-2",
            role="advisor",
            content="Chính sách A đang áp dụng cho trường hợp này.",
        ),
    ]
    state.factual_claims = [
        AdvisorFactualClaim(
            message_id="advisor-2",
            text="Chính sách A đang áp dụng",
            category="policy",
        )
    ]
    state.termination_status = TerminationStatus.ADVISOR_ENDED
    return state


def evaluation_output():
    evaluations = [
        {
            "criterion": CriterionType.NEED_DISCOVERY.value,
            "status": "assessed",
            "score": 2,
            "evidence": [
                {
                    "message_id": "advisor-1",
                    "quote": "Mỗi ngày anh thường chạy khoảng bao nhiêu km?",
                }
            ],
            "reason": "Advisor asked about daily usage.",
            "improvement_suggestion": "Ask a follow-up about charging access.",
        }
    ]
    for criterion in CriterionType:
        if criterion is CriterionType.NEED_DISCOVERY:
            continue
        evaluations.append(
            {
                "criterion": criterion.value,
                "status": "unassessed",
                "score": None,
                "evidence": [],
                "reason": "No fair opportunity occurred.",
            }
        )
    return {
        "evaluations": evaluations,
        "factual_findings": [
            {
                "claim": "Chính sách A đang áp dụng",
                "message_id": "advisor-2",
                "status": "supported",
                "source_references": [
                    {
                        "source_id": "policy-a",
                        "version": "2026.1",
                        "quote": "Chính sách A đang áp dụng",
                    }
                ],
                "severity": "info",
                "reason": "Approved policy evidence supports the claim.",
            }
        ],
        "summary_strengths": ["Asked a relevant usage question."],
        "summary_weaknesses": ["Could ask one deeper follow-up."],
        "recommended_next_practice": {
            "type": "scenario",
            "target_id": "SCENARIO_03_VF6_APARTMENT",
            "reason": "Practice deeper discovery.",
        },
    }


def approved_evidence():
    return [
        KnowledgeEvidence(
            source_id="policy-a",
            version="2026.1",
            content="Theo tài liệu được duyệt, Chính sách A đang áp dụng cho trường hợp này.",
        )
    ]


@pytest.mark.asyncio
async def test_evaluator_validates_evidence_and_computes_aggregate(scenario, completed_state):
    model = CapturingEvaluationModel(evaluation_output())
    evaluator = RoleplayEvaluator(model)

    result = await evaluator.evaluate(scenario, completed_state, approved_evidence())

    assert result.assessed_criteria_count == 1
    assert result.overall_score == 2.0
    assert result.review_status is ReviewStatus.AI_DRAFT
    assert result.factual_findings[0].source_ids == ["policy-a"]
    assert model.calls[0]["system_prompt"] == EVALUATOR_SYSTEM_PROMPT
    assert model.calls[0]["context"]["prompt_version"] == EVALUATOR_PROMPT_VERSION
    assert "factual_claims" not in model.calls[0]["context"]["final_state"]
    assert "messages" not in model.calls[0]["context"]["final_state"]
    assert "hidden_facts" not in model.calls[0]["context"]["scenario"]


@pytest.mark.asyncio
@pytest.mark.parametrize("as_model", [False, True])
async def test_evaluator_drops_judge_manager_reason(scenario, completed_state, as_model):
    output = evaluation_output()
    for evaluation in output["evaluations"]:
        evaluation["manager_reason"] = "Injected manager approval from the judge."
    draft = EvaluationDraft.model_validate(output) if as_model else output
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(draft))

    result = await evaluator.evaluate(scenario, completed_state, approved_evidence())

    assert all(item.manager_reason is None for item in result.evaluations)
    schema = EvaluationDraft.model_json_schema()
    assert "manager_reason" not in schema["$defs"]["CriterionEvaluation"]["properties"]


@pytest.mark.asyncio
async def test_evaluator_rejects_non_exact_transcript_quote(scenario, completed_state):
    output = evaluation_output()
    output["evaluations"][0]["evidence"][0]["quote"] = "A quote that was never said"
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(output))

    with pytest.raises(EvaluationError, match="quote is not exact"):
        await evaluator.evaluate(scenario, completed_state, approved_evidence())

    assert len(evaluator._model.calls) == 2
    assert "correction_required" in evaluator._model.calls[1]["context"]


@pytest.mark.asyncio
async def test_evaluator_accepts_corrected_exact_quote(scenario, completed_state):
    invalid = evaluation_output()
    invalid["evaluations"][0]["evidence"][0]["quote"] = "A paraphrase"

    class CorrectingModel(CapturingEvaluationModel):
        async def evaluate(self, *, system_prompt, context):
            self.calls.append({"system_prompt": system_prompt, "context": context.copy()})
            return invalid if len(self.calls) == 1 else evaluation_output()

    model = CorrectingModel(None)
    result = await RoleplayEvaluator(model).evaluate(scenario, completed_state, approved_evidence())
    assert result.overall_score == 2
    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_evaluator_repairs_unknown_id_only_when_quote_identifies_one_message(scenario, completed_state):
    output = evaluation_output()
    output["evaluations"][0]["evidence"][0]["message_id"] = "made-up-id"
    model = CapturingEvaluationModel(output)

    result = await RoleplayEvaluator(model).evaluate(scenario, completed_state, approved_evidence())

    assert result.evaluations[0].evidence[0].message_id == "advisor-1"
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_evaluator_retries_unidentifiable_message_id_once(scenario, completed_state):
    output = evaluation_output()
    output["evaluations"][0]["evidence"][0].update(message_id="made-up-id", quote="Not in the transcript")
    model = CapturingEvaluationModel(output)

    with pytest.raises(EvaluationError, match="unknown message_id"):
        await RoleplayEvaluator(model).evaluate(scenario, completed_state, approved_evidence())

    assert len(model.calls) == 2
    assert "correction_required" in model.calls[1]["context"]


@pytest.mark.asyncio
async def test_evaluator_rejects_unknown_id_when_exact_quote_is_ambiguous(scenario, completed_state):
    completed_state.messages[0].content = "Dạ. Anh lo chi phí sử dụng."
    completed_state.messages[2].content = "Dạ. Khoảng 180 km mỗi ngày."
    output = evaluation_output()
    output["evaluations"][0]["evidence"][0].update(message_id="made-up-id", quote="Dạ.")
    model = CapturingEvaluationModel(output)

    with pytest.raises(EvaluationError, match="unknown message_id"):
        await RoleplayEvaluator(model).evaluate(scenario, completed_state, approved_evidence())

    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_evaluator_retries_when_model_quote_changes_a_word(scenario, completed_state):
    output = evaluation_output()
    output["evaluations"][0]["evidence"][0]["quote"] = "Mỗi ngày anh thường chạy bao nhiêu km?"
    model = CapturingEvaluationModel(output)

    with pytest.raises(EvaluationError, match="quote is not exact"):
        await RoleplayEvaluator(model).evaluate(scenario, completed_state, approved_evidence())

    assert len(model.calls) == 2


@pytest.mark.asyncio
async def test_evaluator_accepts_legacy_claim_with_only_casing_difference(scenario, completed_state):
    completed_state.factual_claims[0].text = "Chính sách A đang áp dụng"
    completed_state.messages[-1].content = "chính sách A đang áp dụng cho trường hợp này."
    output = evaluation_output()

    result = await RoleplayEvaluator(CapturingEvaluationModel(output)).evaluate(
        scenario, completed_state, approved_evidence()
    )

    assert result.factual_findings[0].status.value == "supported"


@pytest.mark.asyncio
async def test_evaluator_rejects_out_of_range_v3_score(scenario, completed_state):
    output = evaluation_output()
    output["evaluations"][0]["score"] = 4
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(output))

    with pytest.raises(EvaluationError, match="invalid evaluation output"):
        await evaluator.evaluate(scenario, completed_state, approved_evidence())


@pytest.mark.asyncio
async def test_score_three_requires_customer_and_advisor_turns(scenario, completed_state):
    output = evaluation_output()
    output["evaluations"][0]["score"] = 3
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(output))

    with pytest.raises(EvaluationError, match="customer context evidence"):
        await evaluator.evaluate(scenario, completed_state, approved_evidence())

    output["evaluations"][0]["evidence"].append({"message_id": "customer-2", "quote": "Khoảng 180 km mỗi ngày."})
    result = await evaluator.evaluate(scenario, completed_state, approved_evidence())
    assert result.overall_score == 3


@pytest.mark.asyncio
async def test_evaluator_rejects_unsupported_factual_source(scenario, completed_state):
    output = evaluation_output()
    output["factual_findings"][0]["source_references"][0]["source_id"] = "unknown"
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(output))

    with pytest.raises(EvaluationError, match="unknown source_id"):
        await evaluator.evaluate(scenario, completed_state, approved_evidence())


@pytest.mark.asyncio
async def test_evaluator_rejects_model_supplied_aggregate(scenario, completed_state):
    output = evaluation_output()
    output["overall_score"] = 5
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(output))

    with pytest.raises(EvaluationError, match="invalid evaluation output"):
        await evaluator.evaluate(scenario, completed_state, approved_evidence())


@pytest.mark.asyncio
async def test_evaluator_rejects_missing_recorded_factual_claim(scenario, completed_state):
    output = evaluation_output()
    output["factual_findings"] = []
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(output))

    with pytest.raises(EvaluationError, match="omitted recorded factual claims"):
        await evaluator.evaluate(scenario, completed_state, approved_evidence())


@pytest.mark.asyncio
async def test_evaluator_repairs_only_missing_claims_in_bounded_batches(scenario, completed_state):
    completed_state.factual_claims = [
        AdvisorFactualClaim(message_id="advisor-2", text=f"Chính sách {index}", category="policy")
        for index in range(1, 26)
    ]
    completed_state.messages[-1].content = " ".join(claim.text for claim in completed_state.factual_claims)
    output = evaluation_output()
    output["factual_findings"] = []

    class RepairingModel(CapturingEvaluationModel):
        def __init__(self):
            super().__init__(output)
            self.batches = []

        async def evaluate_factual_claims(self, *, system_prompt, context):
            self.batches.append(context["factual_claims"])
            return {
                "factual_findings": [
                    {
                        "message_id": claim["message_id"],
                        "claim": claim["text"],
                        "status": "unverifiable",
                        "reason": "Nguồn hiện có không đủ xác minh.",
                    }
                    for claim in context["factual_claims"]
                ]
            }

    model = RepairingModel()
    result = await RoleplayEvaluator(model).evaluate(scenario, completed_state, approved_evidence())
    assert len(result.factual_findings) == 25
    assert [len(batch) for batch in model.batches] == [4, 4, 4, 4, 4, 4, 1]


@pytest.mark.asyncio
async def test_evaluator_rejects_incomplete_factual_repair(scenario, completed_state):
    output = evaluation_output()
    output["factual_findings"] = []

    class IncompleteModel(CapturingEvaluationModel):
        async def evaluate_factual_claims(self, *, system_prompt, context):
            return {"factual_findings": []}

    with pytest.raises(EvaluationError, match="exactly the requested claims"):
        await RoleplayEvaluator(IncompleteModel(output)).evaluate(scenario, completed_state, approved_evidence())


@pytest.mark.asyncio
async def test_evaluator_retries_factual_batch_with_exact_pair(scenario, completed_state):
    output = evaluation_output()
    output["factual_findings"] = []

    class CorrectingModel(CapturingEvaluationModel):
        def __init__(self):
            super().__init__(output)
            self.repair_contexts = []

        async def evaluate_factual_claims(self, *, system_prompt, context):
            self.repair_contexts.append(context.copy())
            claim = context["factual_claims"][0]
            if len(self.repair_contexts) == 1:
                return {
                    "factual_findings": [
                        {
                            "message_id": claim["message_id"],
                            "claim": "paraphrase",
                            "status": "unverifiable",
                            "reason": "Chưa đủ nguồn.",
                        }
                    ]
                }
            return {
                "factual_findings": [
                    {
                        "message_id": claim["message_id"],
                        "claim": claim["text"],
                        "status": "unverifiable",
                        "reason": "Chưa đủ nguồn.",
                    }
                ]
            }

    model = CorrectingModel()
    result = await RoleplayEvaluator(model).evaluate(scenario, completed_state, approved_evidence())

    assert result.factual_findings[0].claim == completed_state.factual_claims[0].text
    assert len(model.repair_contexts) == 2
    assert "correction_required" in model.repair_contexts[1]


@pytest.mark.asyncio
async def test_evaluator_rejects_duplicate_factual_finding(scenario, completed_state):
    output = evaluation_output()
    output["factual_findings"].append(output["factual_findings"][0].copy())
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(output))

    with pytest.raises(EvaluationError, match="duplicate claims"):
        await evaluator.evaluate(scenario, completed_state, approved_evidence())


@pytest.mark.asyncio
async def test_active_session_cannot_be_evaluated(scenario, completed_state):
    completed_state.termination_status = TerminationStatus.ACTIVE
    evaluator = RoleplayEvaluator(CapturingEvaluationModel(evaluation_output()))

    with pytest.raises(EvaluationError, match="active role-play"):
        await evaluator.evaluate(scenario, completed_state, approved_evidence())


@pytest.mark.asyncio
async def test_config_context_and_deterministic_metadata(scenario, completed_state, caplog):
    output = evaluation_output()
    output["recommended_next_practice"]["target_id"] = "missing-scenario"
    model = CapturingEvaluationModel(output)
    completed_state.__dict__["closing_outcome"] = "close"
    result = await RoleplayEvaluator(model, judge_model="configured-judge").evaluate(
        scenario, completed_state, approved_evidence()
    )
    context = model.calls[0]["context"]
    assert all("ideal_sales_response" not in item for item in context["scenario"]["objections"])
    assert "acceptable_outcomes" in context["scenario"]
    assert "policy_expectations" in context["scenario"]
    assert result.closing_outcome == "close"
    assert result.closing_outcome_label == scenario.acceptable_outcomes[0].label
    assert result.judge_model == "configured-judge"
    assert result.recommended_next_practice is None
    assert "missing-scenario" in caplog.text


@pytest.mark.asyncio
async def test_misconduct_caps_scores(scenario, completed_state):
    completed_state.__dict__["termination_status"] = "advisor_misconduct"
    result = await RoleplayEvaluator(CapturingEvaluationModel(evaluation_output())).evaluate(
        scenario, completed_state, approved_evidence()
    )
    assert all(item.score is None or item.score == 1 for item in result.evaluations)
    assert "sai phạm" in result.summary_weaknesses[0]


@pytest.mark.asyncio
async def test_expected_policies_cannot_be_unassessed(scenario, completed_state):
    scenario.policy_expectations = ScenarioRepository().get(scenario.scenario_id).policy_expectations
    with pytest.raises(EvaluationError, match="policy_accuracy must be assessed"):
        await RoleplayEvaluator(CapturingEvaluationModel(evaluation_output())).evaluate(
            scenario, completed_state, approved_evidence()
        )


@pytest.mark.asyncio
async def test_one_turn_misconduct_allows_unassessed_policy(scenario, completed_state):
    scenario.policy_expectations = ScenarioRepository().get(scenario.scenario_id).policy_expectations
    completed_state.termination_status = TerminationStatus.ADVISOR_MISCONDUCT
    completed_state.messages = [RoleplayMessage(message_id="advisor-1", role="advisor", content="Đồ ngu")]
    completed_state.factual_claims = []
    output = evaluation_output()
    output["evaluations"][0]["evidence"][0]["quote"] = "Đồ ngu"
    output["factual_findings"] = []
    result = await RoleplayEvaluator(CapturingEvaluationModel(output)).evaluate(scenario, completed_state, [])
    assert result.evaluations[3].score is None


@pytest.mark.asyncio
async def test_policy_requirement_retries_with_specific_correction(scenario, completed_state):
    scenario.policy_expectations = ScenarioRepository().get(scenario.scenario_id).policy_expectations

    class CorrectingModel(CapturingEvaluationModel):
        async def evaluate(self, *, system_prompt, context):
            self.calls.append(context.copy())
            output = evaluation_output()
            if len(self.calls) == 2:
                policy = next(item for item in output["evaluations"] if item["criterion"] == "policy_accuracy")
                policy.update(
                    status="assessed",
                    score=1,
                    evidence=[{"message_id": "advisor-2", "quote": completed_state.messages[-1].content}],
                )
            return output

    model = CorrectingModel(None)
    await RoleplayEvaluator(model).evaluate(scenario, completed_state, approved_evidence())
    assert len(model.calls) == 2
    assert "policy_accuracy" in model.calls[1]["correction_required"]


@pytest.mark.asyncio
async def test_no_policy_discussion_allows_unassessed_or_evidenced_missed_opportunity(scenario, completed_state):
    scenario.policy_expectations = ScenarioRepository().get(scenario.scenario_id).policy_expectations
    completed_state.messages[-1].content = "Anh có muốn đặt lịch lái thử không?"
    completed_state.factual_claims = []
    output = evaluation_output()
    output["factual_findings"] = []
    model = CapturingEvaluationModel(output)
    await RoleplayEvaluator(model).evaluate(scenario, completed_state, [])
    policy = next(item for item in output["evaluations"] if item["criterion"] == "policy_accuracy")
    policy.update(
        status="assessed",
        score=1,
        evidence=[{"message_id": "advisor-2", "quote": completed_state.messages[-1].content}],
    )
    result = await RoleplayEvaluator(model).evaluate(scenario, completed_state, [])
    assert next(item for item in result.evaluations if item.criterion is CriterionType.POLICY_ACCURACY).score == 1


@pytest.mark.asyncio
async def test_current_policy_context_uses_resolver_and_session_date(scenario, completed_state):
    from datetime import UTC, date, datetime

    from src.agents.roleplay.contracts import PolicyExpectation
    from src.integrations.practice_policy import ResolvedPolicy, ResolvedPolicySource

    expectation = PolicyExpectation(
        policy_id="current",
        level="expected",
        topic="Chính sách hiện hành",
        lookup={"query": "Chính sách", "document_type": "policy", "product_model": "ALL"},
    )
    scenario = scenario.model_copy(update={"policy_expectations": [expectation]})
    completed_state.created_at = datetime(2026, 10, 1, 18, tzinfo=UTC)

    class Resolver:
        def resolve(self, supplied_scenario, target_date):
            assert supplied_scenario is scenario
            assert target_date == date(2026, 10, 2)
            return [
                ResolvedPolicy(
                    policy_id="current",
                    level="expected",
                    topic=expectation.topic,
                    status="found",
                    sources=[
                        ResolvedPolicySource(
                            document_id="policy-a", version="2026.1", quote=approved_evidence()[0].content
                        )
                    ],
                )
            ]

    output = evaluation_output()
    policy_score = next(item for item in output["evaluations"] if item["criterion"] == "policy_accuracy")
    policy_score.update(
        status="assessed", score=2, evidence=[{"message_id": "advisor-2", "quote": "Chính sách A đang áp dụng"}]
    )
    model = CapturingEvaluationModel(output)
    result = await RoleplayEvaluator(model, policy_resolver=Resolver()).evaluate(
        scenario,
        completed_state,
        approved_evidence(),
    )
    context = model.calls[0]["context"]
    assert context["current_policy_evidence"][0]["sources"][0]["document_id"] == "policy-a"
    assert context["scenario"]["policy_expectations"] == [
        {
            "policy_id": "current",
            "level": "expected",
            "topic": "Chính sách hiện hành",
            "requires_eligibility_check": False,
        }
    ]
    assert result.factual_findings[0].status == "supported"
