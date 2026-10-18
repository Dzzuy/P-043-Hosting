"""One call per invocation and one request-wide transient retry.

The checker node owns its explicit, bounded review-contract retry.
"""

import asyncio
import json
import time

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from src.agents.copilot.errors import CopilotModelOutputError
from src.agents.copilot.nodes._shared import _runtime
from src.agents.copilot.runtime import BudgetExhaustedError, CopilotDependencyError
from src.config import get_settings
from src.observability import annotate, span
from src.services.llm import get_llm
from src.services.provider_response import ProviderResponseError


def _model_usage(response):
    finish = getattr(response, "response_metadata", {}).get("finish_reason")
    if finish == "error":
        return {"input_tokens": None, "output_tokens": None, "reasoning_tokens": None, "finish_reason": finish}
    usage = (
        getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", {}).get("token_usage") or {}
    )
    reasoning = usage.get("output_token_details", {}).get("reasoning")
    if reasoning is None:
        reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens")
    return {
        "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
        "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
        "reasoning_tokens": reasoning,
        "finish_reason": getattr(response, "response_metadata", {}).get("finish_reason"),
    }


def _limits(node):
    settings = get_settings()
    role = {
        "analyze_and_route": "analysis",
        "plan_queries": "plan",
        "generate_answer": "generate",
        "check_grounding": "check",
    }[node]
    return getattr(settings, f"copilot_{role}_timeout_seconds"), getattr(settings, f"copilot_{role}_max_tokens")


def _request_schema(schema, payload):
    """Enforce request-specific budgets in native JSON Schema, not only prompts."""
    wire = schema.model_json_schema()
    for field, limit_key in (("searches", "max_queries"), ("requirements", "max_requirements")):
        if field in wire.get("properties", {}) and isinstance(payload.get(limit_key), int):
            prop = wire["properties"][field]
            prop["maxItems"] = min(prop["maxItems"], payload[limit_key])
    requirements = payload.get("requirements", payload.get("analysis", {}).get("requirements", []))
    ids = [r["requirement_id"] for r in requirements]
    definitions = wire.get("$defs", {})
    if payload.get("source_ids"):
        if "EvidenceProof" in definitions:
            definitions["EvidenceProof"]["properties"]["citation_id"]["enum"] = payload["source_ids"]
    if ids:
        if "PlannedSearch" in definitions:
            recovery = [r["requirement_id"] for r in payload.get("recovery_requirements", [])]
            definitions["PlannedSearch"]["properties"]["requirement_ids"]["items"]["enum"] = recovery or ids
        if "GroundedClaim" in definitions:
            definitions["GroundedClaim"]["properties"]["requirement_ids"]["items"]["enum"] = ids
            if payload.get("source_ids"):
                definitions["GroundedClaim"]["properties"]["citation_ids"]["items"]["enum"] = payload["source_ids"]
        if "RequirementVerdict" in definitions:
            definitions["RequirementVerdict"]["properties"]["requirement_id"]["enum"] = ids
            prop = wire["properties"]["requirement_verdicts"]
            prop["minItems"] = prop["maxItems"] = len(ids)
            if payload.get("source_ids"):
                definitions["RequirementVerdict"]["properties"]["evidence_citation_ids"]["items"]["enum"] = payload["source_ids"]
    claims = payload.get("generated_answer", {}).get("claims", [])
    if claims and "claim_verdicts" in wire.get("properties", {}):
        prop = wire["properties"]["claim_verdicts"]
        prop["minItems"] = prop["maxItems"] = len(claims)
        definitions["ClaimVerdict"]["properties"]["claim_index"]["maximum"] = len(claims) - 1
        definitions["RequirementVerdict"]["properties"]["supporting_claim_indices"]["items"]["maximum"] = (
            len(claims) - 1
        )
    return wire


def _bind_schema(model, schema, provider, wire=None):
    # Strict OpenRouter routing rejects an endpoint when *any* requested parameter
    # is unsupported. Reasoning endpoints may support schemas but not temperature.
    # Omit sampling overrides rather than asking the router to silently ignore them.
    model = model.model_copy(update={"temperature": None})
    wire = schema.model_json_schema() if wire is None else wire

    def strict(value):
        if isinstance(value, dict):
            value.pop("default", None)
            if "properties" in value:
                value["required"] = list(value["properties"])
                value["additionalProperties"] = False
            for child in value.values():
                strict(child)
        elif isinstance(value, list):
            for child in value:
                strict(child)

    strict(wire)
    kwargs = {
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "strict": True, "schema": wire},
        }
    }
    if provider == "openrouter":
        body = dict(model.extra_body or {})
        body["provider"] = {**body.get("provider", {}), "require_parameters": True}
        kwargs["extra_body"] = body
    return model.bind(**kwargs)


async def _invoke_json(state, system, payload, schema, *, node="generate_answer", timeout=None, validator=None):
    runtime, settings = _runtime(state), get_settings()
    limit, max_tokens = _limits(node)
    reserve = runtime.reserve_seconds + (settings.copilot_check_timeout_seconds if node == "generate_answer" else 0)
    wire = _request_schema(schema, payload)
    payload = {**payload, "output_contract": schema.__name__}
    while True:
        call_timeout = runtime.timeout(timeout or limit, reserve_seconds=reserve)
        runtime.consume()
        response, attempt_error, started = None, {}, time.monotonic()
        attempt = runtime.attempts
        with span("llm.attempt", node=node, attempt=attempt, provider_retry=runtime.provider_retries) as metadata:
            try:
                model = get_llm(
                    copilot_provider_errors=True,
                    max_retries=0,
                    max_tokens=max_tokens,
                    openrouter_reasoning_effort=settings.copilot_check_reasoning_effort
                    if node == "check_grounding"
                    else settings.copilot_generate_reasoning_effort
                    if node == "generate_answer"
                    else None,
                )
                provider = settings.llm_provider
                base = getattr(model, "openai_api_base", "") or ""
                for host, actual in (
                    ("openrouter.ai", "openrouter"),
                    ("generativelanguage.googleapis.com", "gemini"),
                    ("api.x.ai", "grok"),
                    ("api.deepseek.com", "deepseek"),
                ):
                    if host in base:
                        provider = actual
                name = getattr(model, "model_name", settings.model_name)
                if isinstance(model, BaseChatModel):
                    if not isinstance(model, ChatOpenAI) or provider not in {"openrouter", "openai"}:
                        raise ValueError("configured provider does not support the strict output adapter")
                    model = _bind_schema(model, schema, provider, wire)
                    model = model.with_config(metadata={"ls_provider": provider, "ls_model_name": name, "node": node})
                with span("llm.provider", node=node, attempt=attempt, provider=provider, model=name):
                    response = await asyncio.wait_for(
                        model.ainvoke(
                            [
                                SystemMessage(content=system),
                                HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
                            ]
                        ),
                        call_timeout,
                    )
                    if _model_usage(response)["finish_reason"] == "error":
                        raise ProviderResponseError(getattr(response, "response_metadata", {}).get("error"))
                with span("llm.parse_validate", node=node, attempt=attempt):
                    metadata.update(_model_usage(response))
                    if _model_usage(response)["finish_reason"] == "length":
                        raise ValueError("model output truncated")
                    raw = response.content
                    if isinstance(raw, list):
                        raw = "".join(b.get("text", "") for b in raw if isinstance(b, dict))
                    if not isinstance(raw, str):
                        raise ValueError("invalid text output")
                    parsed = schema.model_validate_json(raw)
                    if validator:
                        validator(parsed)
                return parsed, _model_usage(response)
            except BudgetExhaustedError:
                raise
            except (ValidationError, ValueError) as exc:
                attempt_error = {
                    "error_type": type(exc).__name__,
                    "failure_stage": node,
                    "failure_kind": "output_contract" if response is not None else "configuration",
                }
                if isinstance(exc, ValidationError):
                    # Only the Pydantic error type, never its input or arbitrary field values.
                    attempt_error["validation_code"] = exc.errors(include_input=False, include_context=False)[0]["type"]
                elif str(exc) in {
                    "search plan exceeds remaining budget",
                    "search plan does not cover all target factual requirements",
                    "corrective query outside missing requirements",
                    "unknown requirement in search plan",
                    "filter absent from corpus",
                    "model without input entity",
                    "repeated query",
                    "checker must evaluate every claim exactly once",
                    "checker must evaluate every requirement exactly once",
                    "requirement not linked to a supported claim",
                    "derived requirement has unverified inputs",
                    "evidence quote not found in cited source",
                    "evidence proof outside claim citations",
                    "evidence proof outside diagnostic citations",
                    "supported claim cannot carry verification errors",
                    "diagnostic citation outside selected evidence",
                    "sufficient evidence requires source citations",
                    "diagnostic sources outside requirement model",
                    "external evidence cannot be established from corpus",
                    "unresolved evidence blocker cannot have sufficient context",
                    "answered requirement cannot have a blocker",
                    "answered requirement cannot have incomplete evidence",
                    "invalid supporting claim indices",
                    "missing requirement cannot have supporting claims",
                    "answered requirement requires support and no missing information",
                    "external requirement cannot be verified from the corpus",
                }:
                    attempt_error["validation_code"] = str(exc).replace(" ", "_")
                metadata.update(attempt_error)
                annotate(**attempt_error)
                if response is None:
                    raise CopilotDependencyError("model configuration unavailable") from exc
                raise CopilotModelOutputError() from exc
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                attempt_error = {
                    "error_type": type(exc).__name__,
                    "provider_status": status,
                    "failure_stage": node,
                    "failure_kind": "provider",
                }
                if isinstance(exc, ProviderResponseError):
                    attempt_error.update(provider_error_kind=exc.provider_error_kind, finish_reason="error")
                metadata.update(attempt_error)
                transient = status == 429 or isinstance(status, int) and status >= 500 or isinstance(exc, OSError)
                transient = transient or type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}
                transient = (
                    transient
                    or isinstance(exc, ProviderResponseError)
                    and exc.provider_error_kind in {"server", "rate_limit_exceeded", "provider_unavailable", "timeout"}
                )
                if (
                    transient
                    and runtime.provider_retries < 1
                    and runtime.can_continue()
                    and runtime.attempts < runtime.max_attempts
                ):
                    runtime.provider_retries += 1
                    continue
                annotate(**attempt_error)
                raise CopilotDependencyError(f"{node} unavailable ({type(exc).__name__})") from exc
            finally:
                runtime.events.append(
                    {
                        "node": node,
                        "llm": True,
                        "attempt": attempt,
                        "elapsed_seconds": time.monotonic() - started,
                        **(_model_usage(response) if response else {}),
                        **attempt_error,
                    }
                )
                events = [e for e in runtime.events if e.get("llm")]
                annotate(
                    llm_attempts=runtime.attempts,
                    provider_retry=runtime.provider_retries,
                    input_tokens=sum(e["input_tokens"] for e in events)
                    if all(e.get("input_tokens") is not None for e in events)
                    else None,
                    output_tokens=sum(e["output_tokens"] for e in events)
                    if all(e.get("output_tokens") is not None for e in events)
                    else None,
                )
