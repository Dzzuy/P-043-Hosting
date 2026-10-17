"""LangGraph orchestration for a bounded multi-turn practice session."""

from __future__ import annotations

import logging
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from src.models.evaluation import SessionEvaluationResult

from .contracts import CheckpointContract, ScenarioContract
from .customer_agent import CustomerAgent
from .guardrails import check_advisor_message
from .scenario_loader import ScenarioNotFoundError, ScenarioRepository
from .state import ConversationStage, EvaluationStatus, RoleplayMessage, RoleplayState, TerminationStatus
from .state_reducer import OFF_TOPIC_REASON, apply_turn_analysis
from .turn_analyzer import TurnAnalysis, TurnAnalyzer

logger = logging.getLogger(__name__)


class RoleplayRuntimeState(TypedDict, total=False):
    """Ephemeral graph state; durable business state lives in RoleplayState."""

    scenario: ScenarioContract
    roleplay_state: RoleplayState
    advisor_message: str
    analysis: TurnAnalysis
    customer_reply: str
    misconduct_category: str


class RoleplayGraphError(ValueError):
    """Raised when a session cannot safely enter the role-play graph."""


class RoleplayScenarioNotFoundError(RoleplayGraphError):
    """Raised when a requested or restored scenario is unavailable."""


class RoleplaySessionNotFoundError(RoleplayGraphError):
    """Raised when a session checkpoint does not exist."""


class RoleplaySessionConflictError(RoleplayGraphError):
    """A stable conflict code independent of internal diagnostic wording."""

    def __init__(
        self,
        message: str,
        *,
        code: Literal["session_finished", "session_busy", "validation_error"] = "validation_error",
    ) -> None:
        super().__init__(message)
        self.code = code


def build_roleplay_turn_graph(
    analyzer: TurnAnalyzer,
    customer_agent: CustomerAgent,
    checkpoint: CheckpointContract,
):
    """Build one advisor-turn graph with persistence before provider generation."""

    async def analyze_advisor_turn(state: RoleplayRuntimeState) -> RoleplayRuntimeState:
        verdict = check_advisor_message(state["advisor_message"])
        if verdict.level == "end_session":
            return {
                "analysis": TurnAnalysis(unsafe_or_abusive=True),
                "misconduct_category": verdict.category or "code_abuse",
            }
        if verdict.level == "warn":
            logger.warning(
                "Advisor guardrail warning: session_id=%s category=%s",
                state["roleplay_state"].session_id,
                verdict.category,
            )
        analysis = await analyzer.analyze(
            state["advisor_message"],
            state["scenario"],
            state["roleplay_state"],
        )
        return {"analysis": analysis}

    async def update_customer_state(state: RoleplayRuntimeState) -> RoleplayRuntimeState:
        updated = apply_turn_analysis(
            state["roleplay_state"],
            state["scenario"],
            state["advisor_message"],
            state["analysis"],
        )
        updated.pending_next_step_attempted = (
            state["analysis"].next_step_attempted if updated.termination_status is TerminationStatus.ACTIVE else False
        )
        if updated.termination_status is TerminationStatus.ADVISOR_MISCONDUCT:
            category = state.get("misconduct_category", "semantic_abuse")
            updated.misconduct_reason = category
            updated.termination_reason = f"Advisor misconduct: {category}."
            address = customer_agent.persona_address(state["scenario"])
            reply = (
                f"{address} sẽ báo cáo em lên quản lý. {address} không có nhu cầu mua xe ở đây nữa."
                if category != "semantic_abuse"
                else f"{address} nghĩ mình nên dừng cuộc trao đổi ở đây. Chào em."
            )
            updated.messages.append(RoleplayMessage(role="customer", content=reply))
            return {"roleplay_state": updated, "customer_reply": reply}
        if (
            updated.termination_status is TerminationStatus.DROPPED_OUT
            and updated.termination_reason == OFF_TOPIC_REASON
        ):
            address = customer_agent.persona_address(state["scenario"])
            reply = f"{address} thấy em không tập trung tư vấn nên {address.lower()} xin phép dừng ở đây. Chào em."
            updated.messages.append(RoleplayMessage(role="customer", content=reply))
            return {"roleplay_state": updated, "customer_reply": reply}
        return {"roleplay_state": updated}

    async def route_pending_turn(state: RoleplayRuntimeState) -> RoleplayRuntimeState:
        return {}

    async def route_after_pending_check(state: RoleplayRuntimeState) -> str:
        return "customer_turn" if state["roleplay_state"].pending_customer_reply else "analyze_advisor_turn"

    async def persist_advisor_turn(state: RoleplayRuntimeState) -> RoleplayRuntimeState:
        await _save_state(checkpoint, state["roleplay_state"])
        return {}

    async def route_after_advisor_turn(state: RoleplayRuntimeState) -> str:
        if state["roleplay_state"].termination_status is not TerminationStatus.ACTIVE:
            return END
        return "customer_turn"

    async def customer_turn(state: RoleplayRuntimeState) -> RoleplayRuntimeState:
        prior = state["roleplay_state"]
        pending = customer_agent.pending_disclosures(state["scenario"], prior)
        focus_id = customer_agent.focus_objection_id(prior) if not pending else None
        turn = await customer_agent.generate_turn(
            state["scenario"],
            prior,
            mode="response",
            consider_next_step=prior.pending_next_step_attempted,
        )
        message = turn.message
        updated = prior.model_copy(deep=True)
        updated.messages.append(message)
        updated.pending_next_step_attempted = False
        for rule in pending:
            if rule.fact_key in turn.disclosed_fact_keys or rule.revealed_statement in message.content:
                updated.spoken_fact_message_ids[rule.fact_key] = message.message_id
        if turn.accepted_next_step and prior.pending_next_step_attempted:
            accepted_id = focus_id or next(iter(updated.active_objections), None)
            updated.closing_outcome = customer_agent.validated_outcome_id(
                turn.accepted_outcome_id, state["scenario"], prior
            )
            rule = state["scenario"].upsell_rule
            outcome = next(
                (item for item in state["scenario"].acceptable_outcomes if item.outcome_id == updated.closing_outcome),
                None,
            )
            if rule and outcome and rule.objection_id not in outcome.requires_resolved_objections:
                # Closing the base product declines the upsell; no resolution credit.
                # closing_outcome preserves the reason, and removing unresolved
                # prevents keyword/stage activation on later turns.
                updated.active_objections = [key for key in updated.active_objections if key != rule.objection_id]
                updated.unresolved_objections = [
                    key for key in updated.unresolved_objections if key != rule.objection_id
                ]
            accepted_objection = next(
                (item for item in state["scenario"].objections if item.objection_id == accepted_id), None
            )
            facts_known = accepted_objection is not None and set(accepted_objection.requires_revealed_facts).issubset(
                prior.revealed_facts
            )
            if accepted_id is not None and facts_known and (rule is None or accepted_id != rule.objection_id):
                objection_id = accepted_id
                updated.active_objections.remove(objection_id)
                if objection_id in updated.unresolved_objections:
                    updated.unresolved_objections.remove(objection_id)
                if objection_id not in updated.resolved_objections:
                    updated.resolved_objections.append(objection_id)
        if turn.raised_objection_id and turn.raised_objection_id in updated.unresolved_objections:
            if turn.raised_objection_id not in updated.active_objections:
                updated.active_objections.append(turn.raised_objection_id)
                updated.conversation_stage = ConversationStage.OBJECTION_HANDLING
            if turn.raised_objection_id not in updated.spoken_concern_message_ids:
                updated.spoken_concern_message_ids[turn.raised_objection_id] = message.message_id
            elif focus_id == turn.raised_objection_id:
                updated.concern_prompt_counts[focus_id] = updated.concern_prompt_counts.get(focus_id, 0) + 1
        elif focus_id and turn.raised_objection_id is None and not turn.accepted_next_step:
            # Legacy provider fixtures omit the structured concern marker.
            updated.concern_prompt_counts[focus_id] = updated.concern_prompt_counts.get(focus_id, 0) + 1
        elif prior.active_objections and not pending and not turn.accepted_next_step:
            updated.termination_status = TerminationStatus.DROPPED_OUT
            updated.termination_reason = "Customer deferred unresolved concerns after two prompts each."
            updated.conversation_stage = ConversationStage.FINISHED
        return {
            "roleplay_state": updated,
            "customer_reply": message.content,
        }

    async def persist_customer_turn(state: RoleplayRuntimeState) -> RoleplayRuntimeState:
        await _save_state(checkpoint, state["roleplay_state"])
        return {}

    graph = StateGraph(RoleplayRuntimeState)
    graph.add_node("route_pending_turn", route_pending_turn)
    graph.add_node("analyze_advisor_turn", analyze_advisor_turn)
    graph.add_node("update_customer_state", update_customer_state)
    graph.add_node("persist_advisor_turn", persist_advisor_turn)
    graph.add_node("customer_turn", customer_turn)
    graph.add_node("persist_customer_turn", persist_customer_turn)
    graph.set_entry_point("route_pending_turn")
    graph.add_conditional_edges("route_pending_turn", route_after_pending_check)
    graph.add_edge("analyze_advisor_turn", "update_customer_state")
    graph.add_edge("update_customer_state", "persist_advisor_turn")
    graph.add_conditional_edges("persist_advisor_turn", route_after_advisor_turn)
    graph.add_edge("customer_turn", "persist_customer_turn")
    graph.add_edge("persist_customer_turn", END)
    return graph.compile()


async def _save_state(checkpoint: CheckpointContract, state: RoleplayState) -> None:
    await checkpoint.save(state.session_id, state.model_dump(mode="json"))


class RoleplayGraph:
    """Stable start/continue boundary for the practice service and API."""

    def __init__(
        self,
        repository: ScenarioRepository,
        analyzer: TurnAnalyzer,
        customer_agent: CustomerAgent,
        checkpoint: CheckpointContract,
    ) -> None:
        self._repository = repository
        self._customer_agent = customer_agent
        self._checkpoint = checkpoint
        self._turn_graph = build_roleplay_turn_graph(
            analyzer,
            customer_agent,
            checkpoint,
        )

    async def start(self, session_id: str, scenario_id: str, max_turns: int | None = None) -> dict:
        if not session_id.strip():
            raise RoleplayGraphError("session_id must not be blank")
        try:
            scenario = self._repository.get(scenario_id)
        except ScenarioNotFoundError as exc:
            raise RoleplayScenarioNotFoundError(str(exc)) from exc

        existing = await self._checkpoint.load(session_id)
        if existing is not None:
            state = self._validate_checkpoint(existing, session_id)
            if state.scenario_id != scenario_id:
                raise RoleplaySessionConflictError(
                    "session_id already belongs to a different scenario", code="validation_error"
                )
            if max_turns is not None and state.max_turns != max_turns:
                raise RoleplaySessionConflictError(
                    "session_id already has a different turn limit", code="validation_error"
                )
            return state.advisor_visible_context()

        state = RoleplayState.from_scenario(session_id, scenario, max_turns=max_turns)
        await _save_state(self._checkpoint, state)
        return state.advisor_visible_context()

    async def continue_session(
        self,
        session_id: str,
        advisor_message: str,
    ) -> dict:
        checkpoint_data = await self._checkpoint.load(session_id)
        if checkpoint_data is None:
            raise RoleplaySessionNotFoundError(f"unknown session_id: {session_id}")
        state = self._validate_checkpoint(checkpoint_data, session_id)
        if state.termination_status is not TerminationStatus.ACTIVE:
            raise RoleplaySessionConflictError("cannot continue a finished practice session", code="session_finished")
        if state.pending_customer_reply:
            raise RoleplaySessionConflictError(
                "customer reply is pending; retry it before sending another message", code="session_busy"
            )
        return await self._run_turn(state, advisor_message)

    async def retry_customer_reply(self, session_id: str) -> dict:
        state = await self.get_session_state(session_id)
        if not state.pending_customer_reply:
            raise RoleplaySessionConflictError("no customer reply is pending", code="validation_error")
        return await self._run_turn(state, state.messages[-1].content)

    async def _run_turn(self, state: RoleplayState, advisor_message: str) -> dict:
        try:
            scenario = self._repository.get(state.scenario_id)
        except ScenarioNotFoundError as exc:
            raise RoleplayScenarioNotFoundError(
                f"session references an unavailable scenario: {state.scenario_id}"
            ) from exc

        result = await self._turn_graph.ainvoke(
            {
                "scenario": scenario,
                "roleplay_state": state,
                "advisor_message": advisor_message,
            }
        )
        updated = result.get("roleplay_state")
        if not isinstance(updated, RoleplayState):
            raise RoleplayGraphError("turn graph returned invalid role-play state")
        return updated.advisor_visible_context()

    async def get_session_state(self, session_id: str) -> RoleplayState:
        checkpoint_data = await self._checkpoint.load(session_id)
        if checkpoint_data is None:
            raise RoleplaySessionNotFoundError(f"unknown session_id: {session_id}")
        return self._validate_checkpoint(checkpoint_data, session_id)

    async def finish_session(self, session_id: str) -> RoleplayState:
        state = await self.get_session_state(session_id)
        if state.pending_customer_reply:
            raise RoleplaySessionConflictError(
                "customer reply is pending; retry it before finishing", code="session_busy"
            )
        if state.termination_status is TerminationStatus.ACTIVE:
            state.termination_status = TerminationStatus.ADVISOR_ENDED
            state.termination_reason = "Advisor ended the practice session."
            state.conversation_stage = ConversationStage.FINISHED
        if state.evaluation_status in {EvaluationStatus.NOT_STARTED, EvaluationStatus.FAILED}:
            state.evaluation_status = EvaluationStatus.PENDING
            await _save_state(self._checkpoint, state)
        return state

    async def save_evaluation_result(self, session_id: str, result: SessionEvaluationResult) -> RoleplayState:
        state = await self.get_session_state(session_id)
        if state.termination_status is TerminationStatus.ACTIVE:
            raise RoleplaySessionConflictError("cannot evaluate an active practice session", code="validation_error")
        if result.session_id != session_id or result.scenario_id != state.scenario_id:
            raise RoleplaySessionConflictError("evaluation does not match practice session", code="validation_error")
        if state.evaluation_result is not None:
            if state.evaluation_result != result:
                raise RoleplaySessionConflictError(
                    "practice session already has an evaluation", code="validation_error"
                )
            return state
        state.evaluation_result = result
        state.evaluation_status = EvaluationStatus.COMPLETE
        await _save_state(self._checkpoint, state)
        return state

    async def mark_evaluation_failed(self, session_id: str) -> None:
        state = await self.get_session_state(session_id)
        if state.evaluation_result is None and state.termination_status is not TerminationStatus.ACTIVE:
            state.evaluation_status = EvaluationStatus.FAILED
            await _save_state(self._checkpoint, state)

    @staticmethod
    def _validate_checkpoint(data: dict, session_id: str) -> RoleplayState:
        try:
            state = RoleplayState.model_validate(data)
        except ValidationError as exc:
            raise RoleplayGraphError(f"invalid checkpoint for session_id {session_id}: {exc}") from exc
        if state.session_id != session_id:
            raise RoleplayGraphError("checkpoint session_id does not match lookup key")
        return state
