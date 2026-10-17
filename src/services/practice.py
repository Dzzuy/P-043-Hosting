"""Application service for advisor-facing role-play operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from src.agents.roleplay.contracts import RoleplayGraphContract, ScenarioContract
from src.agents.roleplay.evaluator import EvaluationError, KnowledgeEvidence, RoleplayEvaluator
from src.agents.roleplay.scenario_loader import ScenarioRepository, ScenarioSummary
from src.agents.roleplay.state import (
    ConversationStage,
    EvaluationStatus,
    RoleplayMessage,
    RoleplayState,
    TerminationStatus,
)
from src.models.evaluation import SessionEvaluationResult

logger = logging.getLogger(__name__)


def _evaluation_error_code(exc: Exception) -> str:
    if not isinstance(exc, EvaluationError):
        return "not_validation_error"
    message = str(exc)
    if message.startswith("invalid evaluation output"):
        return "invalid_output_schema"
    if message.startswith("evaluation omitted recorded factual claims"):
        return "missing_factual_findings"
    if message.startswith("evidence quote is not exact"):
        return "transcript_quote_mismatch"
    if message.startswith("evidence references unknown message_id"):
        return "unknown_transcript_message"
    if message.startswith("factual source quote is not exact"):
        return "source_quote_mismatch"
    if message.startswith("factual finding references unknown source_id"):
        return "unknown_factual_source"
    if message.startswith("factual finding references"):
        return "invalid_factual_reference"
    if message.startswith("factual claim is not exact"):
        return "factual_claim_quote_mismatch"
    if message.startswith("factual repair did not cover exactly"):
        return "factual_repair_mismatch"
    if message.startswith("factual findings must not contain duplicate"):
        return "duplicate_factual_findings"
    if message.startswith("factual source version mismatch"):
        return "factual_source_version_mismatch"
    if message.startswith("supported or contradicted findings require"):
        return "missing_factual_source"
    if message.startswith("scores 2-3 require") or message.startswith("score 3 requires"):
        return "score_evidence_mismatch"
    return "other_validation_error"


class PracticeSessionView(BaseModel):
    """Public session shape consumed by the Practice Room frontend."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    scenario_id: str
    difficulty: str
    sales_channel: str | None = None
    training_objective: str | None = None
    conversation_stage: ConversationStage
    turn_count: int
    max_turns: int = 10
    pending_customer_reply: bool = False
    visible_context: str
    termination_status: TerminationStatus
    termination_reason: str | None = None
    closing_outcome: str | None = None
    messages: list[RoleplayMessage]


class PracticeResultView(BaseModel):
    """Advisor-facing status and draft result for a finished attempt."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    evaluation_status: EvaluationStatus
    result: SessionEvaluationResult | None = None


class KnowledgeEvidenceProvider(Protocol):
    async def for_session(self, scenario: ScenarioContract, state: RoleplayState) -> list[KnowledgeEvidence]: ...


class PracticeEvaluationUnavailableError(RuntimeError):
    """Evaluation failed; the frozen transcript remains available for retry."""


class PracticeService:
    """Keep HTTP handlers independent from graph and persistence details."""

    def __init__(
        self,
        graph: RoleplayGraphContract,
        scenarios: ScenarioRepository,
        *,
        session_id_factory: Callable[[], str] | None = None,
        evaluator: RoleplayEvaluator | None = None,
        knowledge_evidence: KnowledgeEvidenceProvider | None = None,
    ) -> None:
        self._graph = graph
        self._scenarios = scenarios
        self._session_id_factory = session_id_factory or (lambda: str(uuid4()))
        self._evaluator = evaluator
        self._knowledge_evidence = knowledge_evidence
        self._session_locks: dict[str, asyncio.Lock] = {}

    def list_scenarios(self) -> list[ScenarioSummary]:
        return self._scenarios.list_public()

    async def start_session(self, scenario_id: str, max_turns: int | None = None) -> PracticeSessionView:
        session_id = self._session_id_factory()
        result = (
            await self._graph.start(session_id, scenario_id, max_turns=max_turns)
            if max_turns is not None
            else await self._graph.start(session_id, scenario_id)
        )
        return PracticeSessionView.model_validate(result)

    async def send_message(
        self,
        session_id: str,
        advisor_message: str,
    ) -> PracticeSessionView:
        async with self._lock_for(session_id):
            result = await self._graph.continue_session(session_id, advisor_message)
            return PracticeSessionView.model_validate(result)

    async def retry_customer_reply(self, session_id: str) -> PracticeSessionView:
        async with self._lock_for(session_id):
            result = await self._graph.retry_customer_reply(session_id)
            return PracticeSessionView.model_validate(result)

    async def finish_session(
        self,
        session_id: str,
        *,
        started_at: datetime | None = None,
        on_saved: Callable[[], Awaitable[None]] | None = None,
    ) -> PracticeResultView:
        async with self._lock_for(session_id):
            # finish_session commits the frozen transcript before evaluation starts.
            state = await self._graph.finish_session(session_id)
            if state.created_at is None and started_at is not None:
                state = state.model_copy(update={"created_at": started_at})
            if on_saved is not None:
                await on_saved()
            if state.evaluation_result is not None:
                return self._result_view(state)

            stage = "configuration"
            evidence: list[KnowledgeEvidence] = []
            try:
                if self._evaluator is None or self._knowledge_evidence is None:
                    raise PracticeEvaluationUnavailableError("evaluation dependencies are not configured")
                scenario = self._scenarios.get(state.scenario_id)
                stage = "retrieval"
                evidence = await self._knowledge_evidence.for_session(scenario, state)
                stage = "judge_or_validation"
                result = await self._evaluator.evaluate(scenario, state, evidence)
            except Exception as exc:
                logger.warning(
                    "practice_evaluation_failed session_id=%s stage=%s error_type=%s cause_type=%s root_cause_type=%s validation_code=%s claim_count=%d evidence_count=%d",
                    session_id,
                    stage,
                    type(exc).__name__,
                    type(exc.__cause__).__name__ if exc.__cause__ else "none",
                    type(exc.__cause__.__cause__).__name__ if exc.__cause__ and exc.__cause__.__cause__ else "none",
                    _evaluation_error_code(exc),
                    len(state.factual_claims),
                    len(evidence),
                )
                await self._graph.mark_evaluation_failed(session_id)
                raise PracticeEvaluationUnavailableError(
                    "Evaluation is unavailable; the finished attempt can be retried."
                ) from exc

            saved = await self._graph.save_evaluation_result(session_id, result)
            return self._result_view(saved)

    async def get_result(self, session_id: str) -> PracticeResultView:
        state = await self._graph.get_session_state(session_id)
        return self._result_view(state)

    async def get_session(self, session_id: str) -> PracticeSessionView:
        state = await self._graph.get_session_state(session_id)
        return PracticeSessionView.model_validate(state.advisor_visible_context())

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        return self._session_locks.setdefault(session_id, asyncio.Lock())

    @staticmethod
    def _result_view(state: RoleplayState) -> PracticeResultView:
        return PracticeResultView(
            session_id=state.session_id,
            evaluation_status=state.evaluation_status,
            result=state.evaluation_result,
        )
