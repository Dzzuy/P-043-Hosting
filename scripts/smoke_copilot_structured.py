"""Live schema compatibility using synthetic retrieval only; never opens the database."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.copilot.graph import copilot_agent
from src.agents.copilot.nodes import planning, retrieval
from src.config import get_settings


async def snapshot(_):
    return None


async def search(request, state):
    hits = []
    for model, distance in [("VF 5", 326), ("VF 6", 480)]:
        if request.product_model and request.product_model != model:
            continue
        hits.append(
            {
                "chunk_id": f"synthetic-{model}",
                "document_id": f"synthetic-{model}",
                "content": f"{model}: quãng đường di chuyển {distance} km theo chuẩn NEDC. Đây là dữ liệu giả lập kiểm thử.",
                "title": f"Thông số giả lập {model}",
                "section": "Quãng đường",
                "context_prefix": None,
                "requires_context": False,
                "page": None,
                "source_uri": "synthetic-test-fixture",
                "effective_from": "2026-01-01",
                "effective_to": None,
                "status": "active",
                "version": "synthetic-1",
                "product_model": model,
                "document_type": "product_specs",
                "policy_type": None,
                "competitor_model": None,
                "retrieval_method": "dense",
                "native_score": 0.9,
                "rank": len(hits) + 1,
            }
        )
    return {"dense": hits, "bm25": [], "requirement_ids": request.requirement_ids, "errors": []}


async def main():
    retrieval._ensure_snapshot = snapshot
    retrieval._search = search
    planning._catalog = lambda _: {
        "product_model": ["VF 5", "VF 6", "ALL"],
        "document_type": ["product_specs"],
        "policy_type": [],
    }
    report = []
    cases = [
        ("simple_paraphrase", "VF 5 nạp đầy một lần thì đi được bao xa theo NEDC?"),
        ("comparison", "So sánh quãng đường NEDC của VF 5 và VF 6."),
        ("coaching", "Soạn lời chào ngắn cho khách mới, hỏi nhu cầu đi lại; không đưa thông số hay giá xe."),
    ]
    for name, query in cases:
        try:
            state = await copilot_agent.ainvoke({"query": query, "target_date": "2026-10-17"})
            result = state["final_response"]
            row = {
                "case": name,
                "status": result.status,
                "reason": result.reason_code,
                "citations": len(result.citations),
                "llm_attempts": state["runtime"].attempts,
                "typed_metrics": [r.metric for r in state.get("requirements", [])],
                "has_structured_review": state.get("grounding_review") is not None,
                "diagnostics": state.get("evidence_selection_diagnostics", []),
                "claims": state["generated_answer"].model_dump() if state.get("generated_answer") else None,
                "review": state["grounding_review"].model_dump() if state.get("grounding_review") else None,
                "trace": state["runtime"].events,
            }
        except Exception as exc:
            cause = exc.__cause__ or exc
            message = str(cause)
            settings = get_settings()
            for secret in [settings.openrouter_api_key, settings.openai_api_key]:
                if secret:
                    message = message.replace(secret, "[redacted]")
            row = {
                "case": name,
                "error_type": type(exc).__name__,
                "cause": type(cause).__name__,
                "provider_status": getattr(cause, "status_code", None),
                "message": message[:1400],
            }
        report.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    Path("tmp/copilot_structured_smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert all(row.get("status") == "answered" and row.get("has_structured_review") for row in report), report


asyncio.run(main())
