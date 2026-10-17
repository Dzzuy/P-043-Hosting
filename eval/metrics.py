"""Deterministic Gate 3 metrics over benchmark ground truth and runtime observations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


def metric_result(
    *,
    score: float | None,
    applicable: bool,
    passed: bool | None,
    reason: str,
    details: dict[str, Any] | None = None,
    not_observable: bool = False,
) -> dict[str, Any]:
    if not applicable:
        status = "not_applicable"
    elif not_observable:
        status = "not_observable"
    else:
        status = "pass" if passed else "fail"
    return {
        "score": score,
        "applicable": applicable,
        "passed": passed,
        "status": status,
        "reason": reason,
        "details": details or {},
    }


def _document_ids(items: Sequence[str]) -> list[str]:
    """Keep retrieval order while counting each document once across its chunks."""
    return list(dict.fromkeys(items))


def retrieval_hit_rate(expected: Mapping[str, Any], retrieved_document_ids: Sequence[str]) -> dict[str, Any]:
    relevant = set(expected["supporting_document_ids"])
    if not relevant:
        return metric_result(score=None, applicable=False, passed=None, reason="No supporting documents specified.")
    found = relevant.intersection(retrieved_document_ids)
    passed = bool(found)
    return metric_result(
        score=float(passed),
        applicable=True,
        passed=passed,
        reason="At least one supporting document retrieved." if passed else "No supporting document retrieved.",
        details={"matched_document_ids": sorted(found), "expected_document_ids": sorted(relevant)},
    )


def recall_at_k(expected: Mapping[str, Any], retrieved_document_ids: Sequence[str], k: int = 4) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be positive")
    relevant = set(expected["supporting_document_ids"])
    if not relevant:
        return metric_result(score=None, applicable=False, passed=None, reason="No supporting documents specified.")
    top_k_ids = _document_ids(retrieved_document_ids[:k])
    found = relevant.intersection(top_k_ids)
    score = len(found) / len(relevant)
    return metric_result(
        score=score,
        applicable=True,
        passed=score == 1.0,
        reason=f"Retrieved {len(found)} of {len(relevant)} supporting documents in the top {k} chunks.",
        details={"matched_document_ids": sorted(found), "top_k_document_ids": top_k_ids, "k": k},
    )


def citation_correctness(
    expected: Mapping[str, Any],
    citations: Sequence[Any],
    corpus_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    supporting = set(expected["supporting_document_ids"])
    forbidden = set(expected["forbidden_document_ids"])
    if not citations:
        if supporting and expected["behavior"] == "answer":
            return metric_result(
                score=0.0,
                applicable=True,
                passed=False,
                reason="Expected an answer with supporting citations, but none were returned.",
            )
        return metric_result(score=None, applicable=False, passed=None, reason="No citations returned to validate.")

    errors: list[str] = (
        ["Unexpected citations returned for a case with no expected supporting documents."] if not supporting else []
    )
    cited_ids: list[str] = []
    for index, citation in enumerate(citations):
        if not isinstance(citation, Mapping):
            errors.append(f"citations[{index}] is not an object")
            continue
        document_id = citation.get("document_id")
        if not isinstance(document_id, str) or not document_id:
            errors.append(f"citations[{index}] has no document_id")
            continue
        cited_ids.append(document_id)
        document = corpus_by_id.get(document_id)
        if document is None:
            errors.append(f"{document_id} does not exist in corpus")
            continue
        if supporting and document_id not in supporting:
            errors.append(f"{document_id} is not an expected supporting document")
        if document_id in forbidden:
            errors.append(f"{document_id} is forbidden")
        for field in ("source", "product_model", "effective_date"):
            aliases = {"source": "source_uri", "effective_date": "effective_from"}
            observed = citation.get(field, citation.get(aliases.get(field, field), ""))
            if str(observed) != str(document[field]):
                errors.append(f"{document_id} has incorrect {field}")

    passed = not errors
    return metric_result(
        score=float(passed),
        applicable=True,
        passed=passed,
        reason="Citations match the document-level benchmark contract." if passed else "; ".join(errors),
        details={"cited_document_ids": cited_ids, "errors": errors, "scope": "document_metadata_only"},
    )


def policy_version_correctness(
    expected: Mapping[str, Any], observed_document_ids: Sequence[str], *, source: str
) -> dict[str, Any]:
    policy = expected["policy_version"]
    required = policy["required_document_id"]
    forbidden = set(policy["forbidden_document_ids"])
    if required is None and not forbidden:
        return metric_result(
            score=None, applicable=False, passed=None, reason="No policy-version expectation specified."
        )
    observed = set(observed_document_ids)
    missing = required is not None and required not in observed
    disallowed = sorted(observed.intersection(forbidden))
    passed = not missing and not disallowed
    reasons = []
    if missing:
        reasons.append(f"Required document {required} absent from {source}.")
    if disallowed:
        reasons.append(f"Forbidden versions in {source}: {', '.join(disallowed)}.")
    return metric_result(
        score=float(passed),
        applicable=True,
        passed=passed,
        reason="Policy-version expectation satisfied." if passed else " ".join(reasons),
        details={
            "required_document_id": required,
            "forbidden_document_ids": sorted(forbidden),
            "observed_document_ids": sorted(observed),
        },
    )


def appropriate_behavior(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, Any]:
    behavior = expected["behavior"]
    if behavior == "clarify":
        clarification = actual.get("is_clarification")
        if not isinstance(clarification, bool):
            return metric_result(
                score=None,
                applicable=True,
                passed=None,
                not_observable=True,
                reason="Copilot exposes no structured clarification signal; suggested_next_question is not one.",
            )
        passed = clarification
    else:
        abstain = actual.get("is_abstain")
        if not isinstance(abstain, bool):
            return metric_result(
                score=0.0, applicable=True, passed=False, reason="Runtime is_abstain is missing or not boolean."
            )
        passed = (
            abstain
            if behavior == "abstain"
            else (
                not abstain
                and not actual.get("is_clarification", False)
                and bool(str(actual.get("answer", "")).strip())
            )
        )
    return metric_result(
        score=float(passed),
        applicable=True,
        passed=passed,
        reason=f"Expected {behavior}; observed compatible behavior."
        if passed
        else f"Expected {behavior}; runtime behavior differs.",
        details={"expected_behavior": behavior, "is_abstain": actual.get("is_abstain")},
    )


def required_fact_coverage(expected: Mapping[str, Any], answer: str) -> dict[str, Any]:
    """Literal coverage signal, not a semantic correctness score."""
    facts = expected["required_facts"]
    if not facts:
        return metric_result(score=None, applicable=False, passed=None, reason="No required facts.")

    def normalize(text):
        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold()).replace(",", ".")

    normalized_answer = normalize(answer)
    missing = [fact for fact in facts if normalize(fact) not in normalized_answer]
    return metric_result(
        score=(len(facts) - len(missing)) / len(facts),
        applicable=True,
        passed=not missing,
        reason="Literal required-fact coverage.",
        details={"missing_facts": missing, "scope": "literal_fact_coverage"},
    )


def aggregate_metrics(per_case_results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    names = sorted({name for case in per_case_results for name in case["metrics"]})
    aggregate: dict[str, Any] = {}
    for name in names:
        values = [case["metrics"][name] for case in per_case_results if name in case["metrics"]]
        observed = [item["score"] for item in values if item["applicable"] and item["score"] is not None]
        aggregate[name] = {
            "score": sum(observed) / len(observed) if observed else None,
            "applicable_cases": sum(item["applicable"] for item in values),
            "observed_cases": len(observed),
            "passed_cases": sum(item["status"] == "pass" for item in values),
            "failed_cases": sum(item["status"] == "fail" for item in values),
            "not_observable_cases": sum(item["status"] == "not_observable" for item in values),
            "not_applicable_cases": sum(item["status"] == "not_applicable" for item in values),
        }
    return aggregate
