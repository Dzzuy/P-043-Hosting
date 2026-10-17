"""Shared request and response contracts for Copilot entry points."""

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, computed_field, field_validator

from src.agents.copilot.state import CopilotResponse

QueryText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=2, max_length=4000)]


class SalesKnowledgeQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: QueryText


class CopilotQueryRequest(BaseModel):
    query: QueryText
    target_date: date | None = None
    session_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")] | None = None
    customer_context: Annotated[str, StringConstraints(strip_whitespace=True, max_length=6000)] | None = None
    domain: Literal["all", "specs", "policy", "charging", "competitor"] = "all"

    @field_validator("target_date", mode="before")
    @classmethod
    def validate_date(cls, value: Any) -> date | None:
        if value is None or type(value) is date:
            return value
        if not isinstance(value, str):
            raise ValueError("target_date must be YYYY-MM-DD")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("target_date must be YYYY-MM-DD")
        return parsed


class CopilotQueryResponse(CopilotResponse):
    session_id: str | None = None

    @computed_field
    @property
    def is_abstain(self) -> bool:
        return self.status == "abstained"

    @computed_field
    @property
    def is_clarification(self) -> bool:
        return self.status == "needs_clarification"

