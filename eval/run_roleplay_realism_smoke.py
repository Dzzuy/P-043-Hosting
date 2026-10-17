"""Repeatable, small real-model role-play behavior probe using synthetic advisor turns.

Run from the repository root. This uses the configured chat provider, writes no
real customer data, and does not call the evaluator or the product API.
"""

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from src.agents.roleplay.customer_agent import CustomerAgent
from src.agents.roleplay.graph import RoleplayGraph
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.turn_analyzer import TurnAnalyzer
from src.integrations.practice_persistence import SQLCheckpointRepository
from src.integrations.practice_runtime import SharedLLMCustomerModel, SharedLLMTurnAnalysisModel

SCENARIO_ID = "SCENARIO_01_VF5_TAXI"
SCENARIO_04_ID = "SCENARIO_04_VF6_ECO_PLUS_UPSELL"
SCENARIO_04_RUNS = {
    "discovery_and_plus": [
        "Chào chị, VF 6 có ưu đãi 9% Vì Tương Lai Xanh 2 khi đủ điều kiện.",
        "Chị đang đi xe gì, có đứng tên chị không?",
        "Chị dùng xe hằng ngày vào việc gì, chở ai và dự tính ngân sách thế nào ạ?",
        "Cuối tuần chị có đi xa hay về quê không? Khi chọn xe chị ưu tiên điều gì nhất?",
        "Chị lái xe lâu chưa, chỗ đỗ ở nhà và cơ quan thế nào, có chỗ sạc tại nhà không?",
        "Nếu đủ điều kiện, Eco từ 646 triệu còn 587,86 triệu; Plus từ 700 triệu còn 637 triệu, chênh 49,14 triệu. Chị thấy sao?",
        "Plus có 7 túi khí so với 4 trên Eco để thêm bảo vệ gia đình; camera 360° giúp quan sát khi đỗ ngõ hẹp. Chị muốn thử rồi cân nhắc không?",
    ],
    "missed_concern": [
        "Chào chị, chị lấy Plus luôn nhé?",
        "Plus đẹp hơn chị ạ.",
        "Chị chọn màu trước nhé.",
        "Mình đặt cọc luôn chị nhé.",
    ],
}
RUNS = {
    "helpful_advisor": [
        "Em chào anh, em có thể hỗ trợ anh tìm hiểu xe. Anh thường chạy khoảng bao nhiêu km mỗi ngày hoặc mỗi tháng ạ?",
        "Cảm ơn anh. Chi phí đổi xe cần nhìn cả tiền xe, pin, sạc và bảo dưỡng; em chưa muốn hứa mức tiết kiệm khi chưa kiểm tra chính sách đang áp dụng cho xe của anh.",
        "Em có thể lập bảng so sánh theo 5.000 km mỗi tháng, ghi rõ giả định tiền xăng và điều kiện sạc, rồi gửi anh xem trước khi quyết định.",
        "Ngoài chi phí, anh có lo việc dừng sạc trong ca chạy khách không? Mình có thể kiểm tra trạm gần tuyến anh chạy và hẹn trải nghiệm thực tế.",
    ],
    "missed_concern": [
        "Em chào anh, xe điện nhiều công nghệ hay lắm anh ạ.",
        "Dạ xe rất đẹp và đi êm anh nhé.",
        "Mình cứ xem màu xe trước anh nhé.",
        "Em gửi hình xe cho anh.",
    ],
    "discovery_and_next_step": [
        "Em chào anh, mỗi ngày anh chạy quãng đường khoảng bao nhiêu và chủ yếu ở đâu ạ?",
        "Anh thường nghỉ giữa ca ở khu vực nào, có tiện dừng sạc không ạ?",
        "Để so sát với Vios, em sẽ kiểm tra chính sách pin và sạc theo ngày mua xe, rồi tính một khoảng chi phí theo số km anh vừa chia sẻ; em chưa chốt một con số khi thiếu dữ liệu.",
        "Nếu anh thấy hướng này hợp lý, mình hẹn 15 phút xem xe và đối chiếu bảng chi phí theo ca chạy thực tế của anh nhé?",
    ],
}


def runs_for_scenario(scenario_id: str) -> dict[str, list[str]]:
    """Select persona-appropriate probes without creating a model client."""
    return SCENARIO_04_RUNS if scenario_id == SCENARIO_04_ID else RUNS


async def run_one(name: str, advisor_turns: list[str], scenario_id: str = SCENARIO_ID) -> dict:
    with TemporaryDirectory(prefix="p043-roleplay-realism-") as temp:
        graph = RoleplayGraph(
            ScenarioRepository(),
            TurnAnalyzer(SharedLLMTurnAnalysisModel()),
            CustomerAgent(SharedLLMCustomerModel()),
            SQLCheckpointRepository(f"sqlite:///{temp}/checkpoints.db"),
        )
        session_id = f"realism-{name}"
        try:
            await graph.start(session_id, scenario_id, max_turns=10)
            for advisor_turn in advisor_turns:
                state = await graph.get_session_state(session_id)
                if state.termination_status.value != "active":
                    break
                await graph.continue_session(session_id, advisor_turn)
            state = await graph.get_session_state(session_id)
            transcript = [message.model_dump() for message in state.messages]
            prior_customer = []
            false_mileage_memory = False
            for message in transcript:
                if message["role"] != "customer":
                    continue
                text = message["content"].casefold()
                if re.search(r"anh (?:vừa|đã) nói|anh nói rồi", text) and re.search(r"180|200|5[.,]?000", text):
                    if not any(re.search(r"180|200|5[.,]?000", older) for older in prior_customer):
                        false_mileage_memory = True
                prior_customer.append(text)
            return {
                "run": name,
                "status": "completed",
                "turns": state.turn_count,
                "termination": state.termination_status.value,
                "concern_prompt_counts": state.concern_prompt_counts,
                "spoken_fact_message_ids": state.spoken_fact_message_ids,
                "closing_outcome": state.closing_outcome,
                "active_objections": state.active_objections,
                "resolved_objections": state.resolved_objections,
                "linked_benefits": [link.model_dump() for link in state.linked_benefits],
                "policy_mentions": state.policy_mentions,
                "false_mileage_memory_detected": false_mileage_memory,
                "transcript": transcript,
            }
        except Exception as exc:
            return {"run": name, "status": "error", "error_type": type(exc).__name__, "error": str(exc)}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="JSON result path; defaults to a timestamped file")
    parser.add_argument("--scenario-id", choices=(SCENARIO_ID, SCENARIO_04_ID), default=SCENARIO_ID)
    args = parser.parse_args()
    results = [
        await run_one(name, turns, args.scenario_id) for name, turns in runs_for_scenario(args.scenario_id).items()
    ]
    output = args.output or Path(f"eval/results/roleplay_realism_smoke_{datetime.now(UTC):%Y-%m-%dT%H-%M-%SZ}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"date_utc": datetime.now(UTC).isoformat(), "scenario_id": args.scenario_id, "runs": results},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for result in results:
        print(
            result["run"],
            result["status"],
            result.get("turns"),
            result.get("termination"),
            result.get("concern_prompt_counts"),
        )
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
