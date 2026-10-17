"""Planning only for complex queries and corrective search."""

import json
import re

from src.agents.copilot import prompts
from src.agents.copilot.errors import CopilotModelOutputError
from src.agents.copilot.model_io import _invoke_json
from src.agents.copilot.nodes._shared import _requirements, observed
from src.agents.copilot.state import SearchPlan
from src.config import get_settings
from src.knowledge.index_readiness import load_snapshot


def _signature(search):
    return json.dumps(search.model_dump(exclude={"requirement_ids"}), sort_keys=True, ensure_ascii=False)


def _catalog(state):
    return (state.get("snapshot") or load_snapshot()).catalog()


def available_searches(state):
    settings = get_settings()
    if state.get("retrieval_rounds", 0) >= settings.copilot_max_retrieval_rounds:
        return 0
    remaining = max(0, settings.copilot_max_search_calls - state.get("tool_calls", 0))
    return min(settings.copilot_max_queries_per_plan, remaining)


def validate_plan(plan, state):
    if len(plan.searches) > available_searches(state):
        raise ValueError("search plan exceeds remaining budget")
    catalog = _catalog(state)
    text = " ".join(
        [
            state["query"],
            state.get("customer_context", ""),
            state.get("memory_summary") or "",
            *[m.get("content", "") for m in state.get("history", [])],
        ]
    )
    observed_models = {"VF " + v for v in re.findall(r"\bVF[\s-]*(\d+)\b", text, re.I)}
    signatures = set(state.get("search_signatures", []))
    req_map = _requirements(state)
    all_req_ids = set(req_map.keys())

    # Determine target factual requirements for this planning turn
    if state.get("recovery_requirement_ids"):
        target_factual_ids = {
            rid for rid in state["recovery_requirement_ids"] if req_map.get(rid) and req_map[rid].kind == "fact"
        }
    else:
        target_factual_ids = {rid for rid, r in req_map.items() if r.kind == "fact"}

    union_search_req_ids: set[str] = set()
    for search in plan.searches:
        search_reqs = set(search.requirement_ids)
        if not search_reqs <= all_req_ids:
            raise ValueError("unknown requirement in search plan")
        if state.get("recovery_requirement_ids") and not search_reqs <= set(state["recovery_requirement_ids"]):
            raise ValueError("corrective query outside missing requirements")
        union_search_req_ids |= search_reqs
        for key in ("product_model", "document_type", "policy_type"):
            value = getattr(search, key)
            if value and value not in catalog[key]:
                raise ValueError("filter absent from corpus")
        if (
            search.product_model
            and search.product_model.upper() != "ALL"
            and (
                search.product_model not in state["analysis"].product_models
                or search.product_model not in observed_models
            )
        ):
            raise ValueError("model without input entity")
        signature = _signature(search)
        if signature in signatures:
            raise ValueError("repeated query")
        signatures.add(signature)

    if target_factual_ids and not (target_factual_ids <= union_search_req_ids):
        raise ValueError("search plan does not cover all target factual requirements")


@observed
async def plan_queries(state):
    limit = available_searches(state)
    if not limit:
        return {
            "route": "finalize_response" if state.get("verified_snapshot") else "fallback_response",
            "fallback_reason": "budget_exhausted",
        }
    try:
        plan, _ = await _invoke_json(
            state,
            prompts.PLAN_PROMPT,
            {
                "query": state["query"],
                "analysis": state["analysis"].model_dump(),
                "catalog": _catalog(state),
                "customer_context": state.get("customer_context", ""),
                "memory_summary": state.get("memory_summary") or "",
                "lookup_date": state["resolved_date"],
                "search_signatures": state.get("search_signatures", []),
                "feedback": state.get("feedback", ""),
                "corrective": state.get("corrective_retrieval_count", 0) > 0,
                "max_queries": limit,
                "remaining_search_calls": max(0, get_settings().copilot_max_search_calls - state.get("tool_calls", 0)),
                "recovery_requirements": [
                    r.model_dump()
                    for r in state["requirements"]
                    if r.requirement_id in state.get("recovery_requirement_ids", [])
                ],
            },
            SearchPlan,
            node="plan_queries",
            validator=lambda plan: validate_plan(plan, state),
        )
    except CopilotModelOutputError:
        return {
            "route": "finalize_response" if state.get("verified_snapshot") else "fallback_response",
            "fallback_reason": "verification_failed",
        }
    return {"search_plan": plan, "retrieval_mode": "search", "route": "retrieve_documents"}
