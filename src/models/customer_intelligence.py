"""Evidence-first customer analysis contracts; activities never select pipeline stage."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    message_id: str
    quote: str


class FactChange(StrictModel):
    field: str
    value: str | int | float | list[str] | None
    conditional: bool = False
    condition: str = ""
    evidence: list[Evidence] = Field(min_length=1)


class Topic(StrictModel):
    topic: str
    question: str = ""
    answer: str = ""
    status: Literal["open", "answered", "confirmed", "irrelevant"]
    evidence: list[Evidence] = Field(min_length=1)


class Event(StrictModel):
    event_type: Literal[
        "contacted",
        "needs_understood",
        "evaluating",
        "negotiating",
        "deposit_agreed",
        "quote_sent",
        "test_drive_completed",
        "deposit_received",
        "contract_signed",
        "delivered",
        "follow_up",
        "appointment",
        "closed_lost",
    ]
    action: str
    actor: Literal["sales", "customer", "both"]
    activity_kind: Literal[
        "callback", "test_drive", "meeting", "custom_quote", "finance_plan", "documents", "coordination", "other"
    ] = "other"
    # Activities must be accepted by sales; a request or invitation is not a commitment.
    accepted: bool = False
    deferred: bool = False
    conditional: bool = False
    occurred_at: str | None = None
    decision_changed: bool = False
    starts_at: str | None = None
    ends_at: str | None = None
    location: str = ""
    operation: Literal["create", "update", "cancel", "revoke"] = "create"
    target_task_id: str | None = None
    target_event_id: str | None = None
    evidence: list[Evidence] = Field(min_length=1)


class Extraction(StrictModel):
    facts: list[FactChange] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)


class Recap(StrictModel):
    text: str


class HistoryAnswer(StrictModel):
    answer: str
    evidence: list[Evidence] = Field(default_factory=list)


class DraftAnswer(StrictModel):
    text: str
    evidence: list[Evidence] = Field(default_factory=list)


class SuggestedTaskItem(StrictModel):
    title: str
    item_type: Literal["task", "appointment"] = "task"
    priority: Literal["low", "medium", "high"] = "medium"
    starts_at: str | None = None
    ends_at: str | None = None
    location: str = ""
    description: str = ""


class MessageTaskSuggestions(StrictModel):
    tasks: list[SuggestedTaskItem] = Field(default_factory=list)

