"""Shared structured-LLM adapters for the role-play runtime.

This module only adapts the team-owned LLM factory to Duy's role-play model
contracts. Application composition, persistence, and knowledge retrieval are
deliberately handled in later integration phases.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from src.agents.roleplay.contracts import ScenarioContract, policy_prompt_context
from src.agents.roleplay.customer_agent import CustomerAgent, CustomerModelOutput
from src.agents.roleplay.evaluator import EvaluationDraft, FactualFindingsDraft, RoleplayEvaluator
from src.agents.roleplay.graph import RoleplayGraph
from src.agents.roleplay.prompts import (
    TURN_ANALYZER_PROMPT_VERSION,
    TURN_ANALYZER_SYSTEM_PROMPT,
)
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import RoleplayState
from src.agents.roleplay.turn_analyzer import TurnAnalysis, TurnAnalyzer
from src.config import Settings, get_settings
from src.knowledge.retrieval_service import RetrievalService, get_retrieval_service
from src.knowledge.validity import today_in_vietnam
from src.services.llm import get_llm
from src.services.practice import PracticeService

from .practice_knowledge import RetrievalKnowledgeEvidenceProvider
from .practice_persistence import SQLCheckpointRepository
from .practice_policy import OfflinePolicyRetriever, ScenarioPolicyResolver

StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)
LLMFactory = Callable[[], BaseChatModel]


class StructuredModelInvocationError(ValueError):
    """The shared provider failed or returned invalid structured output."""


class _StructuredInvoker:
    def __init__(self, model_factory: LLMFactory = get_llm) -> None:
        self._model_factory = model_factory

    async def invoke(
        self,
        schema: type[StructuredOutput],
        *,
        system_prompt: str,
        context: dict[str, Any],
    ) -> StructuredOutput:
        try:
            model = self._model_factory()
            structured_model = model.with_structured_output(schema)
            raw_output = await structured_model.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=_serialize_context(context)),
                ]
            )
            return schema.model_validate(raw_output)
        except Exception as exc:
            raise StructuredModelInvocationError(f"structured model invocation failed for {schema.__name__}") from exc


class SharedLLMCustomerModel:
    """Adapt the shared LLM factory to ``CustomerTurnModel``."""

    def __init__(self, model_factory: LLMFactory = get_llm) -> None:
        self._invoker = _StructuredInvoker(model_factory)

    async def generate(
        self,
        *,
        system_prompt: str,
        context: dict[str, Any],
    ) -> CustomerModelOutput:
        return await self._invoker.invoke(
            CustomerModelOutput,
            system_prompt=system_prompt,
            context=context,
        )


class SharedLLMTurnAnalysisModel:
    """Adapt the shared LLM factory to ``TurnAnalysisModel``."""

    def __init__(self, model_factory: LLMFactory = get_llm) -> None:
        self._invoker = _StructuredInvoker(model_factory)

    async def analyze(
        self,
        advisor_message: str,
        scenario: ScenarioContract,
        state: RoleplayState,
    ) -> TurnAnalysis:
        return await self._invoker.invoke(
            TurnAnalysis,
            system_prompt=TURN_ANALYZER_SYSTEM_PROMPT,
            context=_turn_analysis_context(advisor_message, scenario, state),
        )


class SharedLLMEvaluationModel:
    """Adapt the shared LLM factory to ``EvaluationModel``."""

    def __init__(self, model_factory: LLMFactory = get_llm) -> None:
        self._invoker = _StructuredInvoker(model_factory)

    async def evaluate(
        self,
        *,
        system_prompt: str,
        context: dict[str, Any],
    ) -> EvaluationDraft:
        # One bounded retry covers transient provider/structured-output failures.
        # The frozen transcript and evidence are unchanged between attempts.
        try:
            return await self._invoker.invoke(
                EvaluationDraft,
                system_prompt=system_prompt,
                context=context,
            )
        except StructuredModelInvocationError:
            return await self._invoker.invoke(
                EvaluationDraft,
                system_prompt=system_prompt,
                context=context,
            )

    async def evaluate_factual_claims(
        self,
        *,
        system_prompt: str,
        context: dict[str, Any],
    ) -> FactualFindingsDraft:
        try:
            return await self._invoker.invoke(FactualFindingsDraft, system_prompt=system_prompt, context=context)
        except StructuredModelInvocationError:
            return await self._invoker.invoke(FactualFindingsDraft, system_prompt=system_prompt, context=context)


def build_practice_service(
    *,
    settings: Settings | None = None,
    model_factory: LLMFactory = get_llm,
    judge_model_factory: LLMFactory | None = None,
    retrieval_service: RetrievalService | None = None,
    checkpoint: SQLCheckpointRepository | None = None,
) -> PracticeService:
    """Compose the production Practice vertical slice from shared adapters."""

    resolved_settings = settings or get_settings()
    if (
        judge_model_factory is None
        and resolved_settings.practice_judge_provider == resolved_settings.llm_provider
        and resolved_settings.practice_judge_model == resolved_settings.model_name
    ):
        raise ValueError("Practice judge model must differ from the generator model")
    resolved_judge_factory = judge_model_factory or (
        lambda: get_llm(
            provider=resolved_settings.practice_judge_provider,
            model=resolved_settings.practice_judge_model,
            temperature=0,
        )
    )
    scenarios = ScenarioRepository()
    resolved_checkpoint = checkpoint or SQLCheckpointRepository(resolved_settings.database_url)
    resolved_retrieval = retrieval_service or get_retrieval_service()
    policy_resolver = ScenarioPolicyResolver(resolved_retrieval)
    # Startup checks local corpus coverage without embedding/provider calls.
    knowledge_dir = Path(__file__).resolve().parents[2] / "data" / "knowledge"
    startup_resolver = ScenarioPolicyResolver(
        OfflinePolicyRetriever(
            [
                knowledge_dir / "corpus.json",
                knowledge_dir / "faq.json",
            ]
        )
    )
    for summary in scenarios.list_public():
        for policy in startup_resolver.resolve(scenarios.get(summary.scenario_id), today_in_vietnam()):
            if policy.status == "not_applicable":
                logging.getLogger(__name__).warning(
                    "Unresolved scenario policy: %s/%s (%s)", summary.scenario_id, policy.policy_id, policy.level
                )
    graph = RoleplayGraph(
        scenarios,
        TurnAnalyzer(SharedLLMTurnAnalysisModel(model_factory)),
        CustomerAgent(SharedLLMCustomerModel(model_factory)),
        resolved_checkpoint,
    )
    return PracticeService(
        graph,
        scenarios,
        evaluator=RoleplayEvaluator(
            SharedLLMEvaluationModel(resolved_judge_factory),
            policy_resolver=policy_resolver,
            judge_model=resolved_settings.practice_judge_model,
            scenario_ids={item.scenario_id for item in scenarios.list_public()},
        ),
        knowledge_evidence=RetrievalKnowledgeEvidenceProvider(resolved_retrieval),
    )


def _turn_analysis_context(
    advisor_message: str,
    scenario: ScenarioContract,
    state: RoleplayState,
) -> dict[str, Any]:
    """Build an allowlisted context without private hidden-fact values."""

    return {
        "prompt_version": TURN_ANALYZER_PROMPT_VERSION,
        "advisor_message": advisor_message,
        "scenario": {
            "scenario_id": scenario.scenario_id,
            "difficulty": scenario.difficulty,
            "disclosure_rules": [rule.model_dump(mode="json") for rule in scenario.disclosure_rules],
            "objections": [objection.model_dump(mode="json") for objection in scenario.objections],
            "success_conditions": scenario.success_conditions,
            "acceptable_outcomes": [item.model_dump(mode="json") for item in scenario.acceptable_outcomes],
            "upsell_benefits": [item.model_dump(mode="json") for item in scenario.upsell_benefits],
            "policy_expectations": policy_prompt_context(scenario),
            "customer_goals": scenario.customer_goals,
            "termination_conditions": {
                **scenario.termination_conditions.model_dump(mode="json"),
                "max_turns": state.max_turns,
            },
        },
        "state": {
            "conversation_stage": state.conversation_stage.value,
            "revealed_fact_ids": list(state.revealed_facts),
            "allowed_need_fact_keys": list(dict.fromkeys([*state.revealed_facts, "visible_goals"])),
            "active_objection_ids": list(state.active_objections),
            "resolved_objection_ids": list(state.resolved_objections),
            "unresolved_objection_ids": list(state.unresolved_objections),
            "current_topic": state.current_topic,
            "concern_prompt_counts": dict(state.concern_prompt_counts),
            "recent_messages": [message.model_dump(mode="json") for message in state.messages[-6:]],
        },
    }


def _serialize_context(context: dict[str, Any]) -> str:
    return "CONTEXT_JSON:\n" + json.dumps(
        context,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
