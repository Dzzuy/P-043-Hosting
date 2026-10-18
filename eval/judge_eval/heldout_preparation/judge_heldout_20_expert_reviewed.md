# judge_heldout_20_expert_reviewed

> **Phiếu đánh giá độc lập theo hồ sơ được cung cấp.** Mã reviewer: **CG**. Ngày đánh giá: **2026-10-17** (Asia/Bangkok).

## Quy tắc chấm và phạm vi

- **Nguồn duy nhất:** `judge_heldout_20_review_packet.md`, `rubric_specification.md` (`sales-rubric-v3`), `corpus_v3_1.json`, `faq.json`. Dữ liệu giá/chính sách lấy theo phiên bản có trong hai tệp KB, không tra cứu web/AI Judge.
- **Mức điểm:** `1` = bỏ lỡ/sai/rủi ro; `2` = phù hợp chuyên nghiệp; `3` = điều chỉnh theo bối cảnh của khách. `ASSESSED` có điểm nguyên 1–3; `UNASSESSED` có `null` và lý do, không dùng để che hành vi bỏ lỡ.
- **Tách chiều:** Bỏ qua câu hỏi trực tiếp về giá/trang bị/sạc được tính vào Product Knowledge/Objection Handling. Nếu advisor không có claim chính sách nào và không đủ cơ hội kiểm chứng điều khoản thì Policy Accuracy `UNASSESSED`. Trường hợp advisor tự cam kết quyền lợi hoặc điều kiện không có căn cứ thì Policy Accuracy được chấm `1`, kể cả chưa có bằng chứng khẳng định phát biểu sai về thực tế.
- **Đối chiếu:** Chỉ coi `SUPPORTED`/`CONTRADICTED` khi có căn cứ từ nguồn được cung cấp; `UNVERIFIABLE` không đồng nghĩa sai về sự thật. Không coi giả định 50 triệu chênh lệch VF 7/CX-5 là thông tin được xác thực vì không có bảng giá/thông số CX-5 trong KB. Không suy đoán trụ sạc trống hoặc vị trí trạm theo thời gian thực.
- **Xác nhận độc lập:** 20/20 phiếu được lập từ transcript và rubric khi **không có, không đọc, không tham khảo điểm AI Judge**; chưa có biên bản chuyên gia người thật phê duyệt hay adjudication. Tham chiếu nhãn gốc: **không được cung cấp**. `passed: null` cho mọi ca theo rubric.

## Bảng tổng hợp

| Mã ca | Need Discovery | Product Knowledge | Objection Handling | Policy Accuracy | Closing / Next Step | Coverage | Điểm TB* |
|---|---:|---:|---:|---:|---:|---:|---:|
| JH26_01_VF5_01 | 3 | 1 | 2 | null | 3 | 4/5 | 2.25 |
| JH26_02_VF5_02 | 1 | 1 | 1 | null | 1 | 4/5 | 1.00 |
| JH26_03_VF5_03 | 3 | 2 | 2 | 2 | 3 | 5/5 | 2.40 |
| JH26_04_VF5_04 | 2 | 2 | 1 | 2 | null | 4/5 | 1.75 |
| JH26_05_VF5_05 | 1 | 1 | 1 | 1 | 1 | 5/5 | 1.00 |
| JH26_06_VF5_06 | 2 | 1 | 1 | 2 | 1 | 5/5 | 1.40 |
| JH26_07_VF5_07 | 1 | 1 | 1 | null | 1 | 4/5 | 1.00 |
| JH26_08_VF7_08 | 3 | 1 | 1 | null | 3 | 4/5 | 2.00 |
| JH26_09_VF7_09 | 2 | 2 | 2 | 2 | null | 4/5 | 2.00 |
| JH26_10_VF7_10 | 1 | 1 | 1 | 1 | null | 4/5 | 1.00 |
| JH26_11_VF7_11 | 2 | 2 | 2 | 2 | 1 | 5/5 | 1.80 |
| JH26_12_VF7_12 | 1 | 1 | 1 | null | null | 3/5 | 1.00 |
| JH26_13_VF7_13 | 2 | 1 | 2 | null | 3 | 4/5 | 2.00 |
| JH26_14_VF7_14 | 1 | 1 | 1 | 1 | 1 | 5/5 | 1.00 |
| JH26_15_VF6_15 | 3 | 2 | 2 | null | 3 | 4/5 | 2.50 |
| JH26_16_VF6_16 | 1 | 1 | 1 | null | null | 3/5 | 1.00 |
| JH26_17_VF6_17 | 1 | 1 | 1 | 1 | null | 4/5 | 1.00 |
| JH26_18_VF6_18 | 2 | 2 | 2 | null | 3 | 4/5 | 2.25 |
| JH26_19_VF6_19 | 2 | 2 | 2 | null | 3 | 4/5 | 2.25 |
| JH26_20_VF6_20 | 2 | 1 | 1 | null | 1 | 4/5 | 1.25 |

*Điểm TB = trung bình các tiêu chí `ASSESSED`, không quy đổi phần trăm và không tự xác định `passed`.*

## Phiếu đánh giá chi tiết

---

### JH26_01_VF5_01 — SCENARIO_01_VF5_TAXI (v2.2)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `2.25`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `7c99a9a1-f539-46cf-b3be-0748a69c630a` (customer): “Anh thường chạy khoảng 200 km mỗi ngày, vậy chi phí sạc cho VF 5 Plus sẽ ảnh hưởng như thế nào đến thu nhập của anh?”
- `0d667a3a-b154-4952-a386-d85d9223ad6f` (advisor): “Hiện mỗi tháng anh chi khoảng bao nhiêu tiền xăng cho chiếc Vios? Anh có ghi lại số thực tế không?”
- `8ac35ae9-c78c-463b-82d0-dd1d8c3f9c32` (customer): “Anh có ghi lại chi tiêu mấy tháng gần đây, trung bình tiền xăng Vios khoảng 8,5 triệu một tháng.”
- `6c2a74fa-4ea8-40cc-886c-52c67e6877a8` (advisor): “Anh chạy vào những khung giờ nào, thường nghỉ giữa ca ở đâu và có thể dừng sạc lúc nào?”
- `f0daffe9-f911-4f0a-ab7e-609ca6e6f157` (customer): “Anh hay chạy liền ca trưa, nếu phải dừng sạc lâu thì mất cuốc. Có cách nào sắp lịch sạc hợp lý không em?”
- `4d366cf2-e696-405e-85fe-dcd5a5124410` (advisor): “Em sẽ tách tiền năng lượng, khoản vay và thời gian dừng xe trong bảng so sánh theo số liệu của anh. Anh đồng ý để em gửi bản giả định để mình cùng kiểm tra không ạ?”
- **Lý do:** Hỏi sâu km, xăng Vios, thời gian dừng và ngân sách; cuối cùng chuyển toàn bộ thành bảng phân tích ba chi phí sát ca chạy khách.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `dce71a5b-310c-44b4-be33-54e669c0f0f2` (customer): “Chào em, anh muốn biết VF 5 Plus lăn bánh bao nhiêu và chi phí sạc ra sao. Anh đang chạy Vios dịch vụ, nên cần so sánh chi phí sử dụng giữa hai xe.”
- `fb5e8128-e13b-4c15-a75a-0c08cd1d353f` (customer): “Chi phí sạc cho VF 5 Plus sẽ ảnh hưởng như thế nào đến thu nhập của anh? Anh cần biết rõ để so sánh với tiền xăng hiện tại.”
- `7e699c28-1d81-4e49-8bae-988ffc8a36c3` (advisor): “Về khoản đổi xe, anh dự kiến trả trước bao nhiêu và muốn giới hạn tiền trả góp mỗi tháng ở mức nào?”
- `4d366cf2-e696-405e-85fe-dcd5a5124410` (advisor): “Em sẽ tách tiền năng lượng, khoản vay và thời gian dừng xe trong bảng so sánh theo số liệu của anh. Anh đồng ý để em gửi bản giả định để mình cùng kiểm tra không ạ?”
- **Lý do:** Khách liên tục hỏi chi phí sạc và tác động đến thu nhập, nhưng advisor chưa đưa thông số sạc, đơn giá hoặc công thức tính dù đã biết 200 km/ngày.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`); `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `f0daffe9-f911-4f0a-ab7e-609ca6e6f157` (customer): “Anh hay chạy liền ca trưa, nếu phải dừng sạc lâu thì mất cuốc. Có cách nào sắp lịch sạc hợp lý không em?”
- `4d366cf2-e696-405e-85fe-dcd5a5124410` (advisor): “Em sẽ tách tiền năng lượng, khoản vay và thời gian dừng xe trong bảng so sánh theo số liệu của anh. Anh đồng ý để em gửi bản giả định để mình cùng kiểm tra không ạ?”
- **Lý do:** Nhận diện rủi ro mất cuốc và hứa tách thời gian dừng xe; chưa đưa phương án lịch sạc hoặc kiểm tra lại băn khoăn.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.
- **Nguồn đối chiếu:** `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`).

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `fb5e8128-e13b-4c15-a75a-0c08cd1d353f` (customer): “Chi phí sạc cho VF 5 Plus sẽ ảnh hưởng như thế nào đến thu nhập của anh? Anh cần biết rõ để so sánh với tiền xăng hiện tại.”
- `4d366cf2-e696-405e-85fe-dcd5a5124410` (advisor): “Em sẽ tách tiền năng lượng, khoản vay và thời gian dừng xe trong bảng so sánh theo số liệu của anh. Anh đồng ý để em gửi bản giả định để mình cùng kiểm tra không ạ?”
- **Lý do:** Chưa có phát biểu cụ thể của advisor về mức giá, điều khoản hoặc ưu đãi có thể kiểm chứng; việc chưa trả lời sạc đã bị trừ ở Product Knowledge/Objection Handling.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `8ac35ae9-c78c-463b-82d0-dd1d8c3f9c32` (customer): “Anh có ghi lại chi tiêu mấy tháng gần đây, trung bình tiền xăng Vios khoảng 8,5 triệu một tháng.”
- `f0daffe9-f911-4f0a-ab7e-609ca6e6f157` (customer): “Anh hay chạy liền ca trưa, nếu phải dừng sạc lâu thì mất cuốc. Có cách nào sắp lịch sạc hợp lý không em?”
- `4d366cf2-e696-405e-85fe-dcd5a5124410` (advisor): “Em sẽ tách tiền năng lượng, khoản vay và thời gian dừng xe trong bảng so sánh theo số liệu của anh. Anh đồng ý để em gửi bản giả định để mình cùng kiểm tra không ạ?”
- **Lý do:** Xin phép gửi bảng giả định dựa trên tiền xăng, vay và thời gian mất cuốc, mức cam kết thấp phù hợp khách chưa sẵn sàng chốt.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_02_VF5_02 — SCENARIO_01_VF5_TAXI (v2.2)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `1.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `ce0c9af6-da1e-40dd-b508-f703c6eb7cb7` (customer): “VF 5 Plus lăn bánh khoảng bao nhiêu? Anh đang chạy Vios dịch vụ nên muốn biết chi phí sử dụng và thời gian sạc ảnh hưởng đến thu nhập như thế nào.”
- `3969fcee-d95c-4807-b088-9775f7a57265` (advisor): “VF 5 Plus là dòng xe điện nhìn hiện đại, đi phố rất hợp anh ạ.”
- `64ac4efe-5273-497a-b1a5-3960fa4d6598` (customer): “Em có thể cho anh biết cụ thể chi phí sạc ngoài là bao nhiêu không? Anh cần biết rõ để tính toán xem có hợp lý không.”
- `30af3a3f-3a09-43b4-954e-2f0076b9217b` (advisor): “Em thấy nhiều khách chọn xe này để đi lại; mình bàn chuyện chi phí sau cũng được.”
- **Lý do:** Biết khách chạy Vios dịch vụ và lo tổng chi phí nhưng không hỏi km, khoản xăng hoặc lịch chạy; né câu hỏi bằng giới thiệu kiểu dáng.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `64ac4efe-5273-497a-b1a5-3960fa4d6598` (customer): “Em có thể cho anh biết cụ thể chi phí sạc ngoài là bao nhiêu không? Anh cần biết rõ để tính toán xem có hợp lý không.”
- `30af3a3f-3a09-43b4-954e-2f0076b9217b` (advisor): “Em thấy nhiều khách chọn xe này để đi lại; mình bàn chuyện chi phí sau cũng được.”
- `30c98585-bae3-44e9-80aa-a88a2102f8f8` (customer): “Em có thể cho anh biết cụ thể chi phí sạc ngoài là bao nhiêu không? Anh cần biết rõ để tính toán xem có hợp lý không.”
- `86531e98-9472-4718-ae41-6a1427782330` (advisor): “Anh ghé xem xe trước đi, lúc đó em giới thiệu thêm các tính năng.”
- **Lý do:** Không trả lời câu hỏi lặp lại về đơn giá sạc và phép tính dùng xe, dù có số liệu nguồn cho đơn giá công cộng.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`); `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`); `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `b58eab51-9291-45bc-bed1-f8e90190f1f2` (customer): “Em nghe nói sạc ngoài vẫn tốn tiền, rồi còn trả góp nữa. Chạy nhiều như anh thì đổi từ Vios có đáng không em?”
- `41f715ca-cbf7-4d1c-92d8-fd09f67f881c` (advisor): “Nội thất xe khá gọn và thiết kế cũng trẻ trung, anh có thể xem nhiều màu.”
- `6216c56e-db50-45b5-ad79-531202cf5d90` (customer): “Anh vẫn chưa yên tâm về điểm này. Bây giờ anh phải ghé siêu thị mua ít đồ. Mình tạm dừng ở đây; em gửi thông tin phù hợp với trường hợp của anh sau nhé.”
- **Lý do:** Bỏ qua nỗi lo chi phí sạc và trả góp, chuyển sang màu sắc/nội thất; cuối cùng khách nói vẫn chưa yên tâm.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `41f715ca-cbf7-4d1c-92d8-fd09f67f881c` (advisor): “Nội thất xe khá gọn và thiết kế cũng trẻ trung, anh có thể xem nhiều màu.”
- `30af3a3f-3a09-43b4-954e-2f0076b9217b` (advisor): “Em thấy nhiều khách chọn xe này để đi lại; mình bàn chuyện chi phí sau cũng được.”
- **Lý do:** Advisor không nêu mức giá, điều kiện ưu đãi hay điều khoản nào để thẩm tra tính đúng/sai; câu hỏi về chi phí bị bỏ lỡ đã chấm ở các chiều hành vi.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `86531e98-9472-4718-ae41-6a1427782330` (advisor): “Anh ghé xem xe trước đi, lúc đó em giới thiệu thêm các tính năng.”
- `6216c56e-db50-45b5-ad79-531202cf5d90` (customer): “Anh vẫn chưa yên tâm về điểm này. Bây giờ anh phải ghé siêu thị mua ít đồ. Mình tạm dừng ở đây; em gửi thông tin phù hợp với trường hợp của anh sau nhé.”
- **Lý do:** Mời ghé xem xe trước không phù hợp nhu cầu tính chi phí; khi khách xin dừng và gửi thông tin, advisor chưa đáp lại bằng một lịch/kênh theo dõi.
- **Cần cải thiện để đạt mức cao hơn:** Xin phép khách về một hành động cụ thể theo đúng mức sẵn sàng; nêu kênh, thời điểm hoặc người thực hiện.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_03_VF5_03 — SCENARIO_01_VF5_TAXI (v2.2)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `5/5`. **Overall score:** `2.40`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `5b2269bd-fce5-4708-bb54-35422e0f4ef8` (advisor): “Anh thường chạy mấy km một ngày và có khung giờ nào nghỉ giữa ca không ạ?”
- `0cf4b86f-979c-4b52-b172-43925926f482` (customer): “Anh thường chạy khoảng 200-300 km một ngày, và có khoảng 1-2 giờ nghỉ giữa ca. Anh muốn biết chi phí sạc cho quãng đường đó.”
- `d9490a81-83ae-4f22-82f5-e8d05a7707e3` (advisor): “Nếu phải dừng sạc thì anh lo mất cuốc vào giờ nào nhất?”
- `c7346886-ae02-4fba-99ce-704d6eb0dfb5` (customer): “Anh lo nhất là thời gian dừng sạc có ảnh hưởng đến thu nhập. Nếu phải dừng sạc trong giờ cao điểm thì sẽ mất cuốc, không biết có cách nào tối ưu không?”
- `fce4f46a-44ea-47cc-9240-a068b3467727` (advisor): “Em sẽ so riêng chi phí điện, thời gian dừng và khoản vay; để tính được cần quãng đường cùng chi phí xăng thực tế của anh.”
- `cd86019a-55d2-4136-8af4-e5b0f7590b71` (advisor): “Nếu anh muốn, em gửi bảng so sánh có ghi rõ giả định và cùng anh rà lại lịch chạy vào một cuộc gọi ngắn.”
- **Lý do:** Đào sâu km/ngày và giờ nghỉ, hỏi thời điểm mất cuốc, chuyển thành kịch bản phân tách điện/dừng sạc/khoản vay.

#### 2. Product Knowledge — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `9c1106b2-8d39-433b-921f-ad38b86f3fe8` (customer): “Anh muốn biết chi phí sạc cho quãng đường 200-300 km một ngày và thời gian dừng sạc có ảnh hưởng đến thu nhập như thế nào.”
- `3485e440-71b9-4ebe-a2e6-1ea414810fa5` (advisor): “Thời gian sạc và chi phí còn phụ thuộc trụ, mức pin, chính sách áp dụng. Mình kiểm tra điểm sạc trên tuyến anh hay chạy trước khi kết luận nhé.”
- **Lý do:** Nêu đúng các biến chi phối chi phí và tốc độ sạc, đề nghị xem tuyến trước khi kết luận; chưa trình bày mốc sạc có điều kiện hoặc số liệu điện tham khảo.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`); `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `c7346886-ae02-4fba-99ce-704d6eb0dfb5` (customer): “Anh lo nhất là thời gian dừng sạc có ảnh hưởng đến thu nhập. Nếu phải dừng sạc trong giờ cao điểm thì sẽ mất cuốc, không biết có cách nào tối ưu không?”
- `3485e440-71b9-4ebe-a2e6-1ea414810fa5` (advisor): “Thời gian sạc và chi phí còn phụ thuộc trụ, mức pin, chính sách áp dụng. Mình kiểm tra điểm sạc trên tuyến anh hay chạy trước khi kết luận nhé.”
- `f013bd33-0e89-43aa-8647-44d0f6d29f4a` (customer): “Anh nghe nói sạc ngoài lượt được ưu đãi vẫn tốn tiền, rồi còn trả góp nữa. Chạy nhiều như anh thì đổi từ Vios có đáng không em?”
- `cd86019a-55d2-4136-8af4-e5b0f7590b71` (advisor): “Nếu anh muốn, em gửi bảng so sánh có ghi rõ giả định và cùng anh rà lại lịch chạy vào một cuộc gọi ngắn.”
- **Lý do:** Không phủ nhận lo lắng, hướng tới kiểm tra điểm sạc và bảng so sánh; chưa giải đáp cụ thể việc mất cuốc và hỏi khách đã yên tâm chưa.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `3485e440-71b9-4ebe-a2e6-1ea414810fa5` (advisor): “Thời gian sạc và chi phí còn phụ thuộc trụ, mức pin, chính sách áp dụng. Mình kiểm tra điểm sạc trên tuyến anh hay chạy trước khi kết luận nhé.”
- **Lý do:** Phân biệt sạc/chi phí phụ thuộc chính sách áp dụng và không khẳng định ưu đãi vô điều kiện; chưa xác minh riêng đối tượng biển vàng.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `0cf4b86f-979c-4b52-b172-43925926f482` (customer): “Anh thường chạy khoảng 200-300 km một ngày, và có khoảng 1-2 giờ nghỉ giữa ca. Anh muốn biết chi phí sạc cho quãng đường đó.”
- `c7346886-ae02-4fba-99ce-704d6eb0dfb5` (customer): “Anh lo nhất là thời gian dừng sạc có ảnh hưởng đến thu nhập. Nếu phải dừng sạc trong giờ cao điểm thì sẽ mất cuốc, không biết có cách nào tối ưu không?”
- `cd86019a-55d2-4136-8af4-e5b0f7590b71` (advisor): “Nếu anh muốn, em gửi bảng so sánh có ghi rõ giả định và cùng anh rà lại lịch chạy vào một cuộc gọi ngắn.”
- **Lý do:** Đề xuất bảng giả định và cuộc gọi ngắn rà lại lịch chạy, kèm lựa chọn “nếu anh muốn”, đúng rào cản mất thu nhập.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_04_VF5_04 — SCENARIO_01_VF5_TAXI (v2.2)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `1.75`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `534c0acf-a349-46de-88d2-9b04b9743b9e` (customer): “VF 5 Plus lăn bánh bao nhiêu? Anh muốn so sánh chi phí sử dụng với Vios.”
- `d1925621-273d-4e57-89c9-11ebfae1e48e` (advisor): “Giá niêm yết và giá lăn bánh khác nhau vì thuế, phí và nơi đăng ký. Anh định đăng ký ở tỉnh thành nào ạ?”
- `b657c210-e631-4978-b8e5-286604938cd1` (customer): “Em nghe nói sạc ngoài vẫn tốn tiền, rồi còn trả góp nữa. Chạy nhiều như anh thì đổi từ Vios có đáng không em?”
- `60c0751e-4ba0-4940-a7c7-82c4ec281427` (advisor): “Anh dùng biển trắng hay biển vàng để chạy dịch vụ? Điều này cần được đối chiếu khi tính chi phí.”
- **Lý do:** Hỏi nơi đăng ký để tính giá lăn bánh và phân loại biển để tính ưu đãi sạc; chưa có phản hồi để cá nhân hóa tiếp.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `534c0acf-a349-46de-88d2-9b04b9743b9e` (customer): “VF 5 Plus lăn bánh bao nhiêu? Anh muốn so sánh chi phí sử dụng với Vios.”
- `d1925621-273d-4e57-89c9-11ebfae1e48e` (advisor): “Giá niêm yết và giá lăn bánh khác nhau vì thuế, phí và nơi đăng ký. Anh định đăng ký ở tỉnh thành nào ạ?”
- `4be8543b-7780-4480-9315-066aef2b72f7` (customer): “Em có thể cho anh biết cụ thể về chi phí sạc ngoài và thời gian dừng sạc ảnh hưởng đến thu nhập như thế nào không?”
- **Lý do:** Phân biệt giá niêm yết với giá lăn bánh và hỏi địa phương thay vì bịa số; phần câu hỏi chi phí/thời gian sạc chưa kịp triển khai.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`); `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `b657c210-e631-4978-b8e5-286604938cd1` (customer): “Em nghe nói sạc ngoài vẫn tốn tiền, rồi còn trả góp nữa. Chạy nhiều như anh thì đổi từ Vios có đáng không em?”
- `60c0751e-4ba0-4940-a7c7-82c4ec281427` (advisor): “Anh dùng biển trắng hay biển vàng để chạy dịch vụ? Điều này cần được đối chiếu khi tính chi phí.”
- `4be8543b-7780-4480-9315-066aef2b72f7` (customer): “Em có thể cho anh biết cụ thể về chi phí sạc ngoài và thời gian dừng sạc ảnh hưởng đến thu nhập như thế nào không?”
- **Lý do:** Khi khách lo tiền sạc và trả góp, advisor chỉ hỏi loại biển mà chưa xác nhận nỗi lo hay phản hồi bằng phương án chi phí.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `60c0751e-4ba0-4940-a7c7-82c4ec281427` (advisor): “Anh dùng biển trắng hay biển vàng để chạy dịch vụ? Điều này cần được đối chiếu khi tính chi phí.”
- **Lý do:** Nhận ra biển vàng là biến điều kiện quan trọng đối với ưu đãi sạc xe dịch vụ; không kết luận sai trước khi biết loại biển.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `4be8543b-7780-4480-9315-066aef2b72f7` (customer): “Em có thể cho anh biết cụ thể về chi phí sạc ngoài và thời gian dừng sạc ảnh hưởng đến thu nhập như thế nào không?”
- **Lý do:** Transcript dừng ở lời hỏi tiếp của khách, chỉ có hai phản hồi của advisor trong bước thu thập thông tin; chưa có thời điểm kết thúc/đề nghị tiếp tục đủ để chấm closing.

**Factual findings (phát biểu đáng chú ý):**
- **UNVERIFIABLE** — `d1925621-273d-4e57-89c9-11ebfae1e48e`: “Giá niêm yết và giá lăn bánh khác nhau vì thuế, phí và nơi đăng ký. Anh định đăng ký ở tỉnh thành nào ạ?”
  - Nhận định: Tài liệu nêu MSRP kèm pin, nhưng không chứa biểu phí lăn bánh từng địa phương để kiểm định đủ vế thuế/phí.
  - Source IDs/versions: `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `PRICE_LIST_VINFAST_20260921`: “Giá bán bán lẻ đề xuất (MSRP) kèm pin, bao gồm VAT”
- **SUPPORTED** — `60c0751e-4ba0-4940-a7c7-82c4ec281427`: “Anh dùng biển trắng hay biển vàng để chạy dịch vụ? Điều này cần được đối chiếu khi tính chi phí.”
  - Nhận định: Loại biển đăng ký là biến điều kiện ưu đãi sạc; chưa suy ra mức hưởng khi khách chưa xác nhận.
  - Source IDs/versions: `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`).
  - Trích nguồn — `POLICY_CHARGING_VINFAST_20260919`: “- | Với Khách hàng xe biển vàng mua xe từ ngày 20/04/2026, ưu đãi sạc trên được áp dụng như sau:”

---

### JH26_05_VF5_05 — SCENARIO_01_VF5_TAXI (v2.2)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `5/5`. **Overall score:** `1.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `be1eee94-4038-4860-abcb-b6689fb87444` (customer): “VF 5 Plus lăn bánh khoảng bao nhiêu? Anh muốn so sánh chi phí sử dụng với Vios.”
- `04b2cb33-d54d-4791-aa71-27aa003d1eb8` (advisor): “Anh yên tâm, tiền sạc xe này luôn cố định một mức cho mọi trạm và sẽ không bao giờ tăng.”
- `7da39dd5-1f76-4e8e-bfa1-6c84a1d9d040` (customer): “Em có thể cho anh biết chi phí sạc cụ thể cho VF 5 Plus không? Anh cần biết rõ để so sánh với chi phí xăng của Vios.”
- `ba5744bb-21b8-4e4f-9fe9-c4e6ef979aeb` (advisor): “Anh cứ quyết định đổi xe; em khẳng định chi phí sạc sẽ thấp hơn tiền xăng của anh trong mọi trường hợp.”
- **Lý do:** Không hỏi bất cứ dữ liệu thực tế nào về km, chi phí xăng hay khả năng trả góp; mặc định luôn tiết kiệm.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `0c4dd4fa-5d35-4251-8aa5-e1b4e2be37ab` (customer): “Em có thể cho anh biết thêm về chi phí sạc và thời gian sạc trung bình không? Anh cần biết rõ để tính toán xem có đáng đổi không.”
- `022e463b-aec0-40e6-b4dd-943c47b8d105` (advisor): “Em không cần kiểm tra chính sách vì mọi khách đều được áp dụng như nhau.”
- `7da39dd5-1f76-4e8e-bfa1-6c84a1d9d040` (customer): “Em có thể cho anh biết chi phí sạc cụ thể cho VF 5 Plus không? Anh cần biết rõ để so sánh với chi phí xăng của Vios.”
- `ba5744bb-21b8-4e4f-9fe9-c4e6ef979aeb` (advisor): “Anh cứ quyết định đổi xe; em khẳng định chi phí sạc sẽ thấp hơn tiền xăng của anh trong mọi trường hợp.”
- **Lý do:** Không giải thích thời gian sạc và quy đổi kWh; phát biểu chi phí lúc nào cũng thấp hơn xăng trong mọi trường hợp không dựa dữ liệu khách.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `ead2f283-193d-4b5b-9ce5-4dc0be170f93` (customer): “Nhưng anh nghe nói sạc ngoài lượt được ưu đãi vẫn tốn tiền, rồi còn trả góp nữa. Chạy nhiều như anh thì đổi từ Vios có đáng không em?”
- `d8d8f8e7-554b-4ee2-bd1f-a492396def76` (advisor): “Dù anh chạy ngày hay đêm, cứ tính cùng một đơn giá ấy là chắc chắn đúng.”
- `7da39dd5-1f76-4e8e-bfa1-6c84a1d9d040` (customer): “Em có thể cho anh biết chi phí sạc cụ thể cho VF 5 Plus không? Anh cần biết rõ để so sánh với chi phí xăng của Vios.”
- `ba5744bb-21b8-4e4f-9fe9-c4e6ef979aeb` (advisor): “Anh cứ quyết định đổi xe; em khẳng định chi phí sạc sẽ thấp hơn tiền xăng của anh trong mọi trường hợp.”
- **Lý do:** Bỏ qua lo lắng về sạc ngoài ưu đãi và dòng tiền, chỉ trấn an tuyệt đối rồi ép quyết định đổi xe.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `04b2cb33-d54d-4791-aa71-27aa003d1eb8` (advisor): “Anh yên tâm, tiền sạc xe này luôn cố định một mức cho mọi trạm và sẽ không bao giờ tăng.”
- `d8d8f8e7-554b-4ee2-bd1f-a492396def76` (advisor): “Dù anh chạy ngày hay đêm, cứ tính cùng một đơn giá ấy là chắc chắn đúng.”
- `022e463b-aec0-40e6-b4dd-943c47b8d105` (advisor): “Em không cần kiểm tra chính sách vì mọi khách đều được áp dụng như nhau.”
- **Lý do:** Cam kết giá sạc cố định mãi, chính sách cho mọi khách như nhau; mâu thuẫn điều kiện ưu đãi theo biển, thời gian và giới hạn số lần.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`); `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `ba5744bb-21b8-4e4f-9fe9-c4e6ef979aeb` (advisor): “Anh cứ quyết định đổi xe; em khẳng định chi phí sạc sẽ thấp hơn tiền xăng của anh trong mọi trường hợp.”
- `bf96ff8a-e420-4f40-bb9f-9ada296a14b2` (customer): “Anh vẫn chưa yên tâm về điểm này. Bây giờ anh phải ghé siêu thị mua ít đồ. Mình tạm dừng ở đây; em gửi thông tin phù hợp với trường hợp của anh sau nhé.”
- **Lý do:** Kêu khách quyết định đổi xe khi chưa minh bạch chi phí; khách xin dừng và nhận thông tin nhưng chưa được đề xuất bước theo dõi cụ thể.
- **Cần cải thiện để đạt mức cao hơn:** Xin phép khách về một hành động cụ thể theo đúng mức sẵn sàng; nêu kênh, thời điểm hoặc người thực hiện.

**Factual findings (phát biểu đáng chú ý):**
- **UNVERIFIABLE** — `04b2cb33-d54d-4791-aa71-27aa003d1eb8`: “Anh yên tâm, tiền sạc xe này luôn cố định một mức cho mọi trạm và sẽ không bao giờ tăng.”
  - Nhận định: Cam kết đơn giá sẽ không bao giờ tăng là dự báo tương lai không thể xác minh từ tài liệu.
  - Source IDs/versions: `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`); `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `CHARGING_TARIFF_VINFAST_20261004`: “Trang dịch vụ pin ô tô điện của VinFast công bố đơn giá tại trạm sạc công cộng là 3.858 VNĐ/kWh”
  - Nguồn xem bối cảnh (không chứng minh claim) — `POLICY_CHARGING_VINFAST_20260919`: “- | Với Khách hàng xe biển vàng mua xe từ ngày 20/04/2026, ưu đãi sạc trên được áp dụng như sau:”
- **UNVERIFIABLE** — `d8d8f8e7-554b-4ee2-bd1f-a492396def76`: “Dù anh chạy ngày hay đêm, cứ tính cùng một đơn giá ấy là chắc chắn đúng.”
  - Nhận định: Đơn giá cơ sở và chi phí thực trả sau ưu đãi là hai khái niệm khác nhau; phát biểu không nêu rõ mức giá, đối tượng hay kỳ áp dụng để chứng thực lời chắc chắn.
  - Source IDs/versions: `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`); `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `CHARGING_TARIFF_VINFAST_20261004`: “Trang dịch vụ pin ô tô điện của VinFast công bố đơn giá tại trạm sạc công cộng là 3.858 VNĐ/kWh”
  - Nguồn xem bối cảnh (không chứng minh claim) — `POLICY_CHARGING_VINFAST_20260919`: “- | Với Khách hàng xe biển vàng mua xe từ ngày 20/04/2026, ưu đãi sạc trên được áp dụng như sau:”
- **CONTRADICTED** — `022e463b-aec0-40e6-b4dd-943c47b8d105`: “Em không cần kiểm tra chính sách vì mọi khách đều được áp dụng như nhau.”
  - Nhận định: Ưu đãi sạc không giống nhau cho mọi khách/xe/khung giờ.
  - Source IDs/versions: `POLICY_CHARGING_VINFAST_20260919` / `2026.09.19` (trạng thái KB: `active`).
  - Trích nguồn — `POLICY_CHARGING_VINFAST_20260919`: “- | Với Khách hàng xe biển vàng mua xe từ ngày 20/04/2026, ưu đãi sạc trên được áp dụng như sau:”
- **UNVERIFIABLE** — `ba5744bb-21b8-4e4f-9fe9-c4e6ef979aeb`: “Anh cứ quyết định đổi xe; em khẳng định chi phí sạc sẽ thấp hơn tiền xăng của anh trong mọi trường hợp.”
  - Nhận định: Không có dữ liệu tình huống đầy đủ để cam đoan chi phí sạc luôn thấp hơn xăng Vios.
  - Source IDs/versions: `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`); `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `CHARGING_TARIFF_VINFAST_20261004`: “Trang dịch vụ pin ô tô điện của VinFast công bố đơn giá tại trạm sạc công cộng là 3.858 VNĐ/kWh”
  - Nguồn xem bối cảnh (không chứng minh claim) — `SPECS_VF5_PLUS_2026`: “Thời gian nạp pin nhanh nhất (10%-70%)”

---

### JH26_06_VF5_06 — SCENARIO_01_VF5_TAXI (v2.2)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `5/5`. **Overall score:** `1.40`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `de72d53c-347b-496f-baf7-0d1e0531e96f` (advisor): “Anh có thể cho em biết mức tiền dự kiến trả trước và phần còn lại muốn vay không ạ?”
- `7a5d8b89-41d5-4ebf-ad28-54d94a5d9007` (customer): “Anh hay chạy liền ca trưa. Nếu phải dừng sạc lâu thì mất cuốc, có cách nào sắp lịch sạc hợp lý không em?”
- `7a3ecf5c-b7b0-4dda-8eea-3482782c146d` (advisor): “Tiền xăng Vios hiện tại mỗi tháng của anh khoảng bao nhiêu để mình tách khỏi khoản trả góp?”
- `963a00d9-15d5-49b4-9bda-931886d1fcc6` (advisor): “Anh có lịch chạy và quãng đường trung bình thế nào? Chi phí vận hành phải dựa vào thực tế của anh.”
- **Lý do:** Thu thập mức vay, xăng Vios và quãng đường để tính toán, song chưa khai thác/điều chỉnh phương án theo ca trưa bị mất cuốc.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `7a5d8b89-41d5-4ebf-ad28-54d94a5d9007` (customer): “Anh hay chạy liền ca trưa. Nếu phải dừng sạc lâu thì mất cuốc, có cách nào sắp lịch sạc hợp lý không em?”
- `1278224b-b5fd-440d-8552-9deaa03eddfd` (customer): “Em có thể cho anh biết thời gian sạc đầy của VF 5 Plus là bao lâu không? Anh cần biết để sắp xếp lịch chạy cho hợp lý.”
- `e5b858bb-77ad-4d48-bcf2-d0afcde6654d` (advisor): “Lãi vay và ưu đãi phụ thuộc hồ sơ, ngân hàng và thời điểm; em cần xác minh bảng điều kiện trước khi lập phép tính.”
- **Lý do:** Khách hỏi thẳng thời gian sạc đầy và xếp lịch chạy, advisor đổi sang lãi vay và không trả lời thông số sản phẩm.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`); `FAQ_VF5_20260922` / `2026.09.22` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `7a5d8b89-41d5-4ebf-ad28-54d94a5d9007` (customer): “Anh hay chạy liền ca trưa. Nếu phải dừng sạc lâu thì mất cuốc, có cách nào sắp lịch sạc hợp lý không em?”
- `38c081ca-9b6f-428f-926d-9505740823a3` (customer): “Nếu em có thể tư vấn cách sắp xếp lịch sạc hợp lý để không ảnh hưởng đến thời gian chạy của anh thì tốt quá. Anh cần biết cụ thể hơn về thời gian sạc và cách quản lý nó.”
- `e5b858bb-77ad-4d48-bcf2-d0afcde6654d` (advisor): “Lãi vay và ưu đãi phụ thuộc hồ sơ, ngân hàng và thời điểm; em cần xác minh bảng điều kiện trước khi lập phép tính.”
- `dbe441d2-3a4f-4946-ab08-19efbaa3e662` (customer): “Anh nghe nói sạc ngoài lượt được ưu đãi vẫn tốn tiền, rồi còn trả góp nữa. Chạy nhiều như anh thì đổi từ Vios có đáng không em?”
- **Lý do:** Lo mất cuốc giữa ca được nêu hai lần; advisor né sang khoản vay và vẫn không xử lý phương án sạc.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `e5b858bb-77ad-4d48-bcf2-d0afcde6654d` (advisor): “Lãi vay và ưu đãi phụ thuộc hồ sơ, ngân hàng và thời điểm; em cần xác minh bảng điều kiện trước khi lập phép tính.”
- **Lý do:** Không tự khẳng định lãi vay/ưu đãi mà yêu cầu kiểm tra hồ sơ, ngân hàng và thời điểm; bảng nguồn không đủ điều kiện lãi cụ thể nên giữ chờ xác minh.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `PROMOTION_SALES_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `dbe441d2-3a4f-4946-ab08-19efbaa3e662` (customer): “Anh nghe nói sạc ngoài lượt được ưu đãi vẫn tốn tiền, rồi còn trả góp nữa. Chạy nhiều như anh thì đổi từ Vios có đáng không em?”
- `677893aa-f28b-4e6a-b663-ae3042d07910` (advisor): “Em sẽ gửi hai kịch bản với giả định rõ ràng, để anh tự xem mức trả hàng tháng có phù hợp dòng tiền không.”
- `58e53cac-8bbf-4c7d-9a57-934ba9eba72b` (customer): “Em có thể cho anh biết cụ thể hơn về chi phí sạc và trả góp không? Anh cần biết rõ để so sánh với chi phí xăng của Vios.”
- **Lý do:** Hứa gửi hai kịch bản đúng mối quan tâm dòng tiền nhưng không xin đồng ý, nêu thời điểm/kênh hoặc trả lời yêu cầu cụ thể về sạc.
- **Cần cải thiện để đạt mức cao hơn:** Xin phép khách về một hành động cụ thể theo đúng mức sẵn sàng; nêu kênh, thời điểm hoặc người thực hiện.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_07_VF5_07 — SCENARIO_01_VF5_TAXI (v2.2)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `1.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `12d592a8-e1c0-49c5-aef4-534087155939` (customer): “VF 5 Plus lăn bánh khoảng bao nhiêu? Anh đang chạy Vios dịch vụ, muốn biết chi phí sử dụng xe điện này so với Vios ra sao.”
- `bb38eba5-8094-4d49-be4f-7f4ad4744197` (advisor): “VF 5 Plus đang được nhiều người quan tâm, kiểu dáng cũng đẹp anh ạ.”
- `e3b7e78b-1a10-4c37-8300-ed86c74425e5` (customer): “Em nghe nói sạc ngoài vẫn tốn tiền và có trả góp nữa. Anh chạy nhiều như vậy thì đổi từ Vios có đáng không em?”
- `6df5e14a-fdb8-4101-90ac-e1d4c04fc52e` (advisor): “Chuyện dừng sạc và mất cuốc chắc không đáng lo đâu. Anh cứ xem xe trước rồi tính tiếp.”
- **Lý do:** Không tìm hiểu số km, thu nhập, loại biển hoặc cách sạc; bỏ qua mục đích chạy dịch vụ được nêu ngay đầu.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `12d592a8-e1c0-49c5-aef4-534087155939` (customer): “VF 5 Plus lăn bánh khoảng bao nhiêu? Anh đang chạy Vios dịch vụ, muốn biết chi phí sử dụng xe điện này so với Vios ra sao.”
- `bb38eba5-8094-4d49-be4f-7f4ad4744197` (advisor): “VF 5 Plus đang được nhiều người quan tâm, kiểu dáng cũng đẹp anh ạ.”
- `97a41034-097c-4123-92c7-1ce933fff897` (customer): “Em có thể cho anh biết cụ thể chi phí sạc ngoài và cách trả góp cho VF 5 Plus không? Anh cần biết rõ để tính toán.”
- **Lý do:** Thay thông tin giá, chi phí sạc và trả góp bằng lời bình về mẫu mã; bỏ qua câu hỏi sản phẩm trực tiếp.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `SPECS_VF5_PLUS_2026` / `2026.09.22` (trạng thái KB: `active`); `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `e3b7e78b-1a10-4c37-8300-ed86c74425e5` (customer): “Em nghe nói sạc ngoài vẫn tốn tiền và có trả góp nữa. Anh chạy nhiều như vậy thì đổi từ Vios có đáng không em?”
- `6df5e14a-fdb8-4101-90ac-e1d4c04fc52e` (advisor): “Chuyện dừng sạc và mất cuốc chắc không đáng lo đâu. Anh cứ xem xe trước rồi tính tiếp.”
- **Lý do:** Phủi lo mất cuốc bằng “chắc không đáng lo” mà không tính thời gian sạc, dòng tiền hoặc xác minh gì.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `bb38eba5-8094-4d49-be4f-7f4ad4744197` (advisor): “VF 5 Plus đang được nhiều người quan tâm, kiểu dáng cũng đẹp anh ạ.”
- `6df5e14a-fdb8-4101-90ac-e1d4c04fc52e` (advisor): “Chuyện dừng sạc và mất cuốc chắc không đáng lo đâu. Anh cứ xem xe trước rồi tính tiếp.”
- **Lý do:** Advisor không nêu chính sách sạc, tài chính hoặc giá cụ thể; thiếu claim để xét accuracy, sự né tránh đã được trừ ở Product Knowledge.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `e3b7e78b-1a10-4c37-8300-ed86c74425e5` (customer): “Em nghe nói sạc ngoài vẫn tốn tiền và có trả góp nữa. Anh chạy nhiều như vậy thì đổi từ Vios có đáng không em?”
- `6df5e14a-fdb8-4101-90ac-e1d4c04fc52e` (advisor): “Chuyện dừng sạc và mất cuốc chắc không đáng lo đâu. Anh cứ xem xe trước rồi tính tiếp.”
- **Lý do:** “Cứ xem xe trước rồi tính tiếp” là bước vội và không gắn băn khoăn; không hỏi sự đồng ý hay cách tiếp tục.
- **Cần cải thiện để đạt mức cao hơn:** Xin phép khách về một hành động cụ thể theo đúng mức sẵn sàng; nêu kênh, thời điểm hoặc người thực hiện.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_08_VF7_08 — SCENARIO_02_VF7_VS_CX5 (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `2.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `3502167e-c58d-4b58-b542-8bbe39d7b2d1` (advisor): “Nhà chị thường có mấy người đi cùng và xe chủ yếu dùng trong phố hay đi xa ạ?”
- `424a34f7-2aa5-49df-8f4f-04f8792c622e` (customer): “Nhà chị có 2 vợ chồng với 2 nhóc tì, mua xe chủ yếu đi lại hàng ngày với cuối tuần hay chở cả nhà về ngoại tầm 120 cây số.”
- `5ab6d23c-9de5-4174-830e-afa01d3a6b2d` (advisor): “Những chuyến đi cuối tuần của gia đình dài khoảng bao nhiêu, chị ưu tiên chỗ ngồi hay chỗ hành lý?”
- `108f6ea4-c57d-4d6b-86d8-1a53083cf17b` (advisor): “Trong hai mẫu xe, điều gì khiến chị thấy khó quyết nhất: chi phí, trải nghiệm hay sự quen thuộc?”
- `b436d2fb-955e-4885-906c-709a4e56b43f` (advisor): “Người cùng chị quyết định mua xe quan tâm nhất điều gì để em không chỉ nói theo góc nhìn của một người?”
- `b7313071-853b-4376-bc42-5b1447af43b4` (advisor): “Em có thể sắp xếp buổi xem xe để cả nhà thử không gian và đối chiếu theo những tiêu chí chị vừa nêu; chị thấy phù hợp không?”
- **Lý do:** Khai thác người ngồi, quãng đường 120 km, không gian/hành lý và người cùng quyết định; mời cả nhà đến kiểm tra đúng tiêu chí.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `995cf2ff-fe28-4d8e-be95-736a33fab5f1` (customer): “Em thấy VF 7 có nhiều công nghệ hiện đại hơn và không gian nội thất rộng rãi hơn, nhưng chị vẫn chưa rõ lý do tại sao lại chênh lệch nhiều như vậy. Có điểm nào nổi bật hơn mà chị nên biết không?”
- `108f6ea4-c57d-4d6b-86d8-1a53083cf17b` (advisor): “Trong hai mẫu xe, điều gì khiến chị thấy khó quyết nhất: chi phí, trải nghiệm hay sự quen thuộc?”
- `41346248-3ced-444d-9c55-c341e53f05fc` (customer): “Chị vẫn chưa thấy rõ lý do tại sao VF 7 lại đắt hơn CX-5 50 triệu. Có điểm nào nổi bật hơn mà em có thể giải thích thêm không?”
- `b436d2fb-955e-4885-906c-709a4e56b43f` (advisor): “Người cùng chị quyết định mua xe quan tâm nhất điều gì để em không chỉ nói theo góc nhìn của một người?”
- **Lý do:** Khách liên tục cần biết lý do chênh giá/công nghệ nổi bật; advisor chỉ tiếp tục đặt câu hỏi, không đưa thông tin có nguồn về VF 7 hoặc bảng so cùng phiên bản.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `PRODUCT_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `41346248-3ced-444d-9c55-c341e53f05fc` (customer): “Chị vẫn chưa thấy rõ lý do tại sao VF 7 lại đắt hơn CX-5 50 triệu. Có điểm nào nổi bật hơn mà em có thể giải thích thêm không?”
- `b436d2fb-955e-4885-906c-709a4e56b43f` (advisor): “Người cùng chị quyết định mua xe quan tâm nhất điều gì để em không chỉ nói theo góc nhìn của một người?”
- `30cbc2c2-3641-435a-804a-03200058efdf` (customer): “Em vẫn chưa thấy rõ lý do tại sao VF 7 lại đắt hơn CX-5 50 triệu. Có điểm nào nổi bật hơn mà em có thể giải thích thêm không?”
- `b7313071-853b-4376-bc42-5b1447af43b4` (advisor): “Em có thể sắp xếp buổi xem xe để cả nhà thử không gian và đối chiếu theo những tiêu chí chị vừa nêu; chị thấy phù hợp không?”
- **Lý do:** Không phản hồi trực diện băn khoăn giá chênh 50 triệu dù khách nhắc nhiều lần; bỏ lửng cả vấn đề mất giá ở lượt cuối (không trừ riêng phần chưa được phản hồi).
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `108f6ea4-c57d-4d6b-86d8-1a53083cf17b` (advisor): “Trong hai mẫu xe, điều gì khiến chị thấy khó quyết nhất: chi phí, trải nghiệm hay sự quen thuộc?”
- `b436d2fb-955e-4885-906c-709a4e56b43f` (advisor): “Người cùng chị quyết định mua xe quan tâm nhất điều gì để em không chỉ nói theo góc nhìn của một người?”
- **Lý do:** Không có claim giá, ưu đãi hoặc điều khoản nào do advisor xác quyết; chênh 50 triệu là giả định của customer chưa đối chiếu đủ hai mẫu.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `424a34f7-2aa5-49df-8f4f-04f8792c622e` (customer): “Nhà chị có 2 vợ chồng với 2 nhóc tì, mua xe chủ yếu đi lại hàng ngày với cuối tuần hay chở cả nhà về ngoại tầm 120 cây số.”
- `b436d2fb-955e-4885-906c-709a4e56b43f` (advisor): “Người cùng chị quyết định mua xe quan tâm nhất điều gì để em không chỉ nói theo góc nhìn của một người?”
- `b7313071-853b-4376-bc42-5b1447af43b4` (advisor): “Em có thể sắp xếp buổi xem xe để cả nhà thử không gian và đối chiếu theo những tiêu chí chị vừa nêu; chị thấy phù hợp không?”
- **Lý do:** Đề xuất cả nhà trải nghiệm không gian rồi đối chiếu tiêu chí người quyết định; hỏi rõ “chị thấy phù hợp không?”, không ép cọc.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_09_VF7_09 — SCENARIO_02_VF7_VS_CX5 (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `2.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `4f308485-983f-40c5-b692-bb3c0309d8c1` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `331ce9e5-510c-4590-967b-7081f186967e` (advisor): “Chị đang so VF 7 với CX-5 theo tiêu chí nào là quan trọng nhất cho gia đình mình ạ?”
- `515ba11b-07d4-4628-a81a-2f5f75e5704b` (customer): “Chị đang quan tâm đến công nghệ và tính năng của xe. VF 7 có gì nổi bật hơn CX-5 mà đáng để bỏ thêm 50 triệu không em?”
- `24ffe84c-42d8-4644-b2ca-ac1af6c5e85d` (advisor): “Về khoản chênh giá, mình cần xác nhận đúng phiên bản và bảng giá ở cùng thời điểm trước khi so.”
- `09b7e34f-deef-426c-a9e1-05d8e9f8dbed` (customer): “Nhà chị có 2 vợ chồng với 2 nhóc tì, mua xe chủ yếu đi lại hàng ngày với cuối tuần hay chở cả nhà về ngoại tầm 120 cây số. Chị thì mê kiểu dáng công nghệ của VF 7 rồi, nhưng ông xã chị cứ cản, bảo mua CX-5 cho lành, sợ xe điện sau này bán mất giá.”
- **Lý do:** Hỏi trọng số lựa chọn và khung so sánh, nhưng thông tin công nghệ/gia đình xuất hiện muộn, chưa có tư vấn tùy biến.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `515ba11b-07d4-4628-a81a-2f5f75e5704b` (customer): “Chị đang quan tâm đến công nghệ và tính năng của xe. VF 7 có gì nổi bật hơn CX-5 mà đáng để bỏ thêm 50 triệu không em?”
- `24ffe84c-42d8-4644-b2ca-ac1af6c5e85d` (advisor): “Về khoản chênh giá, mình cần xác nhận đúng phiên bản và bảng giá ở cùng thời điểm trước khi so.”
- **Lý do:** Từ chối lý giải giá chênh dựa trên hai bản chưa xác nhận, yêu cầu đối chiếu phiên bản/thời điểm; hợp lý vì kho không chứa thông số CX-5.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `4f308485-983f-40c5-b692-bb3c0309d8c1` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `331ce9e5-510c-4590-967b-7081f186967e` (advisor): “Chị đang so VF 7 với CX-5 theo tiêu chí nào là quan trọng nhất cho gia đình mình ạ?”
- `24ffe84c-42d8-4644-b2ca-ac1af6c5e85d` (advisor): “Về khoản chênh giá, mình cần xác nhận đúng phiên bản và bảng giá ở cùng thời điểm trước khi so.”
- **Lý do:** Nhận diện trở ngại so sánh giá và chuyển sang điều kiện so sánh đúng, dù chưa giải thích công nghệ và chưa xử lý lo mất giá mới xuất hiện ở lượt cuối.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `24ffe84c-42d8-4644-b2ca-ac1af6c5e85d` (advisor): “Về khoản chênh giá, mình cần xác nhận đúng phiên bản và bảng giá ở cùng thời điểm trước khi so.”
- **Lý do:** Thận trọng yêu cầu bảng giá cùng thời điểm và phiên bản trước khi kết luận chênh lệch; phù hợp bảng MSRP có nhiều cấu hình.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `09b7e34f-deef-426c-a9e1-05d8e9f8dbed` (customer): “Nhà chị có 2 vợ chồng với 2 nhóc tì, mua xe chủ yếu đi lại hàng ngày với cuối tuần hay chở cả nhà về ngoại tầm 120 cây số. Chị thì mê kiểu dáng công nghệ của VF 7 rồi, nhưng ông xã chị cứ cản, bảo mua CX-5 cho lành, sợ xe điện sau này bán mất giá.”
- **Lý do:** Hội thoại kết thúc ngay sau khi khách cung cấp thêm thông tin gia đình và ý kiến chồng; chưa có cơ hội hợp lý để tư vấn bước tiếp theo dựa trên dữ liệu vừa nhận.

**Factual findings (phát biểu đáng chú ý):**
- **SUPPORTED** — `24ffe84c-42d8-4644-b2ca-ac1af6c5e85d`: “Về khoản chênh giá, mình cần xác nhận đúng phiên bản và bảng giá ở cùng thời điểm trước khi so.”
  - Nhận định: Các cấu hình/phiên bản có MSRP khác nhau; đối chiếu phải cùng thời điểm. Không có hồ sơ CX-5 trong KB.
  - Source IDs/versions: `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).
  - Trích nguồn — `PRICE_LIST_VINFAST_20260921`: “Giá bán bán lẻ đề xuất (MSRP) kèm pin, bao gồm VAT”

---

### JH26_10_VF7_10 — SCENARIO_02_VF7_VS_CX5 (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `1.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `7d3a9de3-2b3e-41c8-9c15-a10dc5ff7524` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `d9da0363-591e-473c-bbde-a1faf21f3e52` (advisor): “Chị lo bán lại sau ba năm à? Em cam đoan VF 7 sẽ giữ ít nhất 90% giá mua, không có rủi ro mất giá.”
- `b56915a4-f2fd-49ec-a95c-e7f946af422f` (customer): “CX-5 đi đầy đường vừa lành vừa đẹp, VF 7 mới ra chưa biết thế nào mà bán đắt thế em?”
- `20810cf1-3272-4550-8fc7-7e713d243f7f` (advisor): “Con số đó chắc chắn áp dụng cho mọi phiên bản và mọi thời điểm, chị không cần hỏi thêm bên nào.”
- **Lý do:** Tự suy đoán lo bán lại dù khách hỏi lý do chênh giá; không hỏi nhu cầu gia đình hay phiên bản.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `7d3a9de3-2b3e-41c8-9c15-a10dc5ff7524` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `d9da0363-591e-473c-bbde-a1faf21f3e52` (advisor): “Chị lo bán lại sau ba năm à? Em cam đoan VF 7 sẽ giữ ít nhất 90% giá mua, không có rủi ro mất giá.”
- `4afe11d6-6ccc-402d-bff0-9412996d8db9` (customer): “Em có thể cho chị biết lý do cụ thể nào khiến VF 7 lại đắt hơn CX-5 không?”
- **Lý do:** Không cung cấp khác biệt có căn cứ giữa VF 7 và CX-5, thay bằng cam kết giá bán lại không liên quan trực tiếp câu hỏi.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRODUCT_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `7d3a9de3-2b3e-41c8-9c15-a10dc5ff7524` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `d9da0363-591e-473c-bbde-a1faf21f3e52` (advisor): “Chị lo bán lại sau ba năm à? Em cam đoan VF 7 sẽ giữ ít nhất 90% giá mua, không có rủi ro mất giá.”
- `b56915a4-f2fd-49ec-a95c-e7f946af422f` (customer): “CX-5 đi đầy đường vừa lành vừa đẹp, VF 7 mới ra chưa biết thế nào mà bán đắt thế em?”
- `20810cf1-3272-4550-8fc7-7e713d243f7f` (advisor): “Con số đó chắc chắn áp dụng cho mọi phiên bản và mọi thời điểm, chị không cần hỏi thêm bên nào.”
- **Lý do:** Hiểu lệch phản đối về chênh giá sang bán lại, khẳng định không rủi ro và ngăn khách kiểm tra độc lập.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `d9da0363-591e-473c-bbde-a1faf21f3e52` (advisor): “Chị lo bán lại sau ba năm à? Em cam đoan VF 7 sẽ giữ ít nhất 90% giá mua, không có rủi ro mất giá.”
- `20810cf1-3272-4550-8fc7-7e713d243f7f` (advisor): “Con số đó chắc chắn áp dụng cho mọi phiên bản và mọi thời điểm, chị không cần hỏi thêm bên nào.”
- **Lý do:** Cam kết giữ ít nhất 90% giá và áp dụng mọi bản/mọi lúc không có nguồn chính sách bảo chứng; tuyệt đối hóa quyền lợi tài chính chưa được duyệt.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `PROMOTION_SALES_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `4afe11d6-6ccc-402d-bff0-9412996d8db9` (customer): “Em có thể cho chị biết lý do cụ thể nào khiến VF 7 lại đắt hơn CX-5 không?”
- **Lý do:** Đoạn ngắn kết thúc bằng yêu cầu giải thích giá của khách; advisor chưa bước vào giai đoạn hẹn lịch/chốt và chưa có lời đề nghị next step để chấm.

**Factual findings (phát biểu đáng chú ý):**
- **UNVERIFIABLE** — `d9da0363-591e-473c-bbde-a1faf21f3e52`: “Chị lo bán lại sau ba năm à? Em cam đoan VF 7 sẽ giữ ít nhất 90% giá mua, không có rủi ro mất giá.”
  - Nhận định: Không có cam kết chính thức giữ tối thiểu 90% giá mua sau ba năm trong bộ nguồn được cấp.
  - Source IDs/versions: `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `PROMOTION_SALES_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `PRICE_LIST_VINFAST_20260921`: “Giá bán bán lẻ đề xuất (MSRP) kèm pin, bao gồm VAT”
  - Nguồn xem bối cảnh (không chứng minh claim) — `PROMOTION_SALES_VINFAST_20260921`: “Các dòng VF 7, VF 9, VF 8 Thế hệ mới, Lạc Hồng 900 LX, EC Van & VF Wild: Ưu đãi 5% MSRP.”
- **UNVERIFIABLE** — `20810cf1-3272-4550-8fc7-7e713d243f7f`: “Con số đó chắc chắn áp dụng cho mọi phiên bản và mọi thời điểm, chị không cần hỏi thêm bên nào.”
  - Nhận định: Lời bảo đảm áp dụng mọi phiên bản và mọi thời điểm không có căn cứ, không thể xác minh.
  - Source IDs/versions: `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `PROMOTION_SALES_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `PRICE_LIST_VINFAST_20260921`: “Giá bán bán lẻ đề xuất (MSRP) kèm pin, bao gồm VAT”
  - Nguồn xem bối cảnh (không chứng minh claim) — `PROMOTION_SALES_VINFAST_20260921`: “Các dòng VF 7, VF 9, VF 8 Thế hệ mới, Lạc Hồng 900 LX, EC Van & VF Wild: Ưu đãi 5% MSRP.”

---

### JH26_11_VF7_11 — SCENARIO_02_VF7_VS_CX5 (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `5/5`. **Overall score:** `1.80`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `4438bd5b-c532-4ade-a9b1-cf14dbea36d7` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `e299785a-914c-4bdb-be78-53510f4228b1` (advisor): “Chị đang hỏi bản VF 7 nào, và đang so với phiên bản CX-5 nào ạ?”
- `11f72bf7-259d-4017-a2fe-33af1ca28f1b` (customer): “Chị đang so bản VF 7 tiêu chuẩn với CX-5 tiêu chuẩn. Em có thể cho chị biết lý do cụ thể nào khiến VF 7 lại đắt hơn không?”
- `c79b83c8-d04d-49e4-b0af-33a13175b12d` (advisor): “Thông số trang bị có thể khác giữa các phiên bản; chị muốn ưu tiên an toàn, không gian hay tiện nghi?”
- `1839e287-bd55-4a51-b046-84c26349ab38` (customer): “Chị muốn biết cụ thể về những trang bị an toàn và công nghệ của VF 7 so với CX-5, có đáng giá thêm 50 triệu không?”
- **Lý do:** Hỏi cụ thể phiên bản hai xe và ưu tiên an toàn/không gian/tiện nghi; chưa áp dụng câu trả lời để trình bày lợi ích.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `11f72bf7-259d-4017-a2fe-33af1ca28f1b` (customer): “Chị đang so bản VF 7 tiêu chuẩn với CX-5 tiêu chuẩn. Em có thể cho chị biết lý do cụ thể nào khiến VF 7 lại đắt hơn không?”
- `1839e287-bd55-4a51-b046-84c26349ab38` (customer): “Chị muốn biết cụ thể về những trang bị an toàn và công nghệ của VF 7 so với CX-5, có đáng giá thêm 50 triệu không?”
- `b833411b-d566-40ac-9c29-d565e5c84049` (advisor): “Em cần kiểm tra tài liệu và thời điểm áp dụng trước khi xác nhận những tính năng chị hỏi.”
- `8e5234fa-ed01-49df-9429-6af8d9b706b9` (advisor): “Khi có đúng hai phiên bản, em sẽ gửi bảng đối chiếu kèm nguồn để chị và gia đình xem rồi mới quyết định bước tiếp.”
- **Lý do:** Chủ động không suy diễn trang bị từng bản và sẽ lập đối chiếu theo tài liệu có nguồn, nhưng chưa cung cấp ví dụ cụ thể cho câu hỏi công nghệ.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `4438bd5b-c532-4ade-a9b1-cf14dbea36d7` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `c79b83c8-d04d-49e4-b0af-33a13175b12d` (advisor): “Thông số trang bị có thể khác giữa các phiên bản; chị muốn ưu tiên an toàn, không gian hay tiện nghi?”
- `b833411b-d566-40ac-9c29-d565e5c84049` (advisor): “Em cần kiểm tra tài liệu và thời điểm áp dụng trước khi xác nhận những tính năng chị hỏi.”
- `8e5234fa-ed01-49df-9429-6af8d9b706b9` (advisor): “Khi có đúng hai phiên bản, em sẽ gửi bảng đối chiếu kèm nguồn để chị và gia đình xem rồi mới quyết định bước tiếp.”
- **Lý do:** Làm rõ lý do chưa thể so giá/tính năng và đề xuất bảng so chuẩn để quyết định; không phản hồi hết băn khoăn trong hiện tại.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `b833411b-d566-40ac-9c29-d565e5c84049` (advisor): “Em cần kiểm tra tài liệu và thời điểm áp dụng trước khi xác nhận những tính năng chị hỏi.”
- `8e5234fa-ed01-49df-9429-6af8d9b706b9` (advisor): “Khi có đúng hai phiên bản, em sẽ gửi bảng đối chiếu kèm nguồn để chị và gia đình xem rồi mới quyết định bước tiếp.”
- **Lý do:** Nêu điều kiện phải kiểm tra tài liệu và thời điểm trước khi khẳng định trang bị; phù hợp nhiều cấu hình theo chính sách giá hiện hành.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `8e5234fa-ed01-49df-9429-6af8d9b706b9` (advisor): “Khi có đúng hai phiên bản, em sẽ gửi bảng đối chiếu kèm nguồn để chị và gia đình xem rồi mới quyết định bước tiếp.”
- `674b0588-9b97-4d80-9a5d-8417fc65d164` (customer): “Em có thể cho chị biết cụ thể về những trang bị an toàn và công nghệ của VF 7 so với CX-5 không? Chị muốn biết có đáng giá thêm 50 triệu không?”
- **Lý do:** Có đề xuất gửi bảng đối chiếu cụ thể, nhưng nói “em sẽ gửi” chứ không hỏi khách có đồng ý, không hẹn kênh/thời điểm; yêu cầu tiếp diễn chưa được xác nhận.
- **Cần cải thiện để đạt mức cao hơn:** Xin phép khách về một hành động cụ thể theo đúng mức sẵn sàng; nêu kênh, thời điểm hoặc người thực hiện.

**Factual findings (phát biểu đáng chú ý):**
- **SUPPORTED** — `b833411b-d566-40ac-9c29-d565e5c84049`: “Em cần kiểm tra tài liệu và thời điểm áp dụng trước khi xác nhận những tính năng chị hỏi.”
  - Nhận định: Cần đối chiếu phiên bản/trang bị theo tài liệu và thời điểm để tránh nhầm lẫn.
  - Source IDs/versions: `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`).
  - Trích nguồn — `PRICE_LIST_VINFAST_20260921`: “Giá bán bán lẻ đề xuất (MSRP) kèm pin, bao gồm VAT”
  - Trích nguồn — `FAQ_VF7_20260922`: “VF 7”

---

### JH26_12_VF7_12 — SCENARIO_02_VF7_VS_CX5 (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `3/5`. **Overall score:** `1.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `1ce2c840-344f-4990-a1d5-1bde3f021346` (customer): “Chị thấy VF 7 và CX-5 cũng tương tự nhau, nhưng tại sao VF 7 lại đắt hơn 50 triệu? Có điểm gì nổi bật hơn không?”
- `1f83ec2e-9f88-4ede-9580-967d754bb36a` (advisor): “VF 7 có thiết kế ngoại thất khá nổi bật và khoang lái hiện đại chị ạ.”
- `8126a684-a573-4fb8-86c5-99d45df8cf0b` (customer): “Em thấy CX-5 đi đầy đường, vừa đẹp vừa bền, trong khi VF 7 mới ra chưa biết thế nào mà giá lại cao hơn. Có lý do gì thuyết phục không?”
- `d5b4249c-465e-4b43-b51e-bdc51c27b048` (advisor): “Xe có nhiều màn hình, nhiều tiện nghi và cũng có các tính năng hỗ trợ người lái.”
- **Lý do:** Không hỏi khách ưu tiên công nghệ, chi phí hay gia đình; kể chung chung thiết kế và tiện nghi.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `1ce2c840-344f-4990-a1d5-1bde3f021346` (customer): “Chị thấy VF 7 và CX-5 cũng tương tự nhau, nhưng tại sao VF 7 lại đắt hơn 50 triệu? Có điểm gì nổi bật hơn không?”
- `1f83ec2e-9f88-4ede-9580-967d754bb36a` (advisor): “VF 7 có thiết kế ngoại thất khá nổi bật và khoang lái hiện đại chị ạ.”
- `8126a684-a573-4fb8-86c5-99d45df8cf0b` (customer): “Em thấy CX-5 đi đầy đường, vừa đẹp vừa bền, trong khi VF 7 mới ra chưa biết thế nào mà giá lại cao hơn. Có lý do gì thuyết phục không?”
- `d5b4249c-465e-4b43-b51e-bdc51c27b048` (advisor): “Xe có nhiều màn hình, nhiều tiện nghi và cũng có các tính năng hỗ trợ người lái.”
- **Lý do:** Nêu feature chung chung, không định danh bản VF 7, không so có căn cứ với CX-5; “nhiều màn hình” thiếu đối chiếu kỹ thuật rõ.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRODUCT_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `8126a684-a573-4fb8-86c5-99d45df8cf0b` (customer): “Em thấy CX-5 đi đầy đường, vừa đẹp vừa bền, trong khi VF 7 mới ra chưa biết thế nào mà giá lại cao hơn. Có lý do gì thuyết phục không?”
- `d5b4249c-465e-4b43-b51e-bdc51c27b048` (advisor): “Xe có nhiều màn hình, nhiều tiện nghi và cũng có các tính năng hỗ trợ người lái.”
- `13ea9039-6557-4e7c-b84d-1c9003f31198` (customer): “Em vẫn thấy CX-5 đi đầy đường, vừa đẹp vừa bền, trong khi VF 7 mới ra chưa biết thế nào mà giá lại cao hơn. Có lý do gì thuyết phục không?”
- **Lý do:** Khách lo giá cao và độ bền, advisor chỉ nói nhiều tiện nghi/ADAS, không chỉ ra giá trị tương xứng hoặc kiểm tra lại băn khoăn.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `1f83ec2e-9f88-4ede-9580-967d754bb36a` (advisor): “VF 7 có thiết kế ngoại thất khá nổi bật và khoang lái hiện đại chị ạ.”
- `d5b4249c-465e-4b43-b51e-bdc51c27b048` (advisor): “Xe có nhiều màn hình, nhiều tiện nghi và cũng có các tính năng hỗ trợ người lái.”
- **Lý do:** Không có khẳng định chính sách/giá/ưu đãi cụ thể của advisor; khác biệt 50 triệu chỉ do khách đưa ra.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `13ea9039-6557-4e7c-b84d-1c9003f31198` (customer): “Em vẫn thấy CX-5 đi đầy đường, vừa đẹp vừa bền, trong khi VF 7 mới ra chưa biết thế nào mà giá lại cao hơn. Có lý do gì thuyết phục không?”
- **Lý do:** Cuộc trao đổi ngắn dừng ở câu hỏi tiếp của khách sau hai lượt tư vấn; chưa có giai đoạn thống nhất hành động tiếp theo.

**Factual findings (phát biểu đáng chú ý):**
- **UNVERIFIABLE** — `d5b4249c-465e-4b43-b51e-bdc51c27b048`: “Xe có nhiều màn hình, nhiều tiện nghi và cũng có các tính năng hỗ trợ người lái.”
  - Nhận định: Khái quát “nhiều màn hình” thiếu xác định phiên bản/hạng mục, KB không xác minh nhận định so sánh CX-5.
  - Source IDs/versions: `PRODUCT_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `PRODUCT_VF7_20260922`: “Các thông tin sản phẩm có thể thay đổi mà không cần báo trước.”
  - Nguồn xem bối cảnh (không chứng minh claim) — `FAQ_VF7_20260922`: “VF 7”

---

### JH26_13_VF7_13 — SCENARIO_02_VF7_VS_CX5 (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `2.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `90ec76e2-ccb9-4a4f-bf4c-3fc417d88927` (advisor): “Em hiểu chị thích trải nghiệm mới còn anh nhà muốn lựa chọn quen thuộc. Điều gì mỗi người lo nhất ạ?”
- `3a072e65-e474-4492-8b05-fd43c3ff6ee1` (advisor): “Những chuyến gia đình mình đi xa và việc sử dụng hàng ngày khác nhau thế nào để em chọn thông tin cần đối chiếu?”
- `c8219983-7f58-45a2-bda3-c64784ebf761` (customer): “Chồng chị bảo xe điện mua thì đắt mà sau 3 năm bán lại khéo lỗ nửa giá xe, không giữ giá bằng CX-5. Em có thể giải thích cho chị về điều này không?”
- `f242d78d-d309-4afb-947d-f717c93a9966` (advisor): “Nếu cả hai đồng ý, em mời anh chị cùng xem xe hoặc lái thử, mỗi người tự kiểm tra tiêu chí của mình.”
- `cd9208e6-4baf-4bca-a310-ece41df118d5` (advisor): “Chị muốn em gửi trước bảng câu hỏi và hẹn qua kênh nào để anh nhà cũng xem được?”
- **Lý do:** Nhận thấy có hai người quyết định và hỏi khác biệt sử dụng, sau đó đề xuất xem/lái thử cùng nhau; tuy nhiên ban đầu tự giả định ý thích của cả hai.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `712d092f-7cfd-427b-8baa-fa5f0cf61428` (customer): “Em có thể cho chị biết lý do cụ thể nào khiến VF 7 lại đắt hơn CX-5 không? Chị muốn hiểu rõ hơn về sự khác biệt giữa hai xe này.”
- `008c0c8b-ea8e-46af-87cc-5bf78420c4c9` (customer): “Chị muốn biết VF 7 có những tính năng công nghệ gì nổi bật hơn CX-5 không?”
- `b1a3eb9d-a7fc-4a91-b305-4a25634e3422` (advisor): “Em không thể bảo đảm giá bán lại sau ba năm; mình có thể cùng xem nguồn về chính sách hiện hành và đánh giá nhu cầu sử dụng.”
- `c8219983-7f58-45a2-bda3-c64784ebf761` (customer): “Chồng chị bảo xe điện mua thì đắt mà sau 3 năm bán lại khéo lỗ nửa giá xe, không giữ giá bằng CX-5. Em có thể giải thích cho chị về điều này không?”
- **Lý do:** Câu hỏi cụ thể về công nghệ VF 7 so CX-5 không được trả lời bằng tính năng hoặc nguồn; chuyển sang chủ đề giữ giá.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `PRODUCT_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `b1a3eb9d-a7fc-4a91-b305-4a25634e3422` (advisor): “Em không thể bảo đảm giá bán lại sau ba năm; mình có thể cùng xem nguồn về chính sách hiện hành và đánh giá nhu cầu sử dụng.”
- `c8219983-7f58-45a2-bda3-c64784ebf761` (customer): “Chồng chị bảo xe điện mua thì đắt mà sau 3 năm bán lại khéo lỗ nửa giá xe, không giữ giá bằng CX-5. Em có thể giải thích cho chị về điều này không?”
- `f242d78d-d309-4afb-947d-f717c93a9966` (advisor): “Nếu cả hai đồng ý, em mời anh chị cùng xem xe hoặc lái thử, mỗi người tự kiểm tra tiêu chí của mình.”
- `e17abb38-0850-4381-8f45-c46abb621d33` (customer): “Chị vẫn lo lắng về việc xe điện VF 7 sẽ mất giá nhanh hơn CX-5. Em có thể cho chị biết lý do tại sao lại như vậy không?”
- **Lý do:** Không hứa giữ giá, tiếp nhận lo ngại của chồng bằng phương án cả hai kiểm tra; vẫn chưa trình bày bằng chứng thị trường hoặc yêu cầu kiểm tra lại mức yên tâm.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `b1a3eb9d-a7fc-4a91-b305-4a25634e3422` (advisor): “Em không thể bảo đảm giá bán lại sau ba năm; mình có thể cùng xem nguồn về chính sách hiện hành và đánh giá nhu cầu sử dụng.”
- **Lý do:** Advisor chỉ tuyên bố không thể bảo đảm giá bán lại và đề nghị xem nguồn sau; không xác quyết điều khoản/ưu đãi hay tỷ lệ hoàn vốn được duyệt.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `c8219983-7f58-45a2-bda3-c64784ebf761` (customer): “Chồng chị bảo xe điện mua thì đắt mà sau 3 năm bán lại khéo lỗ nửa giá xe, không giữ giá bằng CX-5. Em có thể giải thích cho chị về điều này không?”
- `f242d78d-d309-4afb-947d-f717c93a9966` (advisor): “Nếu cả hai đồng ý, em mời anh chị cùng xem xe hoặc lái thử, mỗi người tự kiểm tra tiêu chí của mình.”
- `e17abb38-0850-4381-8f45-c46abb621d33` (customer): “Chị vẫn lo lắng về việc xe điện VF 7 sẽ mất giá nhanh hơn CX-5. Em có thể cho chị biết lý do tại sao lại như vậy không?”
- `cd9208e6-4baf-4bca-a310-ece41df118d5` (advisor): “Chị muốn em gửi trước bảng câu hỏi và hẹn qua kênh nào để anh nhà cũng xem được?”
- **Lý do:** Mời cả hai cùng xem/lái thử, rồi hỏi kênh gửi thông tin để chồng cùng xem, tạo bước cam kết vừa phải cho quyết định chung.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_14_VF7_14 — SCENARIO_02_VF7_VS_CX5 (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `5/5`. **Overall score:** `1.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `b0cd5cdb-6085-46c7-ba38-f518408e4a6a` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `a029baec-4920-4bc6-bb09-cbd7a7657508` (advisor): “Chị chưa muốn đặt lịch cũng được, nhưng em nghĩ chị nên cọc ngay hôm nay.”
- `dd987cdf-133f-4fdf-a8c6-cf713cb1aa7a` (customer): “Chồng chị bảo xe điện mua thì đắt mà sau 3 năm bán lại khéo lỗ nửa giá xe, không giữ giá bằng CX-5. Em có thể giải thích cho chị lý do không?”
- `f187e31d-242f-4ec2-b0e2-02d3964f28fd` (advisor): “Nếu không cọc bây giờ thì chị sẽ bỏ lỡ cơ hội; mình khỏi cần bàn thêm về điều anh nhà đang lo.”
- **Lý do:** Không hỏi tiêu chí so CX-5, điều chồng lo hay phiên bản; mặc định khách phải đặt cọc.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `b0cd5cdb-6085-46c7-ba38-f518408e4a6a` (customer): “Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn 50 triệu vậy em?”
- `dd987cdf-133f-4fdf-a8c6-cf713cb1aa7a` (customer): “Chồng chị bảo xe điện mua thì đắt mà sau 3 năm bán lại khéo lỗ nửa giá xe, không giữ giá bằng CX-5. Em có thể giải thích cho chị lý do không?”
- `f187e31d-242f-4ec2-b0e2-02d3964f28fd` (advisor): “Nếu không cọc bây giờ thì chị sẽ bỏ lỡ cơ hội; mình khỏi cần bàn thêm về điều anh nhà đang lo.”
- `0d126ba0-0367-4f60-9e19-dddd6ef41d69` (advisor): “Em gửi ngay đường dẫn đặt cọc, chị hoàn tất trước rồi hãy xem xe sau.”
- **Lý do:** Không cung cấp bất kỳ thông tin VF 7 hay phân tích giữ giá có căn cứ, thay bằng link đặt cọc.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRICE_LIST_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `PRODUCT_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`); `FAQ_VF7_20260922` / `2026.09.22` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `dd987cdf-133f-4fdf-a8c6-cf713cb1aa7a` (customer): “Chồng chị bảo xe điện mua thì đắt mà sau 3 năm bán lại khéo lỗ nửa giá xe, không giữ giá bằng CX-5. Em có thể giải thích cho chị lý do không?”
- `f187e31d-242f-4ec2-b0e2-02d3964f28fd` (advisor): “Nếu không cọc bây giờ thì chị sẽ bỏ lỡ cơ hội; mình khỏi cần bàn thêm về điều anh nhà đang lo.”
- `470dab81-03c8-4257-b108-928a5c4b138f` (customer): “Em có thể cho chị biết lý do tại sao xe điện VF 7 lại có giá trị giữ giá tốt hơn CX-5 không?”
- `0d126ba0-0367-4f60-9e19-dddd6ef41d69` (advisor): “Em gửi ngay đường dẫn đặt cọc, chị hoàn tất trước rồi hãy xem xe sau.”
- **Lý do:** Khách nhiều lần hỏi về nguy cơ mất giá; advisor công khai né vấn đề và liên tục thúc ép thanh toán.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `a029baec-4920-4bc6-bb09-cbd7a7657508` (advisor): “Chị chưa muốn đặt lịch cũng được, nhưng em nghĩ chị nên cọc ngay hôm nay.”
- `f187e31d-242f-4ec2-b0e2-02d3964f28fd` (advisor): “Nếu không cọc bây giờ thì chị sẽ bỏ lỡ cơ hội; mình khỏi cần bàn thêm về điều anh nhà đang lo.”
- `0d126ba0-0367-4f60-9e19-dddd6ef41d69` (advisor): “Em gửi ngay đường dẫn đặt cọc, chị hoàn tất trước rồi hãy xem xe sau.”
- **Lý do:** Tạo khan hiếm/khẩn cấp khi không nêu chính sách hay hạn chót đang hiệu lực; đẩy khách vào đặt cọc ràng buộc trước khi được giải thích.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `PROMOTION_SALES_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `POLICY_DEPOSIT_TERMS_20260922` / `2026.09.22` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `a029baec-4920-4bc6-bb09-cbd7a7657508` (advisor): “Chị chưa muốn đặt lịch cũng được, nhưng em nghĩ chị nên cọc ngay hôm nay.”
- `f187e31d-242f-4ec2-b0e2-02d3964f28fd` (advisor): “Nếu không cọc bây giờ thì chị sẽ bỏ lỡ cơ hội; mình khỏi cần bàn thêm về điều anh nhà đang lo.”
- `0d126ba0-0367-4f60-9e19-dddd6ef41d69` (advisor): “Em gửi ngay đường dẫn đặt cọc, chị hoàn tất trước rồi hãy xem xe sau.”
- **Lý do:** Đề nghị cọc ngay dù khách chưa sẵn sàng và còn phản đối; bỏ qua xin đồng ý cho bước thông tin/lái thử phù hợp.
- **Cần cải thiện để đạt mức cao hơn:** Xin phép khách về một hành động cụ thể theo đúng mức sẵn sàng; nêu kênh, thời điểm hoặc người thực hiện.

**Factual findings (phát biểu đáng chú ý):**
- **UNVERIFIABLE** — `a029baec-4920-4bc6-bb09-cbd7a7657508`: “Chị chưa muốn đặt lịch cũng được, nhưng em nghĩ chị nên cọc ngay hôm nay.”
  - Nhận định: Không có thông tin hạn cọc cụ thể để xác minh rằng phải cọc ngay hôm nay.
  - Source IDs/versions: `PROMOTION_SALES_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `POLICY_DEPOSIT_TERMS_20260922` / `2026.09.22` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `PROMOTION_SALES_VINFAST_20260921`: “Các dòng VF 7, VF 9, VF 8 Thế hệ mới, Lạc Hồng 900 LX, EC Van & VF Wild: Ưu đãi 5% MSRP.”
  - Nguồn xem bối cảnh (không chứng minh claim) — `POLICY_DEPOSIT_TERMS_20260922`: “thỏa thuận đặt cọc có hiệu lực pháp lý ràng buộc Khách Hàng và VinFast Trading”
- **UNVERIFIABLE** — `f187e31d-242f-4ec2-b0e2-02d3964f28fd`: “Nếu không cọc bây giờ thì chị sẽ bỏ lỡ cơ hội; mình khỏi cần bàn thêm về điều anh nhà đang lo.”
  - Nhận định: Không có chương trình cụ thể chứng minh khách mất quyền lợi nếu không cọc ngay.
  - Source IDs/versions: `PROMOTION_SALES_VINFAST_20260921` / `2026.09.21` (trạng thái KB: `active`); `POLICY_DEPOSIT_TERMS_20260922` / `2026.09.22` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `PROMOTION_SALES_VINFAST_20260921`: “Các dòng VF 7, VF 9, VF 8 Thế hệ mới, Lạc Hồng 900 LX, EC Van & VF Wild: Ưu đãi 5% MSRP.”
  - Nguồn xem bối cảnh (không chứng minh claim) — `POLICY_DEPOSIT_TERMS_20260922`: “thỏa thuận đặt cọc có hiệu lực pháp lý ràng buộc Khách Hàng và VinFast Trading”

---

### JH26_15_VF6_15 — SCENARIO_03_VF6_APARTMENT (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `2.50`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `c871432d-cfc6-4a2c-870e-81b69e6905eb` (advisor): “Anh đi khoảng bao nhiêu km mỗi ngày và xe thường đỗ ở khu nào ạ?”
- `93584414-b7e6-4c13-9110-1dc4337b6164` (customer): “Anh thường đi khoảng 20-30 km mỗi ngày, xe thường đỗ ở bãi đỗ chung của chung cư. Vậy có cách nào để sạc xe không?”
- `1c3bf298-b229-4d19-bde2-ef16a7ba9cdf` (advisor): “Chung cư anh ở khu vực nào, và trên đường đi làm có điểm dừng nào thuận tiện không?”
- `3e2ebf0d-8647-4baa-8892-f12e1b641a90` (customer): “Chung cư của anh ở quận 1, nhưng không có trụ sạc nào gần đó. Vậy có cách nào để anh có thể sạc xe không?”
- `cadb20dd-beee-4968-87d0-c6be00ece625` (advisor): “Không có chỗ sạc riêng thì mình cần kiểm tra trạm công cộng gần nhà, gần chỗ làm và thời gian thực tế anh có thể dừng.”
- `bb55f883-4701-45b6-8e0e-73e2ff08eeac` (advisor): “Anh có muốn cùng em xem bản đồ trạm và chọn một phương án dự phòng trước khi quyết định xem VF 6 không?”
- **Lý do:** Từ 20–30 km/ngày và khu ở không có sạc chuyển thành kiểm tra trạm nhà/cơ quan và giờ dừng, cùng chọn phương án dự phòng.

#### 2. Product Knowledge — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `3e2ebf0d-8647-4baa-8892-f12e1b641a90` (customer): “Chung cư của anh ở quận 1, nhưng không có trụ sạc nào gần đó. Vậy có cách nào để anh có thể sạc xe không?”
- `cadb20dd-beee-4968-87d0-c6be00ece625` (advisor): “Không có chỗ sạc riêng thì mình cần kiểm tra trạm công cộng gần nhà, gần chỗ làm và thời gian thực tế anh có thể dừng.”
- `6f5a1f4c-ed9e-4b19-b69e-9ebb5a05a5e5` (advisor): “Em chưa dám bảo đảm trạm nào luôn còn chỗ; em sẽ hướng dẫn anh tra tình trạng và thử một tuyến sạc phù hợp.”
- **Lý do:** Đưa giải pháp kiểm tra trạm công cộng và thời gian sạc thực tế, không khẳng định có chỗ; chưa xác minh điểm sạc cụ thể phù hợp.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `FAQ_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `ecd4fc30-612f-4230-843b-143c29186393` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `6f5a1f4c-ed9e-4b19-b69e-9ebb5a05a5e5` (advisor): “Em chưa dám bảo đảm trạm nào luôn còn chỗ; em sẽ hướng dẫn anh tra tình trạng và thử một tuyến sạc phù hợp.”
- `6f4f7b30-0cc7-49e2-a488-51922e48129a` (customer): “Nếu không có trụ sạc gần nhà, thì có cách nào khác để anh có thể sạc xe không?”
- `bb55f883-4701-45b6-8e0e-73e2ff08eeac` (advisor): “Anh có muốn cùng em xem bản đồ trạm và chọn một phương án dự phòng trước khi quyết định xem VF 6 không?”
- **Lý do:** Thừa nhận khó bảo đảm chỗ sạc, đề nghị thử tuyến và phương án dự phòng; chưa có điểm sạc thật để khép lại lo ngại.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `cadb20dd-beee-4968-87d0-c6be00ece625` (advisor): “Không có chỗ sạc riêng thì mình cần kiểm tra trạm công cộng gần nhà, gần chỗ làm và thời gian thực tế anh có thể dừng.”
- `6f5a1f4c-ed9e-4b19-b69e-9ebb5a05a5e5` (advisor): “Em chưa dám bảo đảm trạm nào luôn còn chỗ; em sẽ hướng dẫn anh tra tình trạng và thử một tuyến sạc phù hợp.”
- **Lý do:** Advisor chỉ đề xuất quy trình tra trạm, không đưa claim về mức giá/ưu đãi/quyền được sạc hoặc điều khoản nào có thể đối chiếu.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `93584414-b7e6-4c13-9110-1dc4337b6164` (customer): “Anh thường đi khoảng 20-30 km mỗi ngày, xe thường đỗ ở bãi đỗ chung của chung cư. Vậy có cách nào để sạc xe không?”
- `ecd4fc30-612f-4230-843b-143c29186393` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `bb55f883-4701-45b6-8e0e-73e2ff08eeac` (advisor): “Anh có muốn cùng em xem bản đồ trạm và chọn một phương án dự phòng trước khi quyết định xem VF 6 không?”
- **Lý do:** Hỏi xin phép xem bản đồ và chọn phương án dự phòng trước khi quyết định xem VF 6, phù hợp sự ngần ngại vì thiếu sạc.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_16_VF6_16 — SCENARIO_03_VF6_APARTMENT (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `3/5`. **Overall score:** `1.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `f5a0fd29-e5c4-46c9-9ce5-a46f3e951471` (customer): “Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?”
- `7c374d95-5c66-41c8-9a90-480cf9356477` (advisor): “VF 6 có kiểu dáng năng động, anh nhìn ngoài đời sẽ thấy đẹp hơn ảnh.”
- `85a57f54-6d61-4fbe-9e38-e59cac23f976` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `4acb06b6-d5e0-4d71-be75-2051f3263e80` (advisor): “Nội thất của xe khá hiện đại và đi phố cũng tiện anh ạ.”
- **Lý do:** Không hỏi địa điểm, quãng đường hay thời gian rảnh để xem phương án sạc; kể mẫu mã/nội thất không liên quan.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `f5a0fd29-e5c4-46c9-9ce5-a46f3e951471` (customer): “Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?”
- `7c374d95-5c66-41c8-9a90-480cf9356477` (advisor): “VF 6 có kiểu dáng năng động, anh nhìn ngoài đời sẽ thấy đẹp hơn ảnh.”
- `4acb06b6-d5e0-4d71-be75-2051f3263e80` (advisor): “Nội thất của xe khá hiện đại và đi phố cũng tiện anh ạ.”
- `1e0ded4f-48c4-4e11-aedb-23d47fafdc6d` (customer): “Em có thể cho anh biết có những giải pháp nào cho việc sạc xe điện khi sống ở chung cư không có trụ sạc không?”
- **Lý do:** Không trả lời cách sạc ở chung cư hay giải pháp trạm công cộng; chỉ quảng bá thiết kế.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `85a57f54-6d61-4fbe-9e38-e59cac23f976` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `4acb06b6-d5e0-4d71-be75-2051f3263e80` (advisor): “Nội thất của xe khá hiện đại và đi phố cũng tiện anh ạ.”
- `1e0ded4f-48c4-4e11-aedb-23d47fafdc6d` (customer): “Em có thể cho anh biết có những giải pháp nào cho việc sạc xe điện khi sống ở chung cư không có trụ sạc không?”
- **Lý do:** Bỏ qua lo phải tìm trụ khi về nhà, tiếp tục nói nội thất thay vì giải quyết bất tiện.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `7c374d95-5c66-41c8-9a90-480cf9356477` (advisor): “VF 6 có kiểu dáng năng động, anh nhìn ngoài đời sẽ thấy đẹp hơn ảnh.”
- `4acb06b6-d5e0-4d71-be75-2051f3263e80` (advisor): “Nội thất của xe khá hiện đại và đi phố cũng tiện anh ạ.”
- **Lý do:** Không có claim chính sách, quyền lợi hoặc đơn giá; việc không trả lời bài toán sạc bị chấm ở Product Knowledge và Objection Handling.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `1e0ded4f-48c4-4e11-aedb-23d47fafdc6d` (customer): “Em có thể cho anh biết có những giải pháp nào cho việc sạc xe điện khi sống ở chung cư không có trụ sạc không?”
- **Lý do:** Đoạn ngắn bị ngắt ở câu hỏi giải pháp sạc của khách, chưa xuất hiện thời điểm thảo luận bước tiếp theo đủ để kết luận.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_17_VF6_17 — SCENARIO_03_VF6_APARTMENT (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `1.00`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `794a513d-8974-48b9-b5a6-1db160856471` (customer): “Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?”
- `aba11f34-6d5f-4e10-8070-2cc9693032b8` (advisor): “Anh hoàn toàn không cần quan tâm thời gian sạc, xe lúc nào cũng đủ pin để đi cả tuần.”
- `f7866b36-b96f-4b36-b574-cc40db1a72a7` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `2c5a3152-a644-4e62-a9f7-0d6ecf8081a7` (advisor): “Không có trụ ở chung cư vẫn chắc chắn không bao giờ bất tiện, em bảo đảm.”
- **Lý do:** Không tìm hiểu km/ngày, vị trí trạm hay khả năng đỗ; mặc định pin luôn đủ cho một tuần.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `794a513d-8974-48b9-b5a6-1db160856471` (customer): “Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?”
- `aba11f34-6d5f-4e10-8070-2cc9693032b8` (advisor): “Anh hoàn toàn không cần quan tâm thời gian sạc, xe lúc nào cũng đủ pin để đi cả tuần.”
- `f7866b36-b96f-4b36-b574-cc40db1a72a7` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `2c5a3152-a644-4e62-a9f7-0d6ecf8081a7` (advisor): “Không có trụ ở chung cư vẫn chắc chắn không bao giờ bất tiện, em bảo đảm.”
- **Lý do:** Cam kết luôn đi đủ một tuần và không cần quan tâm sạc bất kể hoàn cảnh; trái với tính phụ thuộc vào quãng đường/điều kiện sử dụng.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `FAQ_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `f7866b36-b96f-4b36-b574-cc40db1a72a7` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `2c5a3152-a644-4e62-a9f7-0d6ecf8081a7` (advisor): “Không có trụ ở chung cư vẫn chắc chắn không bao giờ bất tiện, em bảo đảm.”
- **Lý do:** Phủ nhận tuyệt đối bất tiện của khách không có trụ, không đề xuất phương án có thể kiểm tra.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `aba11f34-6d5f-4e10-8070-2cc9693032b8` (advisor): “Anh hoàn toàn không cần quan tâm thời gian sạc, xe lúc nào cũng đủ pin để đi cả tuần.”
- `2c5a3152-a644-4e62-a9f7-0d6ecf8081a7` (advisor): “Không có trụ ở chung cư vẫn chắc chắn không bao giờ bất tiện, em bảo đảm.”
- **Lý do:** Đưa bảo đảm vô điều kiện về khả năng sử dụng và tiếp cận sạc mà không có giới hạn hoặc căn cứ; là lời hứa rủi ro, không phải điều khoản VinFast xác thực.
- **Cần cải thiện để đạt mức cao hơn:** Kiểm tra văn bản hiện hành, điều kiện áp dụng và ngoại lệ trước mọi cam kết giá/quyền lợi.
- **Nguồn đối chiếu:** `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 5. Closing / Next Step — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `9b128056-a298-490c-b1cf-be216e0deaf5` (customer): “Em có thể cho anh biết thêm về các giải pháp sạc pin nào có thể áp dụng cho chung cư không có trụ sạc không?”
- **Lý do:** Đoạn dừng trước khi advisor trả lời yêu cầu cụ thể tiếp theo; không có giai đoạn rõ ràng để đánh giá bước chốt.

**Factual findings (phát biểu đáng chú ý):**
- **UNVERIFIABLE** — `aba11f34-6d5f-4e10-8070-2cc9693032b8`: “Anh hoàn toàn không cần quan tâm thời gian sạc, xe lúc nào cũng đủ pin để đi cả tuần.”
  - Nhận định: Không có mức km hằng ngày và điều kiện vận hành để hứa pin đủ mọi lúc cho cả tuần.
  - Source IDs/versions: `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `FAQ_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `PRODUCT_VF6_20260922`: “Quãng đường di chuyển thực tế có thể giảm so với kết quả kiểm định”
  - Nguồn xem bối cảnh (không chứng minh claim) — `FAQ_VF6_20260922`: “VF 6”
- **UNVERIFIABLE** — `2c5a3152-a644-4e62-a9f7-0d6ecf8081a7`: “Không có trụ ở chung cư vẫn chắc chắn không bao giờ bất tiện, em bảo đảm.”
  - Nhận định: Sự bất tiện của trạm sạc không thể bảo đảm “không bao giờ” chỉ từ thông số xe.
  - Source IDs/versions: `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`).
  - Nguồn xem bối cảnh (không chứng minh claim) — `PRODUCT_VF6_20260922`: “Quãng đường di chuyển thực tế có thể giảm so với kết quả kiểm định”

---

### JH26_18_VF6_18 — SCENARIO_03_VF6_APARTMENT (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `2.25`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `2a2f6199-d63f-4286-82c8-90b76af90eb6` (customer): “Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?”
- `2c6aedb3-13a9-4be0-b967-4cbea45d0f7a` (advisor): “Anh thường đi bao nhiêu km một ngày và hầm chung cư có cho đỗ xe điện không ạ?”
- `c591a789-74f1-40fb-a699-a996ca011f81` (customer): “Nếu không có chỗ lắp sạc riêng, anh có thể sạc ở đâu? Có trạm sạc công cộng gần nhà không?”
- `ec46f0e2-7669-484a-9320-8d34ad7e1839` (advisor): “Anh ở khu nào và đi làm theo tuyến nào để mình tìm trạm gần cả nhà lẫn cơ quan?”
- `86cfcb74-a113-4197-9028-2cc52ba294d5` (advisor): “Em có thể cùng anh kiểm tra điểm sạc trên tuyến chính, thời gian di chuyển và tình trạng trạm, nhưng không dám nói chắc luôn có chỗ.”
- `2a91d5a6-b212-4793-891a-4854e8623273` (advisor): “Nếu trạm gần nhà bận, mình nên có điểm dự phòng gần nơi làm hoặc gần chỗ anh thường ghé.”
- **Lý do:** Hỏi quãng đường, điều kiện đỗ và tuyến đường, nhưng chưa có câu trả lời cá nhân hóa đầy đủ trước khi lập đề xuất dự phòng.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `c591a789-74f1-40fb-a699-a996ca011f81` (customer): “Nếu không có chỗ lắp sạc riêng, anh có thể sạc ở đâu? Có trạm sạc công cộng gần nhà không?”
- `86cfcb74-a113-4197-9028-2cc52ba294d5` (advisor): “Em có thể cùng anh kiểm tra điểm sạc trên tuyến chính, thời gian di chuyển và tình trạng trạm, nhưng không dám nói chắc luôn có chỗ.”
- `3542095c-dc12-451a-9266-b52a14fbf70f` (customer): “Nếu không có chỗ lắp sạc riêng, anh có thể sạc ở đâu? Có trạm sạc công cộng gần nhà không?”
- `2a91d5a6-b212-4793-891a-4854e8623273` (advisor): “Nếu trạm gần nhà bận, mình nên có điểm dự phòng gần nơi làm hoặc gần chỗ anh thường ghé.”
- **Lý do:** Giải thích hợp lý việc kiểm tra trạm/tuyến, đưa điểm dự phòng và không hứa còn chỗ; chưa xác định tuyến trạm thực tế.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `3542095c-dc12-451a-9266-b52a14fbf70f` (customer): “Nếu không có chỗ lắp sạc riêng, anh có thể sạc ở đâu? Có trạm sạc công cộng gần nhà không?”
- `2a91d5a6-b212-4793-891a-4854e8623273` (advisor): “Nếu trạm gần nhà bận, mình nên có điểm dự phòng gần nơi làm hoặc gần chỗ anh thường ghé.”
- `a21e17c3-b4c6-4d9f-9fe0-775b002e518e` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `53dbe48a-e27e-457c-844c-9fbfa720a1d4` (advisor): “Anh muốn em gửi hai phương án để anh thử trực tiếp một lần trước khi quyết định mua không?”
- **Lý do:** Đưa phương án trạm thay thế và thử trực tiếp, nhưng chưa khai thác lịch buổi tối khiến khách thấy bất tiện hay hỏi mức yên tâm.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `86cfcb74-a113-4197-9028-2cc52ba294d5` (advisor): “Em có thể cùng anh kiểm tra điểm sạc trên tuyến chính, thời gian di chuyển và tình trạng trạm, nhưng không dám nói chắc luôn có chỗ.”
- `2a91d5a6-b212-4793-891a-4854e8623273` (advisor): “Nếu trạm gần nhà bận, mình nên có điểm dự phòng gần nơi làm hoặc gần chỗ anh thường ghé.”
- **Lý do:** Không khẳng định đơn giá, ưu đãi hoặc chính sách sạc; chỉ nhấn mạnh tính chưa biết của tình trạng trạm.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `a21e17c3-b4c6-4d9f-9fe0-775b002e518e` (customer): “Đi làm cả ngày mệt mỏi về tối lại phải lang thang đi tìm trụ sạc thì bất tiện quá em.”
- `53dbe48a-e27e-457c-844c-9fbfa720a1d4` (advisor): “Anh muốn em gửi hai phương án để anh thử trực tiếp một lần trước khi quyết định mua không?”
- `bb32b1cd-f0ab-41a2-93af-4f14d672b71c` (customer): “Em có thể cho anh biết thêm về hai phương án sạc mà em đề xuất không? Anh muốn thử nghiệm trước khi quyết định mua.”
- **Lý do:** Xin phép gửi hai phương án để khách thử thực tế trước khi mua, và khách phản hồi muốn tìm hiểu; đáp ứng mức sẵn sàng thăm dò.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_19_VF6_19 — SCENARIO_03_VF6_APARTMENT (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `2.25`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `97d03ca0-0230-4ef6-8809-fcf15e599f93` (advisor): “Anh muốn xem VF 6 nhưng đang lo sạc ở chung cư; anh thường đi bao nhiêu km mỗi ngày ạ?”
- `017fc664-ab01-4b82-97e2-df0c57fa0552` (customer): “Anh chỉ đi làm từ nhà tới cơ quan quanh quanh trong phố tầm 15 cây cả đi lẫn về thôi em. Anh ở chung cư bên mạn Cầu Giấy, gần ngay cái Vincom Trần Duy Hưng ấy.”
- `e89699f5-de16-46e8-a83c-539f6791f09e` (advisor): “Anh ở khu vực nào để mình kiểm tra trạm gần nhà và trên đường đi làm?”
- `c8fea55c-7052-49d9-9ced-5d072a8a5081` (customer): “Cách chung cư 800m có trạm sạc nhanh V-GREEN, nhưng anh vẫn lo lắng không biết có đủ tiện lợi không khi đi làm hàng ngày.”
- `9f845a65-9995-4cd3-9cf1-b1da15778fd5` (advisor): “Nếu anh thuận tiện, buổi xem xe mình kèm việc thử tra tuyến sạc thực tế để giải quyết đúng băn khoăn của anh.”
- **Lý do:** Hỏi km và bối cảnh chung cư, sử dụng vị trí/trạm gần và thói quen đi làm để đề xuất xem xe kèm tra sạc; hỏi lặp lại vị trí đã được khách cung cấp.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `c8fea55c-7052-49d9-9ced-5d072a8a5081` (customer): “Cách chung cư 800m có trạm sạc nhanh V-GREEN, nhưng anh vẫn lo lắng không biết có đủ tiện lợi không khi đi làm hàng ngày.”
- `acab747b-45aa-4dea-bf9a-e98c6e20b2c3` (advisor): “Em sẽ không hứa có trụ trống khi chưa xem dữ liệu; mình có thể kiểm tra cả một phương án dự phòng.”
- `e377aa73-31ee-42b2-b44f-caa6bb338bbe` (customer): “Nếu không có trụ sạc riêng, anh có thể sạc ở trạm V-GREEN gần đó, nhưng anh vẫn lo không biết có đủ thời gian và tiện lợi không khi đi làm hàng ngày.”
- `9f845a65-9995-4cd3-9cf1-b1da15778fd5` (advisor): “Nếu anh thuận tiện, buổi xem xe mình kèm việc thử tra tuyến sạc thực tế để giải quyết đúng băn khoăn của anh.”
- **Lý do:** Nhận định đúng cần kiểm tra trạm trống thay vì hứa chắc, gắn giải pháp với tuyến đi làm, chưa có dữ liệu trạm thực tế.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `c8fea55c-7052-49d9-9ced-5d072a8a5081` (customer): “Cách chung cư 800m có trạm sạc nhanh V-GREEN, nhưng anh vẫn lo lắng không biết có đủ tiện lợi không khi đi làm hàng ngày.”
- `acab747b-45aa-4dea-bf9a-e98c6e20b2c3` (advisor): “Em sẽ không hứa có trụ trống khi chưa xem dữ liệu; mình có thể kiểm tra cả một phương án dự phòng.”
- `e377aa73-31ee-42b2-b44f-caa6bb338bbe` (customer): “Nếu không có trụ sạc riêng, anh có thể sạc ở trạm V-GREEN gần đó, nhưng anh vẫn lo không biết có đủ thời gian và tiện lợi không khi đi làm hàng ngày.”
- `9f845a65-9995-4cd3-9cf1-b1da15778fd5` (advisor): “Nếu anh thuận tiện, buổi xem xe mình kèm việc thử tra tuyến sạc thực tế để giải quyết đúng băn khoăn của anh.”
- **Lý do:** Lắng nghe lo ngại về trạm và thời gian, đề xuất thử tra tuyến ngay buổi xem xe; chưa định lượng thời gian/trả lời đã yên tâm chưa.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `acab747b-45aa-4dea-bf9a-e98c6e20b2c3` (advisor): “Em sẽ không hứa có trụ trống khi chưa xem dữ liệu; mình có thể kiểm tra cả một phương án dự phòng.”
- `9f845a65-9995-4cd3-9cf1-b1da15778fd5` (advisor): “Nếu anh thuận tiện, buổi xem xe mình kèm việc thử tra tuyến sạc thực tế để giải quyết đúng băn khoăn của anh.”
- **Lý do:** Advisor không khẳng định chính sách/giá/ưu đãi; lời nói về chỗ trống được đặt điều kiện cần kiểm tra.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `3`

**Bằng chứng (nguyên văn):**
- `e377aa73-31ee-42b2-b44f-caa6bb338bbe` (customer): “Nếu không có trụ sạc riêng, anh có thể sạc ở trạm V-GREEN gần đó, nhưng anh vẫn lo không biết có đủ thời gian và tiện lợi không khi đi làm hàng ngày.”
- `9f845a65-9995-4cd3-9cf1-b1da15778fd5` (advisor): “Nếu anh thuận tiện, buổi xem xe mình kèm việc thử tra tuyến sạc thực tế để giải quyết đúng băn khoăn của anh.”
- `1eddc5ff-caa4-4a7b-8826-57e656249831` (customer): “Nếu em có thể giúp anh kiểm tra trạm sạc gần đó và thời gian sạc thực tế, anh sẽ cảm thấy yên tâm hơn khi quyết định mua xe.”
- `5be90383-b411-47f3-a180-8d5a0e21d66e` (advisor): “Anh có đồng ý nhận đề xuất thời gian xem xe qua kênh đang trao đổi này không? Nếu chưa tiện, em gửi bảng kiểm tra trạm trước.”
- **Lý do:** Cho lựa chọn xem xe kèm thử tra tuyến hoặc nhận bảng kiểm tra trước, hỏi đồng ý nhận lịch qua kênh hiện tại; không ép quyết định.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

### JH26_20_VF6_20 — SCENARIO_03_VF6_APARTMENT (v2.0)

- **Reviewer:** `CG` (đánh giá theo vai trò chuyên gia bằng AI). **Ngày:** `2026-10-17`. **Rubric:** `sales-rubric-v3`. **Coverage:** `4/5`. **Overall score:** `1.25`. **passed:** `null`.
- **Xác nhận độc lập:** `ĐÃ đánh giá độc lập`; không sử dụng điểm AI Judge. Xác minh/chữ ký chuyên gia là người thật: `CHƯA XÁC MINH`. Nhãn gốc/adjudication: `không có trong nguồn`.

#### 1. Need Discovery — `ASSESSED` / `2`

**Bằng chứng (nguyên văn):**
- `7d7ec921-b613-4be3-ac5f-eb8f56c383aa` (customer): “Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?”
- `8c86d7ad-e740-4b5d-aab0-9b887c0c3017` (advisor): “Anh đi làm mỗi ngày khoảng bao xa, và thường gửi xe ở khu nào ạ?”
- `2fb2b8a2-0559-484a-a19c-c4a226344979` (customer): “Anh chỉ đi làm từ nhà tới cơ quan quanh quanh trong phố tầm 15 cây cả đi lẫn về thôi em. Anh ở chung cư bên mạn Cầu Giấy, gần ngay cái Vincom Trần Duy Hưng ấy.”
- `f8c65d12-6192-49ed-8512-56c4cfc2ce07` (advisor): “Em hiểu anh đang bận; nếu muốn tạm dừng, lúc khác mình kiểm tra khu sạc gần nhà rồi nói tiếp.”
- **Lý do:** Tìm hiểu km/ngày và nơi gửi xe, nhưng kết luận khách bận chưa có căn cứ và không dùng khu vực Cầu Giấy để tư vấn sạc.
- **Cần cải thiện để đạt mức cao hơn:** Hỏi tiếp ràng buộc trọng yếu và sử dụng dữ liệu đó để điều chỉnh tư vấn cụ thể.

#### 2. Product Knowledge — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `7d7ec921-b613-4be3-ac5f-eb8f56c383aa` (customer): “Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?”
- `2fb2b8a2-0559-484a-a19c-c4a226344979` (customer): “Anh chỉ đi làm từ nhà tới cơ quan quanh quanh trong phố tầm 15 cây cả đi lẫn về thôi em. Anh ở chung cư bên mạn Cầu Giấy, gần ngay cái Vincom Trần Duy Hưng ấy.”
- `f8c65d12-6192-49ed-8512-56c4cfc2ce07` (advisor): “Em hiểu anh đang bận; nếu muốn tạm dừng, lúc khác mình kiểm tra khu sạc gần nhà rồi nói tiếp.”
- **Lý do:** Khách hỏi cách sạc khi chung cư không có trụ; sau khi biết địa bàn, advisor vẫn không cho hướng dẫn trạm/tuyến hay cách xác minh.
- **Cần cải thiện để đạt mức cao hơn:** Trả lời câu hỏi sản phẩm bằng thông tin/giới hạn đúng phiên bản có nguồn; với thiếu nguồn phải nói rõ phần cần xác minh.
- **Nguồn đối chiếu:** `PRODUCT_VF6_20260922` / `2026.09.22` (trạng thái KB: `active`); `CHARGING_TARIFF_VINFAST_20261004` / `2026.10.04` (trạng thái KB: `active`).

#### 3. Objection Handling — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `7d7ec921-b613-4be3-ac5f-eb8f56c383aa` (customer): “Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?”
- `f8c65d12-6192-49ed-8512-56c4cfc2ce07` (advisor): “Em hiểu anh đang bận; nếu muốn tạm dừng, lúc khác mình kiểm tra khu sạc gần nhà rồi nói tiếp.”
- `1b45f5b1-3791-4e30-a161-a7d5e6a0946a` (customer): “Nếu có trạm sạc nhanh V-GREEN ở Vincom gần nhà, anh có thể sạc xe khi nào tiện. Nhưng em có thể cho anh biết thêm về thời gian sạc và chi phí không?”
- **Lý do:** Vội đề nghị tạm dừng dù khách chưa nói muốn dừng, không giải quyết rào cản sạc; khách tiếp tục hỏi thời gian/chi phí.
- **Cần cải thiện để đạt mức cao hơn:** Gọi đúng tên phản đối, phản hồi bằng lý do/bằng chứng hoặc kế hoạch xác minh, rồi hỏi lại mức yên tâm.

#### 4. Policy Accuracy — `UNASSESSED` / `null`

**Bằng chứng (nguyên văn):**
- `f8c65d12-6192-49ed-8512-56c4cfc2ce07` (advisor): “Em hiểu anh đang bận; nếu muốn tạm dừng, lúc khác mình kiểm tra khu sạc gần nhà rồi nói tiếp.”
- `1b45f5b1-3791-4e30-a161-a7d5e6a0946a` (customer): “Nếu có trạm sạc nhanh V-GREEN ở Vincom gần nhà, anh có thể sạc xe khi nào tiện. Nhưng em có thể cho anh biết thêm về thời gian sạc và chi phí không?”
- **Lý do:** Không có tuyên bố nào của advisor về đơn giá, chính sách sạc hoặc điều kiện ưu đãi; câu hỏi giá ở tin cuối chưa có lượt advisor để trả lời.
- **Nguồn đối chiếu:** Không phát sinh claim đủ xác định để kết luận từ KB; **không** suy diễn như claim được chứng thực.

#### 5. Closing / Next Step — `ASSESSED` / `1`

**Bằng chứng (nguyên văn):**
- `2fb2b8a2-0559-484a-a19c-c4a226344979` (customer): “Anh chỉ đi làm từ nhà tới cơ quan quanh quanh trong phố tầm 15 cây cả đi lẫn về thôi em. Anh ở chung cư bên mạn Cầu Giấy, gần ngay cái Vincom Trần Duy Hưng ấy.”
- `f8c65d12-6192-49ed-8512-56c4cfc2ce07` (advisor): “Em hiểu anh đang bận; nếu muốn tạm dừng, lúc khác mình kiểm tra khu sạc gần nhà rồi nói tiếp.”
- **Lý do:** Đề nghị “lúc khác” kiểm tra trạm quá mơ hồ, không xin thời gian/kênh và không gắn với nhu cầu thực đã nêu.
- **Cần cải thiện để đạt mức cao hơn:** Xin phép khách về một hành động cụ thể theo đúng mức sẵn sàng; nêu kênh, thời điểm hoặc người thực hiện.

**Factual findings (phát biểu đáng chú ý):**
- Không ghi nhận claim cần finding riêng ngoài các nhận định đã nêu ở 5 tiêu chí; nếu khách nêu chênh giá/lo ngại, đó không phải claim do advisor xác quyết.

---

## Danh mục nguồn đã sử dụng

| Document ID | Phiên bản | Trạng thái trong KB | Được dùng để đánh giá |
|---|---|---|---|
| `SPECS_VF5_PLUS_2026` | `2026.09.22` | `active` | Thông số kỹ thuật và khả năng vận hành VinFast VF 5 Plus |
| `CHARGING_TARIFF_VINFAST_20261004` | `2026.10.04` | `active` | Đơn giá sạc công cộng VinFast và tình trạng dịch vụ thuê pin ô tô |
| `POLICY_CHARGING_VINFAST_20260919` | `2026.09.19` | `active` | Thông báo Chính sách ưu đãi sạc pin cho các dòng xe ô tô điện VinFast tại Việt Nam |
| `PRICE_LIST_VINFAST_20260921` | `2026.09.21` | `active` | Thông báo Chính sách giá bán và trang bị tùy chọn các dòng xe ô tô điện VinFast Việt Nam |
| `FAQ_VF5_20260922` | `2026.09.22` | `active` | Câu hỏi thường gặp VinFast VF 5 |
| `PROMOTION_SALES_VINFAST_20260921` | `2026.09.21` | `active` | Thông báo Chính sách thúc đẩy bán hàng Ô tô điện VinFast tại Việt Nam |
| `FAQ_VF7_20260922` | `2026.09.22` | `active` | Câu hỏi thường gặp VinFast VF 7 |
| `PRODUCT_VF7_20260922` | `2026.09.22` | `active` | Xe VF 7 chính hãng - Giá bán, Ưu đãi mới nhất |
| `POLICY_DEPOSIT_TERMS_20260922` | `2026.09.22` | `active` | Điều khoản đặt cọc mua xe VinFast |
| `PRODUCT_VF6_20260922` | `2026.09.22` | `active` | Xe điện VinFast VF 6 - Thông số, giá bán và ưu đãi mới nhất |
| `FAQ_VF6_20260922` | `2026.09.22` | `active` | Câu hỏi thường gặp VinFast VF 6 |

**Lưu ý nguồn:** Bảng chỉ sử dụng tài liệu trạng thái `active` theo snapshot được cung cấp. Không lấy số liệu từ bản hết hiệu lực (`expired`) để áp dụng hiện tại. Tài liệu về CX-5, báo giá lăn bánh theo địa phương, lãi vay cá nhân và tình trạng trụ sạc thực tế **không có** trong 4 file; không đưa ra kết luận xác quyết cho các nội dung này.
