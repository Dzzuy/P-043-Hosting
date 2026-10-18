"""Five live development probes, kept separate from the 50-case benchmark."""

import argparse
import asyncio
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eval.copilot_eval.experiment import code_hash, experiment, reconcile, save
from eval.copilot_eval.telemetry import graph_case, serial, snapshot

CASES = [
    {
        "case_id": "DEV01",
        "query": "VF 5 Plus có pin khả dụng bao nhiêu kWh?",
        "ground_truth": "37,23 kWh",
        "goals": ["37,23 kWh"],
    },
    {
        "case_id": "DEV02",
        "query": "So sánh giá niêm yết kèm pin gồm VAT, số chỗ ngồi và quãng đường của VF 3 và VF 5; ghi rõ biến thể và chuẩn đo nếu nguồn có.",
        "ground_truth": "VF 3 Plus 296 triệu, 4 chỗ, 215 km (nguồn không chốt chuẩn cụ thể); VF 5 Plus 496 triệu, 5 chỗ, 326,4 km NEDC.",
        "goals": ["296 triệu", "4 chỗ", "215 km", "496 triệu", "5 chỗ", "326,4 km"],
    },
    {
        "case_id": "DEV03",
        "query": "VF 3 Plus TC2 và VF 5 Plus TC1 hiện có giá niêm yết kèm pin gồm VAT chênh nhau bao nhiêu? Với VF 5, pin khả dụng và bảo hành xe mới là bao nhiêu?",
        "ground_truth": "296 và 496 triệu, chênh 200 triệu; VF 5 pin 37,23 kWh; bảo hành xe 7 năm/160.000 km (nguồn không xác nhận quy tắc điều kiện đến trước).",
        "goals": ["chênh 200 triệu", "37,23 kWh", "7 năm/160.000 km"],
    },
    {
        "case_id": "DEV04",
        "query": "Theo chính sách sạc áp dụng ngày 01/10/2026, VF 5 biển vàng có được sạc miễn phí lúc 10 giờ Chủ Nhật không? Giải thích điều kiện khung giờ.",
        "target_date": "2026-10-01",
        "ground_truth": "Không. Xe biển vàng cuối tuần chỉ trong 23:00–06:00 và 14:00–16:00.",
        "goals": ["không lúc 10 giờ Chủ Nhật", "23:00–06:00", "14:00–16:00"],
    },
    {
        "case_id": "DEV05",
        "query": "VF 6 có pin và quãng đường bao nhiêu, mấy chỗ ngồi? Đại lý đang còn bao nhiêu xe để giao ngay?",
        "ground_truth": "Nguồn ghi dung lượng pin 59,6 kW (đơn vị bất thường, không tự sửa sang kWh); quãng đường 485 km NEDC, nguồn chưa phân biệt phiên bản. Corpus không nêu số chỗ, không xác nhận tồn kho đại lý.",
        "goals": ["nêu giới hạn đơn vị pin 59,6 kW", "485 km NEDC", "không bịa số chỗ", "không bịa tồn kho"],
    },
]


async def execute(output, ids=None, cases=None):
    from src.agents.copilot.graph import copilot_agent
    from src.agents.copilot.runtime import RuntimeBudget
    from src.config import get_settings
    from src.knowledge.index_readiness import check_copilot_index
    from src.observability import graph_config

    cases = [c for c in (CASES if cases is None else cases) if not ids or c["case_id"] in ids]
    if not cases or len({c["case_id"] for c in cases}) != len(cases):
        raise ValueError("development cases must have unique IDs and cannot be empty")
    output.mkdir(parents=True, exist_ok=False)
    service, examples, manifest = experiment(cases, output.name, output, {"suite": "development", "transport": "graph"})
    index = await asyncio.to_thread(check_copilot_index)
    records = []
    try:
        for case in cases:
            updates = []

            def observe(name, state):
                updates.append({"node": name, "state": snapshot(state)})
                save(output / f"{case['case_id']}.nodes.json", updates)

            runtime = RuntimeBudget.create(get_settings())
            started = time.monotonic()
            with graph_case(service, case, output.name, examples[case["case_id"]], observe) as scope:
                row = {"case_id": case["case_id"], "request_id": scope.request_id}
                try:
                    state = await asyncio.wait_for(
                        copilot_agent.ainvoke(
                            {
                                "query": case["query"],
                                "target_date": case.get("target_date"),
                                "history": [],
                                "snapshot": index,
                                "runtime": runtime,
                                "request_id": scope.request_id,
                            },
                            config={"recursion_limit": 80, **graph_config()},
                        ),
                        get_settings().copilot_request_timeout_seconds,
                    )
                    row.update(serial(state["final_response"]))
                    if scope.root:
                        scope.root.outputs = row
                except Exception as exc:
                    row.update(
                        error_type=type(exc).__name__,
                        cause_type=type(exc.__cause__).__name__ if exc.__cause__ else None,
                    )
                    row["error_frames"] = [
                        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                        for frame in traceback.extract_tb(exc.__traceback__)
                    ]
                    if scope.root:
                        scope.root.error = type(exc).__name__
                row.update(elapsed_seconds=time.monotonic() - started, trace=runtime.events)
            records.append(row)
            save(output / f"{case['case_id']}.json", row)
            print(
                case["case_id"], row.get("status", row.get("error_type")), round(row["elapsed_seconds"], 2), flush=True
            )
        save(output / "results.json", records)
        save(output / "integrity.json", {"code_unchanged": manifest["code_hash"] == code_hash()})
        if not reconcile(service, records, output):
            raise RuntimeError("LangSmith reconciliation incomplete")
    finally:
        service.close()
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/results")
        / ("p043-copilot-dev-" + datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%Y%m%d_%H%M%S")),
    )
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--cases", type=Path, help="Explicit development probes, separate from the benchmark")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8")) if args.cases else None
    asyncio.run(execute(args.output, args.case_id, cases))
