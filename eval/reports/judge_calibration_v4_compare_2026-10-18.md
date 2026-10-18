# Hiệu chỉnh judge v4: so sánh DeepSeek V3.2 với nhãn chuyên gia (18/10/2026)

Ba lần chạy judge thật bằng DeepSeek V3.2 (`judge_calibration_v4_deepseek_run{1,2,3}.json`),
so với bộ nhãn `eval/datasets/judge_calibration_v4.json` (rubric `sales-rubric-v4`,
6 case, 30 nhãn đã duyệt). Kết quả thô: `judge_calibration_v4_compare_2026-10-18.json`.

## Tóm tắt

- Số case chấm được: 5/6 (JC1–JC5). Trạng thái chung là INCOMPLETE vì JC6 lỗi.
- Khớp điểm chính xác: 97,6% (trung bình 3 lần chạy), MAE 0,024, tính trên 14 ô mà cả
  chuyên gia và judge đều cho điểm.
- Khớp quyết định "chấm hay chưa chấm": 76% (19/25 ô).
- Độ ổn định: 22/25 nhãn giống hệt nhau qua 3 lần chạy (88%), 2 lần đổi trạng thái
  (chấm ↔ chưa chấm), biên độ điểm trung bình 0,056.

## Hạn chế đã biết: JC6 lỗi ở cả 3 lần chạy

`JC6_VF6_PLUS_UPSELL` không cho ra kết quả ở lần chạy nào:

- Lần 1–2: `structured model invocation failed for FactualFindingsDraft` (AI trả về sai định dạng).
- Lần 3: `factual source quote is not exact: PROMOTION_SALES_VINFAST_20260921` (AI trích
  tài liệu khuyến mãi không đúng nguyên văn).

Vì vậy JC6 bị loại khỏi mọi chỉ số bên dưới. Kết quả chỉ phản ánh JC1–JC5.

## Theo từng tiêu chí (trung bình 3 lần chạy)

| Tiêu chí | Ô có điểm | Khớp chính xác | Lệch tối đa 1 điểm | Khớp "chấm hay chưa chấm" |
|---|---|---|---|---|
| need_discovery (khám phá nhu cầu) | 4 | 100% | 100% | 80% (4/5) |
| product_knowledge (kiến thức sản phẩm) | 1 | 100% | 100% | 40% (2/5) |
| objection_handling (xử lý phản đối) | 4 | 91,7% | 100% | 80% (4/5) |
| policy_accuracy (chính sách) | 1 | 100% | 100% | 80% (4/5) |
| closing_next_step (chốt bước tiếp theo) | 4 | 100% | 100% | 100% (5/5) |

## Lệch về "chấm hay chưa chấm"

### Khi nào dùng nhãn "chưa chấm"

"Chưa chấm" (không có điểm) là nhãn hợp lệ cho cả chuyên gia lẫn judge trong sản phẩm
(`src/models/evaluation.py`, `src/agents/roleplay/prompts/evaluator.py`). Chỉ dùng khi:

1. **Không có cơ hội**: trong diễn biến hội thoại, chưa phát sinh tình huống cần vận dụng kỹ năng đó. Ví dụ:
   khách không phản đối gì (objection_handling), chưa ai nói về giá hay chính sách
   (policy_accuracy), hội thoại dừng trước lúc chốt (closing_next_step).
2. **Không đủ bằng chứng**: transcript quá ngắn để kết luận.

Nếu có cơ hội mà nhân viên bỏ lỡ thì chấm **1 điểm**, không để "chưa chấm". Bỏ lỡ cơ hội
là điểm yếu, còn không có cơ hội thì không phải. Tiêu chí "chưa chấm" không tính vào
điểm tổng (`overall_score`), và app hiển thị "Chưa chấm". Ngoại lệ do code bắt buộc:
policy_accuracy phải được chấm khi kịch bản có chính sách cần nêu và nhân viên đã nói
về giá hoặc chính sách. Không bao giờ cho điểm thấp khi không có bằng chứng trong transcript.

### Các ô lệch

- Judge cho điểm trong khi chuyên gia để "chưa chấm": JC2 product_knowledge = 1,
  JC2 objection_handling = 2, JC4 product_knowledge = 1, JC5 need_discovery = 2.
- JC1 policy_accuracy: chuyên gia chấm 1, nhưng judge để "chưa chấm" ở cả 3 lần
  (nhân viên không hề nói về chính sách).
