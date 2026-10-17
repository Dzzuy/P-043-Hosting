# Weekly Journal — Nhóm dự án

> Ghi lại mỗi tuần: học được gì, khó khăn gì, quyết định gì, kế hoạch tiếp.

## Thành viên


| Họ và tên         | Mã sinh viên |
| ----------------- | ------------ |
| Phạm Đình Duy     | 2A202602913  |
| Phạm Quốc Đạt     | 2A202602384  |
| Võ Trường An      | 2A20262656   |
| Nguyễn Hữu Chương | 2A202602601  |


---

> Tổng hợp hồi cứu theo tuần ISO từ ngày commit của thành viên (19/09–17/10/2026), không tính commit khởi tạo của bot. Mục tiêu được diễn đạt từ phạm vi commit, không phải kế hoạch đã được nhóm xác nhận trước tuần; “hoàn thành” nghĩa là đã commit, không tự khẳng định kiểm thử đạt.

## Tuần 1 — 2026-W38: 2026-09-14 - 2026-09-20

### Mục tiêu tuần này

- Cập nhật thông tin nhóm, vai trò và tài liệu bàn giao Gate 1.

### Đã hoàn thành

- 2026-09-19 — Phạm Đình Duy: Cập nhật vai trò Duy và ghi log thử nghiệm.
- 2026-09-20 — Phạm Đình Duy: Bổ sung tài liệu bàn giao Gate 1 và thông tin nhóm.

### Khó khăn & Giải pháp


| Khó khăn                                               | Giải pháp                       | Kết quả                      |
| ------------------------------------------------------ | ------------------------------- | ---------------------------- |
| TODO (team): Bổ sung khó khăn có bằng chứng trong tuần | TODO (team): Bổ sung cách xử lý | TODO (team): Bổ sung kết quả |


### Bài học

- TODO (team): Bổ sung bài học thực tế của tuần; thông điệp commit chưa đủ bằng chứng.

### Kế hoạch tuần sau

- TODO (team): Xác nhận kế hoạch tuần sau; không suy diễn kế hoạch từ commit đã xảy ra.

---

## Tuần 2 — 2026-W39: 2026-09-21 - 2026-09-27

### Mục tiêu tuần này

- Phân công theo roadmap; chốt hợp đồng dữ liệu, schema, rubric và trạng thái khách hàng; điều chỉnh package backend.

### Đã hoàn thành

- 2026-09-21 — Phạm Đình Duy: Lập phân công công việc và cập nhật ROADMAP.
- 2026-09-22 — Phạm Quốc Đạt: Chốt hợp đồng dữ liệu Gate 1, corpus mẫu, rubric và schema kịch bản.
- 2026-09-22 — Phạm Đình Duy: Chốt trạng thái khách hàng, hợp đồng tích hợp roleplay; tích hợp nhánh hợp đồng dữ liệu.
- 2026-09-23 — Phạm Đình Duy: Điều chỉnh đường dẫn package backend theo roadmap.

### Khó khăn & Giải pháp


| Khó khăn                                               | Giải pháp                       | Kết quả                      |
| ------------------------------------------------------ | ------------------------------- | ---------------------------- |
| TODO (team): Bổ sung khó khăn có bằng chứng trong tuần | TODO (team): Bổ sung cách xử lý | TODO (team): Bổ sung kết quả |


### Bài học

- TODO (team): Bổ sung bài học thực tế của tuần; thông điệp commit chưa đủ bằng chứng.

### Kế hoạch tuần sau

- TODO (team): Xác nhận kế hoạch tuần sau; không suy diễn kế hoạch từ commit đã xảy ra.

---

## Tuần 3 — 2026-W40: 2026-09-28 - 2026-10-04

### Mục tiêu tuần này

- Xây dựng và tích hợp Copilot/Practice MVP, corpus/evaluation, auth/lịch sử/review, frontend thật, CI và tài liệu Gate 2.

### Đã hoàn thành

- 2026-09-28 — Nguyễn Hữu Chương: Xây dựng baseline Copilot agent.
- 2026-09-28 — Phạm Đình Duy: Xây dựng roleplay LangGraph, trạng thái lượt, ranh giới AI khách hàng, API kịch bản/chat và lưu/tải/kết thúc phiên; kiểm chứng nguồn đánh giá, metadata và hợp đồng; tích hợp PR #1, #2, cập nhật phạm vi MVP/roadmap.
- 2026-09-29 — Phạm Đình Duy: Ghi nhận trạng thái kiểm chứng roleplay.
- 2026-09-30 — Phạm Đình Duy: Thiết lập CI kiểm tra pull request vào develop.
- 2026-10-01 — Nguyễn Hữu Chương: Ingestion dữ liệu và tích hợp PR #4 baseline Copilot.
- 2026-10-01 — Phạm Quốc Đạt: Xây dựng corpus thực, tách FAQ; bổ sung benchmark Gate 3 và eval runner.
- 2026-10-01 — Phạm Đình Duy: Chuyển runtime roleplay vào src, tích hợp API/LLM/checkpoint và grounding; sửa routing async, đường dẫn kịch bản, dependency ingestion và kiểm chứng factual claim; đồng bộ develop và tài liệu kiến trúc.
- 2026-10-02 — Nguyễn Hữu Chương: Xây dựng baseline Copilot agent.
- 2026-10-02 — Phạm Đình Duy: Kết nối frontend với API thật, OpenRouter và embeddings; bổ sung evidence theo mẫu xe, retry judge sai định dạng, sửa giá/range/provider/Docker; tích hợp frontend và ghi nhận smoke MVP.
- 2026-10-02 — Võ Trường An: Bổ sung frontend, dữ liệu, script khởi động và bản dist.
- 2026-10-03 — Phạm Đình Duy: Tích hợp PR #6–#11 và Practice MVP; thêm cookie auth, phiên người dùng, lịch sử/review có phân quyền và test ownership; cải thiện grounding/suggestions, xử lý lỗi provider và nguồn cũ, CI/OpenRouter và AI log.
- 2026-10-04 — Phạm Đình Duy: Tích hợp PR #12–#15; thêm lịch sử/team overview, rubric ba mức, giới hạn lượt và retry chấm điểm; sửa evidence/quotes, factual coverage, tiếng Việt và retry phản hồi; tích hợp login/review UI, bổ sung dữ liệu phí sạc và tài liệu Gate 2.
- 2026-10-04 — Võ Trường An: Bổ sung frontend và dữ liệu trợ lý VinFast.

### Khó khăn & Giải pháp


| Khó khăn                                                                                       | Giải pháp                                                                   | Kết quả                                                               |
| ---------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Judge trả phản hồi sai định dạng; có lỗi evidence/quotes và factual coverage (commit 02–04/10) | Retry một phản hồi sai định dạng; bổ sung sửa/kiểm chứng evidence và quotes | Các thay đổi xử lý đã commit                                          |
| CI bị chặn bởi billing (thông điệp merge PR #6 ngày 03/10)                                     | Đính kèm kết quả local theo thông điệp merge                                | PR #6 đã tích hợp; TODO (team): xác nhận trạng thái billing/CI sau đó |


### Bài học

- Phản hồi judge cần được kiểm chứng định dạng và evidence/quotes; lỗi provider cần hiển thị để retry (các commit sửa ngày 02–04/10).

### Kế hoạch tuần sau

- TODO (team): Xác nhận kế hoạch tuần sau; không suy diễn kế hoạch từ commit đã xảy ra.

---

## Tuần 4 — 2026-W41: 2026-10-05 - 2026-10-11

### Mục tiêu tuần này

- Bổ sung benchmark Gate 3/4, Docker/PostgreSQL/Neon, voice mode và assignments/team performance; tích hợp frontend và develop.

### Đã hoàn thành

- 2026-10-05 — Phạm Quốc Đạt: Bổ sung ground truth benchmark Copilot Gate 3.
- 2026-10-07 — Phạm Đình Duy: Đồng bộ main vào develop và tích hợp PR #16.
- 2026-10-09 — Phạm Đình Duy: Tích hợp PR #17, #18; triển khai Docker/PostgreSQL pgvector và Neon, tạo tài khoản advisor qua manager; thêm API giọng nói bảo vệ quyền, thống kê usage, push-to-talk/playback và xử lý lỗi; cập nhật tài liệu triển khai và evidence showcase.
- 2026-10-10 — Phạm Đình Duy: Tích hợp PR #19, #20 và frontend An với develop; dọn assets/bundle trùng, ghi nhận khoảng trống backend và dữ liệu demo thực.
- 2026-10-11 — Phạm Quốc Đạt: Tích hợp deliverables Gate 4 và evidence benchmark live T3/T4.
- 2026-10-11 — Phạm Đình Duy: Tích hợp PR #21, đồng bộ develop/Neon/voice; lưu assignments và ranking được duyệt, kết nối luyện tập được giao/team performance, hiển thị voice usage ở review manager.

### Khó khăn & Giải pháp


| Khó khăn                                            | Giải pháp                                         | Kết quả                           |
| --------------------------------------------------- | ------------------------------------------------- | --------------------------------- |
| Lỗi voice API cần thông báo đọc được (commit 09/10) | Bổ sung hiển thị lỗi và tài liệu hành vi thất bại | Thay đổi UI và tài liệu đã commit |


### Bài học

- Luồng giọng nói cần xử lý và giải thích lỗi API cho người dùng (commit 09/10).

### Kế hoạch tuần sau

- TODO (team): Xác nhận kế hoạch tuần sau; không suy diễn kế hoạch từ commit đã xảy ra.

---

## Tuần 5 — 2026-W42: 2026-10-12 - 2026-10-18

### Mục tiêu tuần này

- Cập nhật UI/hosting/Copilot, hội thoại giọng nói, injection hardening, phục hồi attempt và scenario 04 với outcome/upsell/policy/judge riêng.

### Đã hoàn thành

- 2026-10-12 — Võ Trường An: Cập nhật giao diện frontend, cấu hình triển khai và UI manager.
- 2026-10-13 — Phạm Đình Duy: Tích hợp PR #22–#28; đồng bộ hosting/voice/login và AI-Sale UI; làm mới navigation, Copilot, knowledge, practice; khôi phục attempt khi finish lỗi, lưu completion trước evaluation; probe injection đa ngôn ngữ, chặn output riêng tư/ngoại ngữ; bảo vệ demo production và điều chỉnh startup.
- 2026-10-13 — Võ Trường An: Cập nhật giao diện frontend.
- 2026-10-14 — Nguyễn Hữu Chương: Hoàn thiện Copilot agent theo module, insights ngắn gọn, PostgreSQL và bộ test; đồng bộ develop và sửa UI.
- 2026-10-14 — Phạm Đình Duy: Tích hợp PR #30; thêm điều khiển hội thoại giọng nói, lựa chọn voice khách hàng và tài liệu workflow.
- 2026-10-15 — Phạm Đình Duy: Khôi phục ngân sách demo VF5 và đồng bộ preset ngân sách frontend.
- 2026-10-16 — Phạm Đình Duy: Tích hợp PR #32 và các phần scenario 04; mở rộng contract outcome/upsell/policy, thêm VF 6 Eco/Plus, judge riêng, seed transcript/smoke; guardrail abuse, misconduct termination và UI outcome; sửa false positive, retrieval/routing, retry policy, persona và discovery.
- 2026-10-17 — Phạm Đình Duy: Sửa eligibility ưu đãi và lỗi practice với mã ổn định/tiếng Việt; thêm notice hướng dẫn; điều chỉnh push-to-talk, auto-send và giới hạn ghi âm 90 giây; giữ draft khi gửi lỗi, xử lý lỗi playback.
- 2026-10-17 — Phạm Đình Duy: Chính sách kịch bản lấy từ corpus theo ngày phiên (topic + lookup, judge dùng `current_policy_evidence`), script kiểm tra độ phủ tri thức; nhãn JC6 do AI chấm nháp và Tú (tư vấn viên bán hàng VinFast) duyệt; tích hợp PR #33.

### Khó khăn & Giải pháp


| Khó khăn                                                                                                     | Giải pháp                                                                                         | Kết quả               |
| ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- | --------------------- |
| Finish thất bại, draft gửi lỗi; guardrail false positive và eligibility cần điều chỉnh (commit 13, 16–17/10) | Lưu completion trước evaluation, mở lại attempt, giữ draft; sửa guardrail và xác nhận eligibility | Các bản sửa đã commit |
| Ngân sách demo VF5 cần khôi phục (commit 15/10)                                                              | Restore ngân sách và đồng bộ preset frontend                                                      | Hai bản sửa đã commit |


### Bài học

- Cần bảo toàn attempt/draft khi thao tác thất bại và kiểm tra guardrail với hội thoại bán hàng thông thường (commit 13, 16–17/10).

### Kế hoạch tuần sau

- Hạn nộp dự án là 18/10/2026.
- TODO (team): ảnh chụp màn hình README, video demo, slide.

---

<!-- Tiếp tục copy block trên cho Week 3, 4, 5, 6 -->
