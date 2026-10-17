"""Mechanical checks supplement semantic grounding, never prove entailment."""

import re
from decimal import Decimal, InvalidOperation

from src.agents.copilot.nodes._shared import _requirements
from src.agents.copilot.validation.citations import CITATION_PATTERN


def numeric_values(text):
    values = set()
    pattern = r"(?<![\w])([0-9]+(?:[.,][0-9]+)*)(?:\s*(triệu|tỷ|nghìn|ngàn|kwh|wh|km))?"
    for number, unit in re.findall(pattern, text, re.I):
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3}){1,}", number):
            normalized = number.replace(".", "").replace(",", "")
        else:
            normalized = number.replace(",", ".")
        try:
            value = Decimal(normalized)
        except InvalidOperation:
            continue
        values.add(value)
        multiplier = {"triệu": 1000000, "tỷ": 1000000000, "nghìn": 1000, "ngàn": 1000, "kwh": 1000, "km": 1000}.get(
            unit.lower(), 1
        )
        values.add(value * multiplier)
    return values


def validate_claims(parsed, state):
    sources = {h["citation_id"]: h for h in state.get("selected_evidence", [])}
    requirements = set(_requirements(state))
    blocked = {}
    for i, claim in enumerate(parsed.claims):
        if (
            not set(claim.requirement_ids) <= requirements
            or not set(claim.citation_ids) <= set(sources)
            or len(set(claim.citation_ids)) != len(claim.citation_ids)
        ):
            blocked[i] = "citation"
            continue
        inline = set(CITATION_PATTERN.findall(claim.text))
        if inline - set(claim.citation_ids):
            blocked[i] = "citation"
            continue
        source_text = " ".join(
            sources[cid]["content"]
            + " "
            + sources[cid]["product_model"]
            + " "
            + str(sources[cid].get("effective_from"))
            + " "
            + str(sources[cid].get("effective_to"))
            for cid in claim.citation_ids
        )
        # Input numbers can represent customer needs; the semantic checker must bind their role.
        allowed = numeric_values(
            source_text
            + " "
            + state.get("query", "")
            + " "
            + state.get("customer_context", "")
            + " "
            + state.get("resolved_date", "")
        )
        if not numeric_values(CITATION_PATTERN.sub("", claim.text)) <= allowed:
            blocked[i] = "wrong_number"
    return blocked

