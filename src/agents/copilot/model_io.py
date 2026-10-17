"""One call per node; one request-wide transient retry, no schema/semantic retry."""

import asyncio
import json
import re
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


def _bind_schema(model, schema, provider):
    wire = schema.model_json_schema()

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
    payload = {**payload, "output_schema": schema.model_json_schema()}
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
                    if (
                        settings.copilot_native_json_schema
                        and isinstance(model, ChatOpenAI)
                        and provider in {"openrouter", "openai"}
                    ):
                        model = _bind_schema(model, schema, provider)
                    elif (
                        settings.copilot_json_mode
                        and isinstance(model, ChatOpenAI)
                        and provider in {"openrouter", "openai"}
                    ):
                        model = model.bind(response_format={"type": "json_object"})
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
                    fence = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", raw, re.S)
                    parsed = schema.model_validate_json(fence.group(1) if fence else raw.strip())
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


async def _invoke_text(state, system, payload, *, node="generate_answer", timeout=None):
    runtime, settings = _runtime(state), get_settings()
    limit, max_tokens = _limits(node)
    reserve = runtime.reserve_seconds + settings.copilot_check_timeout_seconds
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
                    model = model.with_config(metadata={"ls_provider": provider, "ls_model_name": name, "node": node})
                with span("llm.provider", node=node, attempt=attempt, provider=provider, model=name):
                    human_content = (
                        json.dumps(payload, ensure_ascii=False, default=str)
                        if isinstance(payload, dict)
                        else str(payload)
                    )
                    response = await asyncio.wait_for(
                        model.ainvoke(
                            [
                                SystemMessage(content=system),
                                HumanMessage(content=human_content),
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
                    if not isinstance(raw, str) or not raw.strip():
                        raise ValueError("invalid text output")
                return raw.strip(), _model_usage(response)
            except BudgetExhaustedError:
                raise
            except (ValidationError, ValueError) as exc:
                attempt_error = {
                    "error_type": type(exc).__name__,
                    "failure_stage": node,
                    "failure_kind": "output_contract" if response is not None else "configuration",
                }
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
