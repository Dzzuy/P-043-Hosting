"""Validate the concise, evidence-backed presentation from a shared analysis."""

import re
from typing import Any


def normalize_intelligence(memory: dict, message_ids: set[str], customer_ids: set[str]) -> dict[str, Any] | None:
    """Legacy analyses remain readable; new sections require actual message evidence."""
    raw = memory.get("customer_intelligence")
    if not isinstance(raw, dict):
        return None

    def clean(value):
        return " ".join(value.split()) if isinstance(value, str) else ""

    def key(value):
        return re.sub(r"[\W_]+", " ", clean(value).casefold()).strip()

    def sources(item):
        ids = item.get("source_message_ids", [])
        return list(dict.fromkeys(s for s in ids if isinstance(s, str) and s in message_ids)) if isinstance(ids, list) else []

    points, outcomes, commitments = {}, {}, {}
    for item in raw.get("key_points", []) or []:
        if not isinstance(item, dict):
            continue
        topic, question, answer = (clean(item.get(field)) for field in ("topic", "question", "answer"))
        evidence = sources(item)
        if not (topic or question) or not evidence:
            continue
        # Later entries carry the latest conclusion for a repeated topic.
        points[key(topic or question)] = {
            "topic": topic or question, "question": question, "answer": answer,
            "status": "answered" if item.get("status") == "answered" and answer else "open",
            "source_message_ids": evidence,
        }
    for item in raw.get("outcomes", []) or []:
        if not isinstance(item, dict):
            continue
        text, evidence = clean(item.get("text")), sources(item)
        if text and customer_ids.intersection(evidence):
            outcomes[key(text)] = {"text": text, "source_message_ids": evidence}
    for item in raw.get("commitments", []) or []:
        if not isinstance(item, dict):
            continue
        actor, action, time = (clean(item.get(field)) for field in ("actor", "action", "time"))
        evidence = sources(item)
        if action and evidence:
            commitments[key(f"{actor} {action}")] = {
                "actor": actor, "action": action, "time": time, "source_message_ids": evidence,
            }
    # A confirmed decision or a promise appears once, in its dedicated section.
    dedicated = set(outcomes) | {key(f"{c['actor']} {c['action']} {c['time']}") for c in commitments.values()}
    points = [p for p in points.values() if key(p["answer"] or p["question"]) not in dedicated or p["status"] == "open"]
    return {"key_points": points, "outcomes": list(outcomes.values()), "commitments": list(commitments.values())}
