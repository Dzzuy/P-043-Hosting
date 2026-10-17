"""Pure, deterministic role-play state transitions."""

from __future__ import annotations

import re

from .contracts import ScenarioContract
from .state import AdvisorFactualClaim, ConversationStage, RoleplayMessage, RoleplayState, TerminationStatus
from .turn_analyzer import TurnAnalysis, validated_benefit_links

OFF_TOPIC_LIMIT = 2
OFF_TOPIC_REASON = "Customer left after repeated off-topic advisor messages."


class StateTransitionError(ValueError):
    """Raised when an advisor turn cannot be applied to the supplied state."""


def _bounded_level(value: int) -> int:
    return min(5, max(1, value))


def _append_unique(target: list[str], values: list[str]) -> None:
    existing = set(target)
    for value in values:
        if value not in existing:
            target.append(value)
            existing.add(value)


def apply_turn_analysis(
    state: RoleplayState,
    scenario: ScenarioContract,
    advisor_message: str,
    analysis: TurnAnalysis,
) -> RoleplayState:
    """Return a new state; never let an LLM mutate business state directly."""
    if state.scenario_id != scenario.scenario_id:
        raise StateTransitionError("state and scenario identifiers do not match")
    if state.termination_status is not TerminationStatus.ACTIVE:
        raise StateTransitionError("cannot continue a terminated role-play session")
    if not advisor_message.strip():
        raise StateTransitionError("advisor_message must not be blank")

    updated = state.model_copy(deep=True)
    advisor_turn = RoleplayMessage(role="advisor", content=advisor_message.strip())
    updated.messages.append(advisor_turn)
    updated.factual_claims.extend(
        AdvisorFactualClaim(
            message_id=advisor_turn.message_id,
            text=claim.text,
            category=claim.category,
        )
        for claim in analysis.factual_claims
    )
    updated.turn_count += 1
    updated.consecutive_off_topic_turns = state.consecutive_off_topic_turns + 1 if analysis.off_topic else 0

    permitted_fact_ids = {
        rule.fact_key for rule in scenario.disclosure_rules if rule.trigger_intent in analysis.detected_intents
    }
    validated_discoveries = [fact_id for fact_id in analysis.discovered_fact_ids if fact_id in permitted_fact_ids]
    previous_discoveries = set(updated.advisor_discoveries)
    _append_unique(updated.advisor_discoveries, validated_discoveries)
    _append_unique(updated.revealed_facts, validated_discoveries)
    new_discovery_count = len(set(updated.advisor_discoveries) - previous_discoveries)

    if analysis.detected_intents:
        updated.current_intent = analysis.detected_intents[0]
    if analysis.current_topic:
        updated.current_topic = analysis.current_topic

    next_stage = updated.conversation_stage
    if next_stage is ConversationStage.OPENING:
        next_stage = ConversationStage.DISCOVERY
    if analysis.factual_claims:
        next_stage = ConversationStage.PRESENTATION

    updated.linked_benefits = validated_benefit_links(
        [*state.linked_benefits, *analysis.linked_benefits], scenario, state
    )
    known_policies = {item.policy_id for item in scenario.policy_expectations}
    _append_unique(updated.policy_mentions, [item for item in analysis.policy_mentions if item in known_policies])
    for objection in scenario.objections:
        if objection.objection_id in updated.unresolved_objections and any(
            re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", advisor_message, re.IGNORECASE)
            for keyword in objection.trigger_keywords
        ):
            _append_unique(updated.active_objections, [objection.objection_id])

    rule = scenario.upsell_rule
    eligible_upsell = False
    if rule:
        linked_ids = {link.benefit_id for link in updated.linked_benefits}
        safety_ids = {benefit.benefit_id for benefit in scenario.upsell_benefits if benefit.safety}
        eligible_upsell = len(linked_ids) >= rule.min_linked and len(linked_ids & safety_ids) >= rule.min_safety

    newly_resolved: list[str] = []
    addressed_objections = set(analysis.addressed_objection_ids)
    resolution_ids = list(analysis.resolved_objection_ids)
    if rule and eligible_upsell:
        resolution_ids.append(rule.objection_id)
        addressed_objections.add(rule.objection_id)
    objections_by_id = {item.objection_id: item for item in scenario.objections}
    for objection_id in dict.fromkeys(resolution_ids):
        objection = objections_by_id.get(objection_id)
        if objection is None or not set(objection.requires_revealed_facts).issubset(state.revealed_facts):
            continue
        if rule and objection_id == rule.objection_id and not eligible_upsell:
            continue
        if objection_id not in addressed_objections:
            continue
        if objection_id not in updated.active_objections:
            continue
        updated.active_objections.remove(objection_id)
        if objection_id in updated.unresolved_objections:
            updated.unresolved_objections.remove(objection_id)
        newly_resolved.append(objection_id)
    _append_unique(updated.resolved_objections, newly_resolved)

    if analysis.next_step_attempted and not updated.active_objections:
        next_stage = ConversationStage.CLOSING

    for objection in scenario.objections:
        if objection.trigger_stage != next_stage.value:
            continue
        if objection.objection_id not in updated.unresolved_objections:
            continue
        _append_unique(updated.active_objections, [objection.objection_id])

    if updated.active_objections:
        next_stage = ConversationStage.OBJECTION_HANDLING
    elif newly_resolved and next_stage is ConversationStage.OBJECTION_HANDLING:
        next_stage = ConversationStage.PRESENTATION

    trust_delta = min(new_discovery_count, 1) + min(len(newly_resolved), 1)
    interest_delta = min(len(newly_resolved), 1)
    if analysis.next_step_attempted and not analysis.premature_closing:
        interest_delta += 1
    if analysis.premature_closing:
        trust_delta -= 1
        interest_delta -= 1
    if analysis.unsafe_or_abusive:
        trust_delta -= 1
        interest_delta -= 1
    updated.trust_level = _bounded_level(updated.trust_level + trust_delta)
    updated.interest_level = _bounded_level(updated.interest_level + interest_delta)

    updated.conversation_stage = next_stage
    if analysis.unsafe_or_abusive:
        updated.termination_status = TerminationStatus.ADVISOR_MISCONDUCT
        updated.misconduct_reason = "semantic_abuse"
        updated.termination_reason = "Advisor misconduct: semantic_abuse."
    elif analysis.advisor_requested_finish:
        updated.termination_status = TerminationStatus.ADVISOR_ENDED
        updated.termination_reason = "Advisor explicitly ended the practice session."
    elif updated.consecutive_off_topic_turns >= OFF_TOPIC_LIMIT:
        updated.termination_status = TerminationStatus.DROPPED_OUT
        updated.termination_reason = OFF_TOPIC_REASON
    elif updated.turn_count >= updated.max_turns:
        updated.termination_status = TerminationStatus.MAX_TURNS
        updated.termination_reason = "Scenario turn limit reached."

    if updated.termination_status is not TerminationStatus.ACTIVE:
        updated.conversation_stage = ConversationStage.FINISHED

    return updated
