"""Business state only. Runtime graph, persistence, and LLM behavior begin in D2."""

import logging
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from src.knowledge.validity import today_in_vietnam
from src.models.evaluation import SessionEvaluationResult

from .contracts import ClaimCategory, ScenarioContract


class ConversationStage(StrEnum):
    OPENING = "opening"
    DISCOVERY = "discovery"
    PRESENTATION = "presentation"
    OBJECTION_HANDLING = "objection_handling"
    CLOSING = "closing"
    FINISHED = "finished"


class TerminationStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ADVISOR_ENDED = "advisor_ended"
    DROPPED_OUT = "dropped_out"
    MAX_TURNS = "max_turns"
    ADVISOR_MISCONDUCT = "advisor_misconduct"


class EvaluationStatus(StrEnum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    FAILED = "failed"
    COMPLETE = "complete"


class RoleplayMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    role: Literal["customer", "advisor"]
    content: str = Field(min_length=1)


class AdvisorFactualClaim(BaseModel):
    """Exact advisor claim retained for grounded checks at session finish."""

    message_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    category: ClaimCategory


class LinkedBenefit(BaseModel):
    benefit_id: str
    need_fact_key: str


class RoleplayState(BaseModel):
    session_id: str
    created_at: datetime | None = None
    scenario_id: str
    difficulty: str
    sales_channel: str | None = None
    training_objective: str | None = None
    persona: dict[str, Any] = Field(default_factory=dict)
    conversation_stage: ConversationStage = ConversationStage.OPENING
    turn_count: int = Field(default=0, ge=0)
    trust_level: int = Field(default=3, ge=1, le=5)
    interest_level: int = Field(default=3, ge=1, le=5)
    visible_context: str
    hidden_facts: dict[str, str] = Field(default_factory=dict)
    revealed_facts: list[str] = Field(default_factory=list)
    spoken_fact_message_ids: dict[str, str] = Field(default_factory=dict)
    spoken_concern_message_ids: dict[str, str] = Field(default_factory=dict)
    concern_prompt_counts: dict[str, int] = Field(default_factory=dict)
    max_turns: int = Field(default=10, ge=1, le=15)
    advisor_discoveries: list[str] = Field(default_factory=list)
    active_objections: list[str] = Field(default_factory=list)
    resolved_objections: list[str] = Field(default_factory=list)
    unresolved_objections: list[str] = Field(default_factory=list)
    customer_goals: str
    current_intent: str
    current_topic: str | None = None
    pending_next_step_attempted: bool = False
    consecutive_off_topic_turns: int = Field(default=0, ge=0)
    termination_status: TerminationStatus = TerminationStatus.ACTIVE
    termination_reason: str | None = None
    closing_outcome: str | None = None
    linked_benefits: list[LinkedBenefit] = Field(default_factory=list)
    policy_mentions: list[str] = Field(default_factory=list)
    misconduct_reason: str | None = None
    evaluation_status: EvaluationStatus = EvaluationStatus.NOT_STARTED
    evaluation_result: SessionEvaluationResult | None = None
    messages: list[RoleplayMessage] = Field(default_factory=list)
    factual_claims: list[AdvisorFactualClaim] = Field(default_factory=list)

    @property
    def target_date(self) -> date:
        created = self.created_at
        if created is None:
            logging.getLogger(__name__).warning(
                "Legacy session has no creation timestamp; using today's VN date: session_id=%s", self.session_id
            )
            return today_in_vietnam()
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return created.astimezone(timezone(timedelta(hours=7))).date()

    @property
    def pending_customer_reply(self) -> bool:
        return (
            self.termination_status is TerminationStatus.ACTIVE
            and bool(self.messages)
            and self.messages[-1].role == "advisor"
        )

    @model_validator(mode="after")
    def validate_evaluation_lifecycle(self) -> "RoleplayState":
        customer_message_ids = {message.message_id for message in self.messages if message.role == "customer"}
        if any(
            fact_key not in self.revealed_facts or message_id not in customer_message_ids
            for fact_key, message_id in self.spoken_fact_message_ids.items()
        ):
            raise ValueError("spoken facts must reference an actual customer message")
        if any(message_id not in customer_message_ids for message_id in self.spoken_concern_message_ids.values()):
            raise ValueError("spoken concerns must reference an actual customer message")
        if any(count < 0 or count > 2 for count in self.concern_prompt_counts.values()):
            raise ValueError("concern prompt counts must remain within the two-prompt limit")
        if self.pending_next_step_attempted and not self.pending_customer_reply:
            raise ValueError("pending next-step context requires a pending customer reply")
        if (self.evaluation_status is EvaluationStatus.COMPLETE) != (self.evaluation_result is not None):
            raise ValueError("complete evaluation status and saved result must occur together")
        if self.evaluation_result is not None and (
            self.evaluation_result.session_id != self.session_id
            or self.evaluation_result.scenario_id != self.scenario_id
        ):
            raise ValueError("saved evaluation does not match practice session")
        if (
            self.termination_status is TerminationStatus.ACTIVE
            and self.evaluation_status is not EvaluationStatus.NOT_STARTED
        ):
            raise ValueError("active practice session cannot have an evaluation status")
        return self

    @classmethod
    def from_scenario(
        cls, session_id: str, scenario: ScenarioContract, max_turns: int | None = None
    ) -> "RoleplayState":
        objection_ids = [item.objection_id for item in scenario.objections]
        return cls(
            session_id=session_id,
            created_at=datetime.now(UTC),
            scenario_id=scenario.scenario_id,
            difficulty=scenario.difficulty,
            sales_channel=scenario.sales_channel,
            training_objective=scenario.training_objective,
            persona=scenario.persona,
            visible_context=scenario.visible_context,
            hidden_facts=scenario.hidden_facts,
            unresolved_objections=objection_ids,
            customer_goals=scenario.customer_goals,
            current_intent=scenario.buyer_intent,
            max_turns=max_turns or scenario.termination_conditions.max_turns,
        )

    def customer_prompt_context(self) -> dict[str, Any]:
        """Server-only context for the customer model; unrevealed facts stay private."""
        revealed_fact_values = {
            fact_key: self.hidden_facts[fact_key]
            for fact_key in self.spoken_fact_message_ids
            if fact_key in self.hidden_facts
        }
        return {
            "scenario_id": self.scenario_id,
            "difficulty": self.difficulty,
            "persona": self.persona,
            "conversation_stage": self.conversation_stage.value,
            "trust_level": self.trust_level,
            "interest_level": self.interest_level,
            "visible_context": self.visible_context,
            "customer_goals": self.customer_goals,
            "current_intent": self.current_intent,
            "advisor_off_topic": self.consecutive_off_topic_turns > 0,
            "revealed_facts": revealed_fact_values,
            "spoken_fact_message_ids": self.spoken_fact_message_ids,
            "spoken_concern_message_ids": self.spoken_concern_message_ids,
            "concern_prompt_counts": self.concern_prompt_counts,
            "active_objections": self.active_objections,
            "messages": [message.model_dump() for message in self.messages],
        }

    def advisor_visible_context(self) -> dict[str, Any]:
        """Frontend context for the trainee; it excludes private customer state."""
        return {
            "session_id": self.session_id,
            "scenario_id": self.scenario_id,
            "difficulty": self.difficulty,
            "sales_channel": self.sales_channel,
            "training_objective": self.training_objective,
            "conversation_stage": self.conversation_stage.value,
            "turn_count": self.turn_count,
            "max_turns": self.max_turns,
            "pending_customer_reply": self.pending_customer_reply,
            "visible_context": self.visible_context,
            "termination_status": self.termination_status.value,
            "termination_reason": self.termination_reason,
            "closing_outcome": self.closing_outcome,
            "messages": [message.model_dump() for message in self.messages],
        }
