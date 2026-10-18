"""Data models and schemas for the AI Sales Copilot module.

Customer facts, versioned consultation memory, requested drafts and activities.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SenderRole(StrEnum):
    CUSTOMER = "customer"
    SALES = "sales"
    SYSTEM = "system"


class LeadStage(StrEnum):
    NEW = "new"
    DISCOVERY = "discovery"
    QUALIFIED = "qualified"
    CONSIDERING = "considering"
    NEGOTIATING = "negotiating"
    DEPOSIT_PROCESS = "deposit_process"
    WON = "won"
    LOST = "lost"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# -------------------------------------------------------------
# Core Customer & Conversation Schemas
# -------------------------------------------------------------

class CustomerBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(..., min_length=1, max_length=120)
    phone: str | None = None
    email: str | None = None
    location: str | None = None
    advisor_id: str = Field(..., max_length=120)


class CustomerCreate(CustomerBase):
    pass


class CustomerResponse(CustomerBase):
    id: str
    created_at: datetime
    updated_at: datetime | None = None
    lead_stage: LeadStage | None = LeadStage.NEW
    pending_tasks_count: int = 0
    interested_models: list[str] = Field(default_factory=list)


class ChatMessageBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    sender_role: SenderRole
    content: str = Field(..., min_length=1)
    sent_at: datetime | None = None


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessageResponse(ChatMessageBase):
    id: str
    conversation_id: str
    seq: int
    sent_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    customer_id: str
    customer_name: str
    customer_location: str | None = None
    last_analyzed_at: datetime | None = None
    analysis_version: int = 0
    messages: list[ChatMessageResponse] = Field(default_factory=list)
    message_total: int = 0
    last_message_seq: int = 0
    next_before_seq: int | None = None
    profile: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    lead_status: dict[str, Any] = Field(default_factory=dict)


# -------------------------------------------------------------
# F01: Customer Understanding (Facts & Profile)
# -------------------------------------------------------------

class CustomerFact(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str
    value: Any
    verification_status: Literal["reported", "inferred", "confirmed", "conflicted"] = "reported"
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source_message_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class CustomerProfileSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")
    interested_models: list[str] = Field(default_factory=list)
    competitor_models: list[str] = Field(default_factory=list)
    budget_vnd: int | None = None
    budget_notes: str | None = None
    down_payment_vnd: int | None = None
    payment_method: str | None = None  # cash, installment, mixed
    max_monthly_payment_vnd: int | None = None
    loan_term_years: int | None = None
    usage_purpose: str | None = None
    passenger_count: int | None = None
    daily_distance_km: str | None = None
    living_area: str | None = None
    charging_condition: str | None = None  # apartment, home_ground, public_charger
    purchase_timeline: str | None = None
    objections_and_concerns: list[str] = Field(default_factory=list)
    buying_signals: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    facts: list[CustomerFact] = Field(default_factory=list)


# -------------------------------------------------------------
# F02: Conversation Memory
# -------------------------------------------------------------

class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    description: str
    occurred_at: str | None = None
    source_message_id: str | None = None
    event_type: str = "general"  # consulted, resolved (customer confirmation), inquiry, promise, appointment, ...


class ConversationMemory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    quick_summary: str = ""  # 2-4 sentences for immediate context restore
    detailed_summary: str = ""
    timeline: list[TimelineEvent] = Field(default_factory=list)
    pending_items: list[str] = Field(default_factory=list)
    key_promises: list[str] = Field(default_factory=list)
    version: int = 1


# -------------------------------------------------------------
# F05: Smart Follow-up
# -------------------------------------------------------------

class FollowupTask(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    customer_id: str | None = None
    conversation_id: str | None = None
    owner_sales_id: str
    task_type: str
    title: str
    description: str
    due_at: datetime | None = None
    due_window: str | None = None  # e.g., "Hôm nay", "Sáng Chủ nhật", "Tháng sau"
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    item_type: Literal["task", "appointment"] = "task"
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    source_message_ids: list[str] = Field(default_factory=list)
    dedupe_key: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


# -------------------------------------------------------------
# F06: Lead Classification & Scoring
# -------------------------------------------------------------

class LeadStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")
    customer_id: str
    stage: LeadStage = LeadStage.DISCOVERY
    stage_name: str = "Tìm hiểu nhu cầu"
    rationale: str = ""


# -------------------------------------------------------------
# F03 & F04: Next Best Action & Message Drafting
# -------------------------------------------------------------

class MessageDraftResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    conversation_id: str
    draft_id: str
    text: str
    tone: str = "friendly_professional"
    context_trigger: str = ""  # which question or context caused this draft
    sources: list[str] = Field(default_factory=list)
    status: Literal["generated", "copied", "inserted", "sent", "discarded"] = "generated"
    based_on_message_seq: int | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# -------------------------------------------------------------
# Sales Feature Preferences
# -------------------------------------------------------------

class SalesPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")
    advisor_id: str
    draft_enabled: bool = False
    notifications_enabled: bool = True
