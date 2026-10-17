"""One input guard/analysis call; no retrieval for clarification or blocked input."""

import re
from datetime import date
from uuid import uuid4

from src.agents.copilot import prompts
from src.agents.copilot.model_io import _invoke_json
from src.agents.copilot.nodes import planning
from src.agents.copilot.nodes._shared import observed
from src.agents.copilot.state import CopilotResponse, IntakeDecision, PlannedSearch, Requirement, SearchPlan
from src.knowledge.validity import parse_target_date, today_in_vietnam
from src.observability import allow_content, annotate

PURE_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "alo",
    "halo",
    "xin chào",
    "xin chao",
    "chào",
    "chao",
    "chào bạn",
    "chao ban",
    "chào em",
    "chao em",
    "chào anh",
    "chao anh",
    "chào chị",
    "chao chi",
    "chào shop",
    "chao shop",
    "chào ad",
    "chao ad",
    "cảm ơn",
    "cam on",
    "cảm ơn bạn",
    "cam on ban",
    "cảm ơn nhé",
    "cam on nhe",
    "cảm ơn nha",
    "cam on nha",
    "thanks",
    "thank you",
    "tks",
    "bạn là ai",
    "ban la ai",
    "bạn có thể làm gì",
    "ban co the lam gi",
    "giới thiệu bản thân",
    "gioi thieu ban than",
    "help",
    "trợ giúp",
    "tro giup",
}


def _check_pure_greeting(query: str) -> str | None:
    """Detect if query is purely a conversational greeting/thanks/help request without factual task.

    Must match the ENTIRE message after stripping punctuation and whitespace.
    Returns the canned reply text if pure greeting, or None if task/mixed.
    """
    cleaned = re.sub(r"[^\w\s]", "", query).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned in PURE_GREETINGS:
        if any(w in cleaned for w in ["cảm ơn", "cam on", "thanks", "thank you", "tks"]):
            return (
                "Rất vui được hỗ trợ bạn! Nếu cần thêm thông tin xe, so sánh "
                "hoặc đối chiếu chính sách ưu đãi cho khách hàng, bạn cứ cho mình biết nhé."
            )
        if any(
            w in cleaned
            for w in [
                "bạn là ai",
                "ban la ai",
                "bạn có thể làm gì",
                "ban co the lam gi",
                "help",
                "trợ giúp",
                "tro giup",
                "giới thiệu",
            ]
        ):
            return (
                "Chào bạn! Tôi là trợ lý VinFast AI Copilot, sẵn sàng hỗ trợ bạn tra cứu "
                "thông số kỹ thuật, giá bán niêm yết, chính sách ưu đãi pin và sạc, "
                "cũng như chuẩn bị nội dung tư vấn khách hàng. Bạn đang cần hỗ trợ dòng xe nào?"
            )
        return "Chào bạn! Mình có thể giúp tra cứu xe, đối chiếu chính sách hoặc chuẩn bị nội dung tư vấn. Bạn đang cần hỗ trợ xe nào?"
    return None


def resolve_date(query, supplied):
    dates, invalid = set(), False
    pattern = r"(?<!\d)(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})(?!\d)"
    for match in re.finditer(pattern, query):
        raw = match.group()
        try:
            if "/" in raw:
                day, month, year = map(int, raw.split("/"))
                parsed = date(year, month, day)
            else:
                parsed = date.fromisoformat(raw)
        except ValueError:
            invalid = True
            continue
        # Event dates are facts used to evaluate a policy, not its lookup date.
        prefix = re.split(r"[.!?;\n]", query[: match.start()].lower())[-1][-100:]
        events = list(
            re.finditer(
                r"mua|hóa đơn|hoá đơn|bàn giao|đặt cọc|ký hợp đồng|đăng ký|giao xe|phiên sạc|sạc lúc|sạc ngày|nhận xe",
                prefix,
            )
        )
        lookups = list(
            re.finditer(r"tra cứu|đối chiếu|tính đến|hiệu lực|bảng giá|giá\s+(?:vào\s+|tại\s+)?ngày", prefix)
        )
        if events and (not lookups or events[-1].start() > lookups[-1].start()):
            continue
        if not events and not lookups:
            suffix = re.split(r"[.!?;\n,]", query[match.end() :].lower())[0][:30]
            if re.search(r"mua|hóa đơn|hoá đơn|bàn giao|đặt cọc|giao xe|phiên sạc|nhận xe", suffix):
                continue
        dates.add(parsed)
    target = parse_target_date(supplied)
    conflict = invalid or len(dates) > 1 or bool(target and dates and target not in dates)
    effective = target or (next(iter(dates)) if len(dates) == 1 else None)
    return effective, conflict


def _validate_intake(decision, state, history):
    if decision.guard_decision.decision != "allow" or decision.route != "simple":
        return
    if decision.simple_search is None:
        return
    search = PlannedSearch(
        **decision.simple_search.model_dump(), requirement_ids=[r.requirement_id for r in decision.requirements]
    )
    planning.validate_plan(
        SearchPlan(searches=[search]),
        {**state, "history": history, "analysis": decision, "requirements": decision.requirements},
    )


def atomic_requirements(decision):
    """Separate direct vehicle metrics so coverage cannot conflate price and range, preserving conditions."""
    normalized = []
    for requirement in decision.requirements:
        text = requirement.description
        if requirement.kind != "fact":
            normalized.append(requirement)
            continue
        attributes = []
        if re.search(r"giá|msrp", text, re.I):
            if re.search(r"thuê pin", text, re.I):
                attributes.append("Giá niêm yết (thuê pin)")
            elif re.search(r"kèm pin", text, re.I):
                attributes.append("Giá niêm yết (kèm pin)")
            else:
                attributes.append("Giá niêm yết")
            if re.search(r"vat", text, re.I):
                attributes[-1] += " (giữ đúng điều kiện VAT trong yêu cầu)"
        if re.search(r"quãng đường|nedc|wltp", text, re.I):
            standard = "NEDC" if "nedc" in text.lower() else "WLTP" if "wltp" in text.lower() else "chuẩn công bố"
            attributes.append(f"Quãng đường di chuyển theo {standard}")
        if re.search(r"dung lượng|kwh", text, re.I):
            attributes.append("Dung lượng pin khả dụng, đúng đơn vị nguồn")
        entities = list(dict.fromkeys(re.findall(r"\bVF[\s-]*\d+(?:\s+(?:Plus|Eco))?", text, re.I)))
        if len(attributes) > 1 and entities:
            # Extract any qualifiers like dates, customer segments, or conditions present in text
            qualifiers = []
            date_m = re.findall(
                r"(?:vào\s+|tại\s+|tính đến\s+|áp dụng\s+(?:từ\s+)?|tháng\s+|năm\s+)\d{1,2}(?:[/-]\d{1,2})?(?:[/-]\d{2,4})?",
                text,
                re.I,
            )
            if date_m:
                qualifiers.extend(date_m)
            cust_m = re.findall(
                r"(?:cho\s+|đối với\s+)(?:khách(?: hàng)?\s+[^,.;]+|doanh nghiệp[^,.;]*|xe dịch vụ[^,.;]*)",
                text,
                re.I,
            )
            if cust_m:
                qualifiers.extend(cust_m)
            qualifier_str = f" ({', '.join(dict.fromkeys(q.strip() for q in qualifiers))})" if qualifiers else ""

            normalized.extend(
                Requirement(requirement_id="R1", description=f"{attribute} của {entity}{qualifier_str}.")
                for entity in entities
                for attribute in attributes
            )
        else:
            normalized.append(requirement)
    # Preserve all original requirements when expansion cannot fit the approved cap.
    if len(normalized) > 6:
        return decision
    return decision.model_copy(
        update={"requirements": [r.model_copy(update={"requirement_id": f"R{i}"}) for i, r in enumerate(normalized, 1)]}
    )


@observed
async def analyze_and_route(state):
    # Check for pure conversational greetings first (0 LLM, 0 searches)
    greeting_reply = _check_pure_greeting(state["query"])
    if greeting_reply is not None:
        annotate(route="greeting", workflow_version="2")
        request_id = state.get("request_id") or uuid4().hex
        final = CopilotResponse(
            status="answered",
            answer=greeting_reply,
            citations=[],
            product_insights=[],
            talking_points=[],
            suggested_message=None,
            suggested_next_question="Bạn đang quan tâm đến dòng xe nào của VinFast (VF 3, VF 5, VF 6, VF 7, VF 8, VF 9)?",
            sales_actions=[],
            missing_information=[],
            request_id=request_id,
            answer_kind="coaching",
        )
        return {
            "history": state.get("history", []),
            "final_response": final,
            "route": "end",
            "request_id": request_id,
        }

    history, size = [], 0
    for message in reversed(state.get("history", [])[-8:]):
        content = message.get("content", "")
        if size + len(content) > 12000:
            break
        if message.get("role") in {"user", "assistant"}:
            history.insert(0, {"role": message["role"], "content": content})
            size += len(content)
    target, date_conflict = resolve_date(state["query"], state.get("target_date"))
    decision, _ = await _invoke_json(
        state,
        prompts.INTAKE_PROMPT,
        {
            "query": state["query"],
            "customer_context": state.get("customer_context", ""),
            "memory_summary": state.get("memory_summary") or "",
            "history": history,
            "domain": state.get("domain", "all"),
            "lookup_date": str(target or today_in_vietnam()),
            "catalog": planning._catalog(state),
        },
        IntakeDecision,
        node="analyze_and_route",
        validator=lambda decision: _validate_intake(decision, state, history),
    )
    decision = atomic_requirements(decision)
    if decision.route == "simple" and (
        len([r for r in decision.requirements if r.kind == "fact"]) > 2
        or decision.task == "comparison"
        or len(decision.product_models) > 1
    ):
        decision = decision.model_copy(update={"route": "complex", "simple_search": None})
    if decision.route == "clarify" and (
        (decision.task == "comparison" and len(decision.product_models) >= 2)
        or (
            any(r.kind == "fact" for r in decision.requirements)
            and any(r.kind == "external" for r in decision.requirements)
        )
        or (
            any(r.kind == "fact" for r in decision.requirements)
            and any(r.kind == "advice" for r in decision.requirements)
        )
    ):
        # Missing customer preferences or external requests must not suppress a factual lookup.
        decision = decision.model_copy(update={"route": "complex", "simple_search": None})
    answer_kind = getattr(decision, "answer_kind", "factual")
    result = {
        "history": history,
        "analysis": decision,
        "product_models": [m for m in decision.product_models if m.upper() != "ALL"],
        "requirements": decision.requirements,
        "task": decision.task,
        "answer_kind": answer_kind,
        "target_date": target,
        "resolved_date": str(target or today_in_vietnam()),
        "request_id": state.get("request_id") or uuid4().hex,
        "generation_count": 0,
        "corrective_retrieval_count": 0,
        "retrieval_rounds": 0,
        "tool_calls": 0,
        "search_signatures": [],
        "evidence_registry": [],
        "candidate_evidence": [],
        "selected_evidence": [],
        "selected_anchor_ids": [],
        "evidence_query_provenance": {},
        "evidence_query_references": {},
        "rejected_evidence_ids": [],
        "evidence_selection_diagnostics": [],
        "retrieval_errors": 0,
        "parent_context_cache": {},
        "feedback": "",
        "fallback_reason": "insufficient_evidence",
        "clarification_question": None,
        "profile_name": "simple",
        "retrieval_mode": "search",
    }
    if decision.guard_decision.decision == "block" or decision.route == "blocked":
        return {**result, "route": "fallback_response", "fallback_reason": "input_blocked"}
    allow_content()  # The combined call itself began with capture disabled.
    if date_conflict:
        return {
            **result,
            "route": "fallback_response",
            "clarification_question": "Bạn muốn tra cứu theo ngày nào để thống nhất giữa câu hỏi và form?",
        }
    if decision.route in {"clarify", "out_of_scope"}:
        return {
            **result,
            "route": "fallback_response",
            "clarification_question": decision.clarification_question,
            "fallback_reason": "out_of_scope" if decision.route == "out_of_scope" else "insufficient_evidence",
        }

    # Direct coaching path: advice / call prep / message drafting without factual lookup requirements
    if answer_kind == "coaching" and not any(r.kind == "fact" for r in decision.requirements):
        annotate(route="coaching", workflow_version="2")
        return {**result, "route": "generate_answer"}

    simple = (
        decision.route == "simple"
        and decision.task == "knowledge"
        and len(decision.product_models) <= 1
        and len(decision.requirements) <= 2
        and decision.simple_search is not None
    )
    annotate(route="simple" if simple else "complex", workflow_version="2")
    if simple and decision.simple_search is not None:
        search = PlannedSearch(
            **decision.simple_search.model_dump(), requirement_ids=[r.requirement_id for r in decision.requirements]
        )
        return {**result, "search_plan": SearchPlan(searches=[search]), "route": "retrieve_documents"}
    return {**result, "profile_name": "complex", "route": "plan_queries"}
