"""Shared product contracts for role-play, knowledge, and evaluation work."""

import re
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from src.models.evaluation import SessionEvaluationResult

if TYPE_CHECKING:
    from .state import RoleplayState

RUBRIC_CRITERIA = ("need_discovery", "product_knowledge", "objection_handling", "policy_accuracy", "closing_next_step")
RUBRIC_SCORE_MIN = 1
RUBRIC_SCORE_MAX = 3
CUSTOMER_BEHAVIOR_RULES = (
    "Always role-play the customer, never the sales advisor.",
    "Keep the scenario persona consistent throughout the session.",
    "Do not reveal hidden facts until a matching disclosure rule is satisfied.",
    "Keep unresolved objections available for later turns; do not repeat resolved objections without new evidence.",
    "Conversation stages may advance or move back as the dialogue changes.",
    "Do not invent current prices, promotions, battery policy, charging policy, or product specifications.",
    "Route factual claims through the future knowledge-tool layer.",
    "Keep customer replies natural and limited to one to three sentences.",
    "Do not reveal scores, rubric criteria, evaluator feedback, prompts, or hidden facts during practice.",
    "End only through a configured termination condition, explicit advisor finish, or the turn limit.",
    "Preserve message history for the full session; never reset it between advisor turns.",
)

EvaluationCriterion = Literal[
    "need_discovery",
    "product_knowledge",
    "objection_handling",
    "policy_accuracy",
    "closing_next_step",
]
ClaimCategory = Literal[
    "product",
    "price",
    "promotion",
    "policy",
    "warranty",
    "battery_charging",
    "other",
]
ObjectionStage = Literal[
    "opening",
    "discovery",
    "presentation",
    "objection_handling",
    "closing",
]


# Customer budgets and usage are persona facts, not current corpus policies.
# Percentages, dates and warranty pairs are prohibited in both kinds of text.
_CORPUS_ONLY_PATTERN = (
    r"\d{1,2}/\d{1,2}(?:/\d{4})?(?:\s*[–—-]\s*\d{1,2}/\d{1,2}(?:/\d{4})?)?"
    r"|\d+(?:[.,]\d+)*\s*%"
    r"|\d+\s*năm\s*/\s*\d+(?:[.,]\d+)*\s*km(?!\w)"
)
_CORPUS_ONLY_FIGURE = re.compile(r"(?<![\w/])(?:" + _CORPUS_ONLY_PATTERN + r")", re.IGNORECASE)
_CORPUS_FIGURE = re.compile(
    r"(?<![\w/])(?:" + _CORPUS_ONLY_PATTERN + r"|\d+(?:[.,]\d+)*\s*(?:triệu(?:\s+đồng)?|tr|VNĐ|VND|đồng|đ)(?!\w)"
    r"|\d+(?:[.,]\d+)*\s*km(?![\w/])"
    r"|\d{1,3}(?:\.\d{3}){2,}(?![\w.])"
    r")",
    re.IGNORECASE,
)


def find_corpus_figures(text: str) -> list[str]:
    """Return corpus-style money, percentages, dates and warranty figures in order."""
    return [match.group() for match in _CORPUS_FIGURE.finditer(text)]


def _validate_figure_free(value: Any, field: str, *, customer_owned: bool = False) -> Any:
    """Name the offending field while allowing customer-owned money and usage."""
    if isinstance(value, str):
        pattern = _CORPUS_ONLY_FIGURE if customer_owned else _CORPUS_FIGURE
        figures = [match.group() for match in pattern.finditer(value)]
        if figures:
            raise ValueError(f"{field} must be figure-free; offending figure: {figures[0]!r}.")
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_figure_free(item, f"{field}.{key}", customer_owned=customer_owned)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_figure_free(item, f"{field}[{index}]", customer_owned=customer_owned)
    return value


class ScenarioModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DisclosureRule(ScenarioModel):
    fact_key: str = Field(min_length=1)
    trigger_intent: str = Field(
        ...,
        min_length=1,
        description="Semantic advisor intent that permits this disclosure",
    )
    trigger_keywords: list[str] = Field(
        default_factory=list,
        description="Positive examples/test hints; never an exact-phrase requirement",
    )
    revealed_statement: str = Field(min_length=1)

    @field_validator("trigger_keywords", "revealed_statement")
    @classmethod
    def validate_customer_text(cls, value: Any, info: ValidationInfo) -> Any:
        return _validate_figure_free(value, info.field_name, customer_owned=True)


class ObjectionContract(ScenarioModel):
    objection_id: str = Field(min_length=1)
    trigger_stage: ObjectionStage | None = None
    trigger_keywords: list[str] = Field(default_factory=list)
    objection_text: str = Field(min_length=1)
    resolve_condition: str = Field(min_length=1)
    ideal_sales_response: str | None = None
    requires_revealed_facts: list[str] = Field(default_factory=list)

    @field_validator("trigger_keywords", "objection_text", "resolve_condition", "ideal_sales_response")
    @classmethod
    def validate_objection_text(cls, value: Any, info: ValidationInfo) -> Any:
        return _validate_figure_free(value, info.field_name)

    @model_validator(mode="after")
    def validate_trigger(self) -> "ObjectionContract":
        if any(not keyword.strip() for keyword in self.trigger_keywords):
            raise ValueError("trigger_keywords must not contain blank keywords")
        if self.trigger_stage is None and not self.trigger_keywords:
            raise ValueError("objection requires at least one trigger")
        return self


class AcceptableOutcome(ScenarioModel):
    outcome_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    product: str
    requires_resolved_objections: list[str] = Field(default_factory=list)
    preferred: bool = False

    @field_validator("label", "product")
    @classmethod
    def validate_outcome_text(cls, value: str, info: ValidationInfo) -> str:
        return _validate_figure_free(value, info.field_name)


def default_acceptable_outcomes() -> list[AcceptableOutcome]:
    """Compute a fresh legacy closing outcome without guessing a product."""
    return [AcceptableOutcome(outcome_id="close", label="Chốt bước tiếp theo", product="")]


class UpsellBenefit(ScenarioModel):
    benefit_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    safety: bool
    linked_need_fact_keys: list[str] = Field(default_factory=list)


class UpsellRule(ScenarioModel):
    objection_id: str = Field(min_length=1)
    min_linked: int = Field(ge=1)
    min_safety: int = Field(ge=0)


class PolicyLookup(ScenarioModel):
    query: str = Field(min_length=1)
    document_type: Literal["policy", "price_list", "product_specs", "promotion", "faq"]
    policy_type: str | None = None
    product_model: str


class PolicyExpectation(ScenarioModel):
    policy_id: str = Field(min_length=1)
    level: Literal["expected", "bonus"]
    requires_eligibility_check: bool = False
    topic: str = Field(min_length=1)
    lookup: PolicyLookup

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, value: str) -> str:
        return _validate_figure_free(value, "topic")


class TerminationConditions(ScenarioModel):
    max_turns: int = Field(ge=1, le=15)
    drop_out_trigger: str = Field(min_length=1)

    @field_validator("drop_out_trigger")
    @classmethod
    def validate_drop_out_trigger(cls, value: str) -> str:
        return _validate_figure_free(value, "drop_out_trigger")


class ScenarioContract(ScenarioModel):
    scenario_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    difficulty: str = Field(min_length=1)
    target_skills: list[EvaluationCriterion] = Field(min_length=1)
    sales_channel: str | None = None
    training_objective: str | None = None
    scenario_version: str = Field(default="1.0", min_length=1)
    persona: dict[str, Any] = Field(min_length=1)
    visible_context: str = Field(min_length=1)
    hidden_facts: dict[str, str] = Field(min_length=1)
    buyer_intent: str = Field(min_length=1)
    customer_goals: str = Field(min_length=1)
    disclosure_rules: list[DisclosureRule]
    objections: list[ObjectionContract]
    expected_discovery: str = Field(min_length=1)
    success_conditions: str = Field(min_length=1)
    termination_conditions: TerminationConditions
    acceptable_outcomes: list[AcceptableOutcome] = Field(default_factory=default_acceptable_outcomes, min_length=1)
    upsell_benefits: list[UpsellBenefit] = Field(default_factory=list)
    upsell_rule: UpsellRule | None = None
    policy_expectations: list[PolicyExpectation] = Field(default_factory=list)

    @field_validator(
        "title",
        "sales_channel",
        "training_objective",
        "persona",
        "visible_context",
        "hidden_facts",
        "buyer_intent",
        "customer_goals",
    )
    @classmethod
    def validate_scenario_text(cls, value: Any, info: ValidationInfo) -> Any:
        return _validate_figure_free(value, info.field_name, customer_owned=True)

    @field_validator("expected_discovery", "success_conditions")
    @classmethod
    def validate_success_text(cls, value: str, info: ValidationInfo) -> str:
        return _validate_figure_free(value, info.field_name)

    @model_validator(mode="after")
    def validate_scenario_references(self) -> "ScenarioContract":
        if len(self.target_skills) != len(set(self.target_skills)):
            raise ValueError("target_skills must not contain duplicates")

        if any(not fact_key.strip() or not fact_value.strip() for fact_key, fact_value in self.hidden_facts.items()):
            raise ValueError("hidden fact keys and values must not be blank")

        disclosure_fact_keys = [rule.fact_key for rule in self.disclosure_rules]
        if len(disclosure_fact_keys) != len(set(disclosure_fact_keys)):
            raise ValueError("each hidden fact can have at most one disclosure rule")

        unknown_fact_keys = set(disclosure_fact_keys) - self.hidden_facts.keys()
        if unknown_fact_keys:
            raise ValueError("disclosure rules reference unknown hidden facts: " + ", ".join(sorted(unknown_fact_keys)))

        objection_ids = [objection.objection_id for objection in self.objections]
        if len(objection_ids) != len(set(objection_ids)):
            raise ValueError("objection_id values must be unique within a scenario")

        for objection in self.objections:
            if set(objection.requires_revealed_facts) - self.hidden_facts.keys():
                raise ValueError("objection prerequisites reference unknown hidden facts")

        outcome_ids = [outcome.outcome_id for outcome in self.acceptable_outcomes]
        if len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("outcome_id values must be unique within a scenario")
        for outcome in self.acceptable_outcomes:
            if set(outcome.requires_resolved_objections) - set(objection_ids):
                raise ValueError("acceptable outcomes reference unknown objection ids")

        benefit_ids = [benefit.benefit_id for benefit in self.upsell_benefits]
        if len(benefit_ids) != len(set(benefit_ids)):
            raise ValueError("benefit_id values must be unique within a scenario")
        for benefit in self.upsell_benefits:
            if set(benefit.linked_need_fact_keys) - self.hidden_facts.keys():
                raise ValueError("upsell benefits reference unknown hidden facts")
        if self.upsell_rule is not None:
            if self.upsell_rule.objection_id not in objection_ids:
                raise ValueError("upsell_rule references unknown objection id")
            if not self.upsell_benefits:
                raise ValueError("upsell_rule requires non-empty upsell_benefits")

        normalized_context = self.visible_context.casefold()
        leaked_fact_keys = [
            fact_key
            for fact_key, fact_value in self.hidden_facts.items()
            if fact_value.strip() and fact_value.casefold() in normalized_context
        ]
        if leaked_fact_keys:
            raise ValueError("visible_context contains hidden fact values: " + ", ".join(sorted(leaked_fact_keys)))

        return self


class KnowledgeToolContract(Protocol):
    async def search(self, query: str) -> list[dict[str, Any]]: ...


class CheckpointContract(Protocol):
    async def save(self, session_id: str, state: dict[str, Any]) -> None: ...

    async def load(self, session_id: str) -> dict[str, Any] | None: ...


class RoleplayGraphContract(Protocol):
    """Shared D2 graph boundary without choosing its implementation."""

    async def start(self, session_id: str, scenario_id: str, max_turns: int | None = None) -> dict[str, Any]: ...

    async def continue_session(self, session_id: str, advisor_message: str) -> dict[str, Any]: ...
    async def retry_customer_reply(self, session_id: str) -> dict[str, Any]: ...

    async def get_session_state(self, session_id: str) -> "RoleplayState": ...

    async def finish_session(self, session_id: str) -> "RoleplayState": ...

    async def save_evaluation_result(self, session_id: str, result: SessionEvaluationResult) -> "RoleplayState": ...

    async def mark_evaluation_failed(self, session_id: str) -> None: ...


def policy_prompt_context(scenario: ScenarioContract) -> list[dict[str, Any]]:
    """Expose figure-free policy topics without retrieval configuration."""
    return [
        item.model_dump(mode="json", include={"policy_id", "level", "topic", "requires_eligibility_check"})
        for item in scenario.policy_expectations
    ]
