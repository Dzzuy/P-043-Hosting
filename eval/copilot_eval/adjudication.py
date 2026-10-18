"""Apply explicit, evidence-backed decisions without modifying raw judge output."""

import copy
import json

from eval.copilot_eval.experiment import digest


def apply_decisions(reviews, document, raw_hash):
    if document.get("raw_scores_hash") != raw_hash:
        raise ValueError("Adjudication belongs to different raw scores")
    result = copy.deepcopy(reviews)
    indexed = {r["case_id"]: r for r in result}
    if len(indexed) != len(result):
        raise ValueError("Duplicate raw reviews")
    for decision in document["decisions"]:
        if not all(decision.get(k) for k in ("reviewer", "reason", "before", "after")):
            raise ValueError("Decision requires reviewer, reason and full before/after")
        review = indexed[decision["case_id"]]
        if review.get("custom") != decision["before"]:
            raise ValueError("Decision before-state differs from raw/prior reviewed state")
        review["custom"] = copy.deepcopy(decision["after"])
    return result


def reviewed(raw_path, decisions_path=None):
    reviews = json.loads(raw_path.read_text(encoding="utf-8"))
    if decisions_path is None:
        return reviews
    return apply_decisions(reviews, json.loads(decisions_path.read_text(encoding="utf-8")), digest(raw_path))
