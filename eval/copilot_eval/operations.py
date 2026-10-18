"""Operational metrics with explicit request/attempt denominators and unknowns."""

import math
import statistics
from collections import Counter, defaultdict


def distribution(values):
    values = sorted(x for x in values if isinstance(x, (int, float)) and math.isfinite(x))

    def q(p):
        if not values:
            return None
        n = (len(values) - 1) * p
        i = int(n)
        return values[i] + (values[min(i + 1, len(values) - 1)] - values[i]) * (n - i)

    return {
        "count": len(values),
        "mean": statistics.mean(values) if values else None,
        "p50": q(0.5),
        "p95": q(0.95),
        "p99": q(0.99),
        "max": max(values) if values else None,
    }


def rate(n, d):
    return {"numerator": n, "denominator": d, "value": n / d if d else None}


def operations(rows):
    events = [e for r in rows for e in r.get("trace", [])]
    llm = [e for e in events if e.get("llm")]
    decisions = [e for e in events if e.get("decision")]
    bad = [e for e in llm if e.get("error_type")]

    def timeout(e):
        return (
            "timeout"
            in (
                str(e.get("error_type", "")) + str(e.get("cause_type", "")) + str(e.get("provider_error_kind", ""))
            ).lower()
        )

    request_errors = [r for r in rows if r.get("error_type") or r.get("http_status", 200) >= 500]
    nodes = defaultdict(list)
    for e in events:
        if not e.get("llm") and not e.get("decision"):
            nodes[e.get("node", "unknown")].append(e.get("elapsed_seconds"))
    tokens = {}
    for kind, group in (("agent", llm), ("jev", decisions)):
        tokens[kind] = {}
        for key in ("input_tokens", "output_tokens"):
            known = [e[key] for e in group if isinstance(e.get(key), (int, float))]
            tokens[kind][key] = {
                "known_total": sum(known),
                "known_events": len(known),
                "events": len(group),
                "complete": len(known) == len(group),
            }
    known_cost = [
        e.get("cost")
        for e in decisions
        if not e.get("cached") and isinstance(e.get("cost"), (int, float)) and e.get("cost") > 0
    ]
    memory = [r.get("memory", {}).get("peak_rss_bytes") for r in rows]
    memory = [v for v in memory if isinstance(v, (int, float))]
    available_memory = [r.get("memory", {}).get("minimum_available_bytes") for r in rows]
    available_memory = [v for v in available_memory if isinstance(v, (int, float))]
    errored_requests = [r for r in rows if any(e.get("error_type") for e in r.get("trace", []) if e.get("llm"))]
    recovered = [
        r
        for r in errored_requests
        if not r.get("error_type")
        and r.get("status", r.get("response", {}).get("status")) in {"answered", "partial", "needs_clarification"}
    ]
    n = len(rows)
    return {
        "requests": n,
        "request_error_rate": rate(len(request_errors), n),
        "latency_seconds": distribution([r.get("elapsed_seconds") for r in rows]),
        "time_to_first_token_seconds": None,
        "streaming_scope": "No SSE/streaming probe; TTFT, disconnect/cancellation behavior and streaming error rate are unmeasured.",
        "zero_error_upper_95_one_sided": 1 - 0.05 ** (1 / n) if n and not request_errors else None,
        "provider_error_attempt_rate": rate(sum(e.get("failure_kind") == "provider" for e in llm), len(llm)),
        "llm_timeout_attempt_rate": rate(sum(timeout(e) for e in llm), len(llm)),
        "request_timeout_rate": rate(
            sum(
                timeout(r) or any(timeout(e) for e in r.get("trace", []) if e.get("llm")) and bool(r.get("error_type"))
                for r in rows
            ),
            n,
        ),
        "schema_contract_error_attempt_rate": rate(
            sum(e.get("failure_kind") == "output_contract" for e in llm), len(llm)
        ),
        "requests_with_recovered_attempt_errors": rate(
            sum(
                any(e.get("error_type") for e in r.get("trace", []) if e.get("llm")) and not r.get("error_type")
                for r in rows
            ),
            n,
        ),
        "completed_useful_response_after_attempt_error": rate(len(recovered), len(errored_requests)),
        "recovery_note": "A non-exception fallback is not useful recovery. Useful response here excludes abstention after errors; semantic correctness remains separately judged.",
        "http_4xx_rate": rate(
            sum(400 <= r.get("http_status", 0) < 500 for r in rows), sum("http_status" in r for r in rows)
        ),
        "technical_fallback_rate": rate(
            sum(
                r.get("reason_code", r.get("response", {}).get("reason_code"))
                in {"verification_failed", "budget_exhausted", "retrieval_degraded"}
                for r in rows
            ),
            n,
        ),
        "provider_retries": sum(r["provider_retries"] for r in rows if "provider_retries" in r)
        if any("provider_retries" in r for r in rows)
        else None,
        "provider_retry_observed_requests": sum("provider_retries" in r for r in rows),
        "attempts": len(llm),
        "attempt_errors": dict(Counter(e.get("validation_code") or e.get("error_type") for e in bad)),
        "jev_decisions": len(decisions),
        "jev_unscored": sum(e.get("route") == "unscored" for e in decisions),
        "jev_reasons": dict(Counter(e.get("reason", "unknown") for e in decisions)),
        "jev_decision_timeout_rate": rate(
            sum(e.get("reason") == "timeout" for e in decisions if not e.get("cached")),
            sum(not e.get("cached") for e in decisions),
        ),
        "jev_provider_error_rate": rate(
            sum(
                str(e.get("reason", "")).startswith("http_") or e.get("reason") == "connection_error"
                for e in decisions
                if not e.get("cached")
            ),
            sum(not e.get("cached") for e in decisions),
        ),
        "timeout_scope_note": "Chat LLM attempt timeouts and Jev decision timeouts use separate denominators. Jev timeout can include its queue/deadline budget. Requests with unavailable usage are not assumed free.",
        "jev_decision_latency_seconds": distribution(
            [e.get("elapsed_seconds") for e in decisions if not e.get("cached")]
        ),
        "tokens": tokens,
        "cost_usd": {
            "agent_actual": None,
            "agent_reason": "runtime events do not expose billable cost; see Cloud cost readback for available billing data",
            "jev_known_positive_cost": sum(known_cost) if known_cost else None,
            "jev_known_events": len(known_cost),
            "jev_uncached_events": sum(not e.get("cached") for e in decisions),
            "jev_complete": len(known_cost) == sum(not e.get("cached") for e in decisions),
        },
        "peak_rss_bytes": max(memory) if memory else None,
        "minimum_available_system_memory_bytes": min(available_memory) if available_memory else None,
        "ram_observed_requests": len(memory),
        "node_latency_seconds": {k: distribution(v) for k, v in nodes.items()},
        "quality_statuses": dict(
            Counter(r.get("status") or r.get("response", {}).get("status") or "technical_error" for r in rows)
        ),
    }
