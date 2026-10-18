# Báo cáo Đánh giá Copilot Agent Benchmark (`copilot-benchmark-20261018`)

- **Ngày thực hiện**: 18/10/2026
- **Bộ dữ liệu benchmark**: `eval/datasets/copilot_benchmark.json` (50 cases: 30 `on_topic`, 15 `negative`, 5 `edge`)
- **Corpus đối chiếu**: `data/knowledge/corpus.json` (359 chunks, SHA-256: `752da79756877a287d5e994112fc3e8df2eba3f6fb68b6dea0dffe61d93f2b52`)
- **File kết quả đi kèm trong repo**:
  - Tổng hợp metrics & chẩn đoán: [`copilot_benchmark_live_2026-10-18_summary.json`](./copilot_benchmark_live_2026-10-18_summary.json)
  - Chi tiết chấm điểm LLM Judge + Ragas (50 cases): [`copilot_benchmark_live_2026-10-18_reviews.json`](./copilot_benchmark_live_2026-10-18_reviews.json)
  - Kết quả phản hồi, trích dẫn & độ trễ của Agent (50 cases): [`copilot_benchmark_live_2026-10-18_results.json`](./copilot_benchmark_live_2026-10-18_results.json)
- **LangSmith Experiment**: `copilot-benchmark-20261018` (`trace_complete = 50/50`, `feedback_readback = 404/404`)
  - URL: https://smith.langchain.com/o/17ac782e-c0ef-405a-ab35-6cdb0997d6cc/projects/p/22725387-4382-4216-8689-5d8c48525129

---

## 1. Tổng quan Kết quả Benchmark (`copilot-benchmark-20261018`)

| Hạng mục | Kết quả | Chi tiết |
|---|---|---|
| **Tổng số case Pass** | **44 / 50 (88.0%)** | `valid: 50/50`, `outcomes: 50/50`, `request_error_rate: 0%` |
| **Nhóm `negative`** | **15 / 15 (100.0%)** | `off_topic` (4/4), `prompt_injection` (5/5), `unsupported_domain` (6/6) |
| **Nhóm `edge`** | **4 / 5 (80.0%)** | Pass 4/4 case cập nhật (`EDGE_001`–`EDGE_004`), Fail `EDGE_005` |
| **Nhóm `on_topic`** | **25 / 30 (83.3%)** | Pass `battery_policy` (3/3), `multi_document` (3/3), `vinclub` (2/2), `product_fact` (11/12), `version_*` (4/4), `deposit` (1/1), `sales_contract` (1/1) |

### Điểm số Metrics (LLM Judge `deepseek/deepseek-v3.2` + Ragas)

| Metric | Điểm trung bình (Mean) | Mẫu số (Denominator) | N/A hoặc Error | Ngưỡng Gate | Trạng thái |
|---|---:|---:|---:|---:|---|
| `custom.relevance` | **0.980** | 50 | 0 | - | Tốt |
| `custom.scope_unit_date_conditions` | **0.950** | 50 | 0 | - | Tốt |
| `custom.fact_correctness` | **0.910** | 50 | 0 | - | Tốt |
| `custom.goal_completeness` | **0.900** | 50 | 0 | $\ge 0.90$ | **PASS** |
| `ragas.faithfulness` | **0.919** | 32 | 18 | $\ge 0.95$ | Chưa đạt ngưỡng 0.95 |
| `custom.citation_support` | **0.838** | 37 | 13 | $\ge 0.95$ | Chưa đạt ngưỡng 0.95 |
| `ragas.context_recall` | **0.773** | 35 | 15 | - | - |

---

## 2. Kết quả từng Case (50/50 Cases)

| Case | Audit | Outcome | Diagnosis |
|---|---|---|---|
| ON_001 | valid | pass | correct |
| ON_002 | valid | pass | correct |
| ON_003 | valid | pass | correct |
| ON_004 | valid | pass | correct |
| ON_005 | valid | pass | correct |
| ON_006 | valid | fail | checker_false_rejection |
| ON_007 | valid | pass | correct |
| ON_008 | valid | pass | correct |
| ON_009 | valid | pass | correct |
| ON_010 | valid | pass | correct |
| ON_011 | valid | pass | correct |
| ON_012 | valid | pass | correct |
| ON_013 | valid | pass | correct |
| ON_014 | valid | pass | correct |
| ON_015 | valid | fail | generation_omission |
| ON_016 | valid | pass | correct |
| ON_017 | valid | fail | technical_error |
| ON_018 | valid | fail | generation_omission |
| ON_019 | valid | fail | technical_error |
| ON_020 | valid | pass | correct |
| ON_021 | valid | pass | correct |
| ON_022 | valid | pass | correct |
| ON_023 | valid | pass | correct |
| ON_024 | valid | pass | correct |
| ON_025 | valid | pass | correct |
| ON_026 | valid | pass | correct |
| ON_027 | valid | pass | correct |
| ON_028 | valid | pass | correct |
| ON_029 | valid | pass | correct |
| ON_030 | valid | pass | correct |
| NEG_001 | valid | pass | correct |
| NEG_002 | valid | pass | corpus_missing |
| NEG_003 | valid | pass | correct |
| NEG_004 | valid | pass | corpus_missing |
| NEG_005 | valid | pass | corpus_missing |
| NEG_006 | valid | pass | missing_input |
| NEG_007 | valid | pass | correct |
| NEG_008 | valid | pass | correct |
| NEG_009 | valid | pass | correct |
| NEG_010 | valid | pass | correct |
| NEG_011 | valid | pass | correct |
| NEG_012 | valid | pass | correct |
| NEG_013 | valid | pass | correct |
| NEG_014 | valid | pass | correct |
| NEG_015 | valid | pass | correct |
| EDGE_001 | valid | pass | correct |
| EDGE_002 | valid | pass | correct |
| EDGE_003 | valid | pass | correct |
| EDGE_004 | valid | pass | correct |
| EDGE_005 | valid | fail | eligibility_failure |

---


## 3. Thông số Vận hành & Hiệu năng (Operational Measurements)

### 3.1. Tổng quan Độ tin cậy, Phục hồi lỗi & Tài nguyên (50 Cases)

| Chỉ số vận hành | Giá trị | Tỷ lệ / Chi tiết |
|---|---:|---|
| **Tổng số request đánh giá (`requests`)** | **50** | Hoàn tất 50/50 case |
| **Tỷ lệ lỗi request (`request_error_rate`)** | **0 / 50** | **0.0%** (Không có lỗi hệ thống) |
| **Tỷ lệ timeout request (`request_timeout_rate`)** | **0 / 50** | **0.0%** |
| **Tổng số lượt gọi LLM (`attempts`)** | **154** | Trung bình ~3.08 lần gọi LLM / case |
| **Tỷ lệ lỗi từ Provider (`provider_error_attempt_rate`)** | **0 / 154** | **0.0%** (`provider_retries = 0`) |
| **Tỷ lệ timeout gọi LLM (`llm_timeout_attempt_rate`)** | **0 / 154** | **0.0%** |
| **Tỷ lệ lỗi Schema/Contract ở lượt sinh (`schema_contract_error_attempt_rate`)** | **9 / 154** | **5.84%** (`ValueError: 4`, `quote_not_found: 3`, `json_invalid: 1`, `incomplete_evidence: 1`) |
| **Request tự phục hồi sau lỗi lượt đầu (`requests_with_recovered_attempt_errors`)** | **6 / 50** | **12.0%** (Trong đó **4 / 6 = 66.7%** sinh được câu trả lời hữu ích sau retry) |
| **Tỷ lệ rơi vào Technical Fallback (`technical_fallback_rate`)** | **3 / 50** | **6.0%** |
| **Phân bổ trạng thái phản hồi (`quality_statuses`)** | **50** | `answered`: **27** (54%) · `partial`: **7** (14%) · `abstained`: **14** (28%) · `needs_clarification`: **2** (4%) |
| **Bộ nhớ RAM đỉnh (`peak_rss_bytes`)** | **~186.1 MB** | `195,162,112 bytes` (Quan sát đủ 50/50 requests) |

### 3.2. Độ trễ Toàn luồng & Theo từng Node trong Graph (Đơn vị: giây)

| Giai đoạn / Node | Số lần chạy (`count`) | Trung bình (`mean`) | Trung vị (`p50`) | `p95` | `p99` | Tối đa (`max`) |
|---|---:|---:|---:|---:|---:|---:|
| **Toàn luồng End-to-End (`latency_seconds`)** | **50** | **19.79s** | **17.74s** | **41.02s** | **47.15s** | **49.58s** |
| `1. analyze_and_route` | 50 | 4.76s | 4.33s | 8.56s | 10.33s | 10.97s |
| `2. plan_queries` *(khi cần lập kế hoạch truy vấn)* | 18 | 4.47s | 4.11s | 7.08s | 7.53s | 7.64s |
| `3. retrieve_documents` *(Hybrid Dense + BM25)* | 49 | 3.96s | 3.67s | 5.42s | 5.96s | 5.99s |
| `4. select_evidence` *(Tổng thời gian node Jev)* | 52 | 1.78s | 1.55s | 2.94s | 3.31s | 3.66s |
| `   ↳ Mỗi quyết định Jev đơn lẻ (jev_decision_latency)` | 455 | 1.14s | 1.13s | 2.25s | 2.73s | 3.44s |
| `5. build_context` | 50 | 0.0003s | 0.00s | 0.00s | 0.008s | 0.016s |
| `6. generate_answer` | 43 | 2.62s | 2.25s | 4.33s | 5.18s | 5.63s |
| `7. check_grounding` | 47 | 5.30s | 4.81s | 9.64s | 13.85s | 14.34s |
| `8. finalize_response` | 34 | 0.0004s | 0.00s | 0.00s | 0.010s | 0.015s |
| `9. fallback_response` | 16 | 0.00s | 0.00s | 0.00s | 0.00s | 0.00s |

### 3.3. Thống kê Token, Chi phí & Bộ lọc Bằng chứng Jev (`select_evidence`)

| Thành phần | Sự kiện (`events`) | Input Tokens | Output Tokens | Tổng Tokens | Ghi chú / Chi tiết |
|---|---:|---:|---:|---:|---|
| **Copilot Main Agent (`tokens.agent`)** | 154 | 343,634 | 65,311 | **408,945** | Trung bình ~8,179 tokens / case (`complete: true`) |
| **Jev Evidence Selector (`tokens.jev`)** | 569 | 806,720 | 62,003 | **868,723** | Chi phí Jev ghi nhận: **\$0.0339 USD** / 455 uncached events |
| **Tổng cộng toàn bộ đợt chạy** | **723** | **1,150,354** | **127,314** | **1,277,668** | `jev_decisions = 569` (`jev_evidence: 76`, `jev_irrelevant: 489`, `jev_no_evidence: 4`, `timeout/error: 0%`) |

### 3.4. Dữ liệu JSON Chi tiết (Raw Operational Measurements)

```json
{
  "requests": 50,
  "request_error_rate": {
    "numerator": 0,
    "denominator": 50,
    "value": 0.0
  },
  "latency_seconds": {
    "count": 50,
    "mean": 19.78942000000039,
    "p50": 17.74199999999837,
    "p95": 41.02325000000418,
    "p99": 47.15103000000438,
    "max": 49.578000000008615
  },
  "provider_error_attempt_rate": {
    "numerator": 0,
    "denominator": 154,
    "value": 0.0
  },
  "llm_timeout_attempt_rate": {
    "numerator": 0,
    "denominator": 154,
    "value": 0.0
  },
  "request_timeout_rate": {
    "numerator": 0,
    "denominator": 50,
    "value": 0.0
  },
  "schema_contract_error_attempt_rate": {
    "numerator": 9,
    "denominator": 154,
    "value": 0.05844155844155844
  },
  "requests_with_recovered_attempt_errors": {
    "numerator": 6,
    "denominator": 50,
    "value": 0.12
  },
  "completed_useful_response_after_attempt_error": {
    "numerator": 4,
    "denominator": 6,
    "value": 0.6666666666666666
  },
  "technical_fallback_rate": {
    "numerator": 3,
    "denominator": 50,
    "value": 0.06
  },
  "attempts": 154,
  "attempt_errors": {
    "answered_requirement_cannot_have_incomplete_evidence": 1,
    "json_invalid": 1,
    "ValueError": 4,
    "evidence_quote_not_found_in_cited_source": 3
  },
  "jev_decisions": 569,
  "jev_unscored": 0,
  "jev_reasons": {
    "jev_evidence": 76,
    "jev_irrelevant": 489,
    "jev_no_evidence": 4
  },
  "jev_decision_latency_seconds": {
    "count": 455,
    "mean": 1.1437186813192406,
    "p50": 1.125,
    "p95": 2.254499999995459,
    "p99": 2.7258999999891964,
    "max": 3.437000000005355
  },
  "tokens": {
    "agent": {
      "input_tokens": {
        "known_total": 343634,
        "known_events": 154,
        "events": 154,
        "complete": true
      },
      "output_tokens": {
        "known_total": 65311,
        "known_events": 154,
        "events": 154,
        "complete": true
      }
    },
    "jev": {
      "input_tokens": {
        "known_total": 806720,
        "known_events": 569,
        "events": 569,
        "complete": true
      },
      "output_tokens": {
        "known_total": 62003,
        "known_events": 569,
        "events": 569,
        "complete": true
      }
    }
  },
  "peak_rss_bytes": 195162112,
  "node_latency_seconds": {
    "analyze_and_route": {
      "count": 50,
      "mean": 4.761859999996959,
      "p50": 4.327999999994063,
      "p95": 8.559149999990762
    },
    "retrieve_documents": {
      "count": 49,
      "mean": 3.961795918369661,
      "p50": 3.672000000020489,
      "p95": 5.419000000000227
    },
    "select_evidence": {
      "count": 52,
      "mean": 1.7790576923099042,
      "p50": 1.5540000000037253,
      "p95": 2.942700000008335
    },
    "generate_answer": {
      "count": 43,
      "mean": 2.615186046509798,
      "p50": 2.25,
      "p95": 4.332399999996414
    },
    "check_grounding": {
      "count": 47,
      "mean": 5.296553191491105,
      "p50": 4.812999999994645,
      "p95": 9.643499999993944
    },
    "plan_queries": {
      "count": 18,
      "mean": 4.473944444447018,
      "p50": 4.10899999999674,
      "p95": 7.0823999999949585
    }
  },
  "quality_statuses": {
    "answered": 27,
    "partial": 7,
    "abstained": 14,
    "needs_clarification": 2
  }
}
```
