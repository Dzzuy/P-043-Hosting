# P-043 — Sơ đồ kiến trúc hiện tại

```mermaid
flowchart LR
  A[Advisor browser] --> UI[React / Vite]
  M[Manager browser] --> UI
  UI -->|REST + session cookie| API[FastAPI]
  API --> AUTH[Auth service]
  AUTH --> SQL[(SQL: users / sessions)]
  API --> CP[Copilot LangGraph]
  CP --> RET[Hybrid retrieval + evidence gate]
  RET --> CH[(Vector index: pgvector or Chroma)]
  RET --> CORPUS[Corpus JSON + metadata]
  CP --> CHAT[OpenRouter chat model]
  API --> RP[Practice / Role-play LangGraph]
  MIC[Advisor microphone] -->|recording| UI
  API -->|server-side transcription| STT[Groq Whisper Turbo]
  STT -->|Vietnamese text| API
  API -->|saved customer text| TTS[Google WaveNet]
  TTS -->|MP3 playback| API
  API --> USAGE[(SQL: voice usage by session)]
  RP --> GUARD[Guardrail cục bộ + analyzer flag]
  GUARD -->|advisor_misconduct| RECORDS
  RP --> CUSTOMER[AI Customer + turn analysis]
  CUSTOMER --> CHAT
  RP --> JUDGE[Rubric evaluator + evidence checks]
  JUDGE --> JMODEL[OpenRouter judge riêng]
  JUDGE --> RET
  RP --> RECORDS[(SQL: attempts / transcript / scores / review)]
  API --> REVIEW[Manager review API]
  REVIEW --> RECORDS
  EMB[OpenRouter embedding model] --> CH
  CORPUS -->|ingest on empty index| EMB
```

## Luồng và quyền

1. `POST /api/v1/auth/login` đặt HTTP-only cookie. Practice giới hạn Advisor; review giới hạn Manager. Copilot trên nhánh hiện tại yêu cầu Advisor qua `current_copilot_user`; danh mục scenario cho cả Advisor/Manager. Xem [router Copilot](../src/api/copilot.py) và [router Practice/manager](../src/api/recorded_practice.py).
2. Copilot nhận `/api/v1/copilot/query`, tìm evidence từ corpus/vector index và lexical retrieval, lọc theo metadata, tạo câu trả lời trích nguồn hoặc abstain/lỗi. `/api/v1/copilot/sources/{document_id}` mở tài liệu gốc.
3. Advisor chọn [scenario JSON](../data/scenarios/scenarios.json) → tạo state/checkpoint → **Advisor mở lời trước** → guardrail cục bộ → turn analyzer → cập nhật/lưu state → AI Customer → lưu transcript → frontend. Guardrail trong [guardrails.py](../src/agents/roleplay/guardrails.py) và cờ `unsafe_or_abusive` của analyzer là hai lớp phát hiện; khi vi phạm, kết thúc bằng `advisor_misconduct`.
4. Kết thúc phiên → [evaluator chung](../src/agents/roleplay/evaluator.py) nhận transcript + state + scenario + knowledge evidence → judge riêng → validate quote/message ID/nguồn → AI draft trong SQL. `sales-rubric-v4` có 5 tiêu chí (nhu cầu, sản phẩm, phản đối, chính sách, chốt); cấu hình `policy_expectations` nằm trong từng scenario. Judge dùng `PRACTICE_JUDGE_PROVIDER` / `PRACTICE_JUDGE_MODEL` (mặc định OpenRouter / `google/gemini-3.8-flash`, temperature 0), tách khỏi generator `OPENROUTER_MODEL_NAME`.
5. SQL lưu ownership, transcript, AI draft và review. Advisor chỉ đọc lịch sử của mình. Manager xem hàng đợi/lịch sử, sửa điểm kèm lý do và duyệt; Advisor xem kết quả đã duyệt.

## Kịch bản và giọng nói

Bốn kịch bản: `SCENARIO_01_VF5_TAXI`, `SCENARIO_02_VF7_VS_CX5`, `SCENARIO_03_VF6_APARTMENT`, `SCENARIO_04_VF6_ECO_PLUS_UPSELL`. Kịch bản 04 cho phép `close_eco` và `upsell_plus`; upsell là ưu tiên, không phải điều kiện bắt buộc của mọi phiên.

Micro → push-to-talk tối đa 90 giây → FastAPI → Groq Whisper → bản chép. Công tắc **Tự động gửi** chọn gửi ngay hoặc sửa trước khi gửi. Văn bản Customer → Google WaveNet → phát audio; [voice service](../src/services/voice.py) và SQL usage ở server. [Mã lỗi Practice](../src/api/practice_errors.py) có thông báo tiếng Việt; frontend dùng [notice dialog](../frontend/src/components/common/NoticeDialog.jsx) và [ánh xạ lỗi](../frontend/src/utils/practiceNotices.js) để đưa ra hành động phù hợp.

## Ranh giới MVP

`data/knowledge/corpus.json` là nguồn nội dung demo được kiểm soát; vector index chỉ là dữ liệu dẫn xuất. Docker Compose dùng PostgreSQL + pgvector trong volume riêng của từng máy. Chạy Python trực tiếp vẫn mặc định SQLite + Chroma. Muốn chia sẻ lịch sử cần một backend và database hosted dùng chung. `/health` chỉ đo liveness, không xác nhận provider. Scenario/khách hàng là dữ liệu giả lập; không đưa PII thật vào log, báo cáo hay video.

## Triển khai và tham chiếu

Docker Compose: browser → Caddy/React → FastAPI → PostgreSQL + pgvector với volume local. Chạy trực tiếp dùng SQLite + Chroma mặc định. Mô hình hosted trong [deployment](deployment.md) là Vercel → Render → Neon; tài liệu này mô tả code hiện tại, không xác nhận các thay đổi chưa merge đã chạy live. [CI](../.github/workflows/ci.yml) hiện chạy Ruff và pytest backend. Chi tiết thành phần ở [ARCHITECTURE.md](../ARCHITECTURE.md); hướng dẫn chạy và Live URL ở [README.md](../README.md).
