# SPEC — CV Trend Radar: Đồ thị tri thức và ứng dụng phân tích xu hướng nghiên cứu Thị giác máy tính

| Mục | Giá trị |
|---|---|
| Phiên bản | 0.3.2 (chờ A duyệt) |
| Ngày | 23/11/2026 (v0.3: 20/11) |
| Tác giả | B (Sntug), có tiếp nhận các đề xuất góp ý cho v0.2 |
| Người duyệt | A (TienHung229), giảng viên |
| Mô hình | Agile/Scrum rút gọn cho nhóm 2 người; kế hoạch triển khai ở `docs/PLAN_trend_app.md` |
| Ký hiệu | ✅ đã chốt · 🟡 chờ A chốt · ❓ cần xác nhận · ♻️ dùng lại từ Đề tài 30 · **[Lõi]** bắt buộc để nghiệm thu · **[Mở rộng]** làm khi lõi đã đạt |

**Mục tiêu demo.** Người xem chọn một chủ đề và thấy tỷ trọng bài thuộc chủ đề đó thay đổi qua các kỳ **của cùng một hội nghị**. Từ đó mở danh sách nhóm và tổ chức đang làm chủ đề, rồi lần theo đường đi trên đồ thị đến bài báo gốc và câu bằng chứng. Theo chiều ngược lại, người xem chọn một nhóm nổi bật và thấy nhóm đó đang nghiên cứu những gì.

**Phạm vi kết luận.** Mọi kết quả chỉ áp dụng cho mẫu bài main track CVPR/ICCV ở các kỳ đã thu. "Nổi bật" được định nghĩa bằng chỉ số tính trên mạng mẫu, không phải danh tiếng ngoài đời.

---

## 0. Ánh xạ thang điểm → sản phẩm

| Tiêu chí của đề | Điểm | Sản phẩm để giảng viên kiểm tra | Mục |
|---|---:|---|---|
| Thu thập, lựa chọn dữ liệu làm giàu | 0,5 | Danh sách kỳ, nguồn, quy tắc chọn mẫu, bảng số bài và độ phủ từng kỳ | §2, §4.1 |
| Nhận dạng thực thể | 0,5 | NER hai tầng (từ điển + luật ♻️, SLM), ví dụ đúng/sai, P/R/F1 trên tập kiểm tra giữ riêng | §4.2 |
| Nhận dạng quan hệ | 0,5 | Ba quan hệ NLP có câu bằng chứng, SLM xác minh ca mơ hồ | §4.3 |
| Đánh giá chất lượng đồ thị | 0,5 | Tập gold tách trước, P/R/F1, κ, audit mẫu cạnh ♻️, kiểm tra toàn vẹn | §4.4 |
| Thế giới nhỏ | 0,5 | Ba số khoảng cách (LCC, mọi cặp có đường đi, tỷ lệ cặp liên thông), so mạng tham chiếu | §5.1 |
| Xếp hạng node | 0,5 | PageRank có trọng số cho tác giả và tổ chức | §5.2 |
| Cộng đồng và hạt nhân | 0,5 | Louvain, modularity, main core (k-core), hạt nhân từng cộng đồng | §5.3 |
| SLM ≤ 9 tỷ tham số | 1,0 | Model card, cấu hình thực chạy, ví dụ đầu vào/đầu ra, đánh giá | §6.1 |
| Đồ thị tri thức + RAG (ưu tiên GraphRAG) | 0,5 | Schema Neo4j, truy xuất đường đi thật, ngữ cảnh đưa vào SLM, câu trả lời có nguồn | §6.2 |
| Ứng dụng multi-hop + biểu diễn đồ thị | 3,0 | Xu hướng cùng hội nghị, truy vấn hai chiều chủ đề ↔ nhóm, đồ thị con tương tác, embedding đồ thị | §6.3–§7 |
| Slide / trình bày / báo cáo / trả lời câu hỏi | 4 × 0,5 | Slide, báo cáo chuẩn arXiv, demo 5 phút, bộ câu hỏi dự kiến | §8 |

---

## 1. Dữ liệu nền và câu hỏi sản phẩm

### 1.1 Dữ liệu nền (snapshot A8, đã kiểm lại với repo ngày 20/11/2026)

| Chỉ số (700 bài) | Giá trị | Hệ quả thiết kế |
|---|---|---|
| Đồ thị | 4.182 node, 16.979 cạnh, 8 nhãn, 10 quan hệ | Dùng lại schema |
| Mạng đồng tác giả | 2.950 tác giả, 7.771 cạnh, 416 thành phần liên thông | Mạng phân mảnh, phải báo cáo khoảng cách theo §5.1 |
| LCC | 502 tác giả (17%) | Không được kết luận thế giới nhỏ chỉ từ LCC |
| Hệ số gom cụm | 0,92 | Bị thổi phồng vì mỗi bài tạo một clique |
| Louvain trên LCC | 19 cộng đồng, Q = 0,87 | Dùng lại được |
| CITES trong tập lõi | 97 cạnh | Không xếp hạng bài theo trích dẫn |
| Affiliation theo bài | `authorships.csv` có (paper_id, author_id, institution_id); cạnh AFFILIATED_WITH có `paper_ids` | Truy vấn affiliation đúng theo từng bài là khả thi |

Mọi kết quả của bản mở rộng phải tính lại trên snapshot mới.

### 1.2 Câu hỏi sản phẩm

| Câu hỏi | Người dùng nhận được |
|---|---|
| Chủ đề nào phổ biến, tăng, giảm, mới nổi? | x/n, tỷ trọng từng kỳ, chênh lệch theo điểm phần trăm, mức độ chắc chắn |
| Nhóm nổi bật đang làm gì? | Nhóm, cách xếp hạng, hạt nhân, chủ đề chính trong kỳ, bài minh họa |
| Ai đang nghiên cứu chủ đề k? | Nhóm và tổ chức, số bài riêng biệt, đường đi và bằng chứng |

### 1.3 Không làm

Dự báo tương lai; fine-tune SLM; deploy có tài khoản người dùng; thu toàn bộ kỷ yếu; sửa các lỗi danh tính đã biết của A8 (chỉ đo và báo cáo); thêm nhãn hoặc quan hệ ngoài contract.

---

## 2. Kỳ hội nghị và cách so sánh

### 2.1 Các kỳ

| Kỳ | Trạng thái | Người thu |
|---|---|---|
| ICCV 2023 | ✅ ♻️ 350 bài | B |
| CVPR 2024 | ✅ ♻️ 350 bài | A |
| CVPR 2025 | ⬜ 350 bài | A |
| CVPR 2026 | ⬜ 350 bài | A |
| ICCV 2025 | ⬜ 350 bài | B |

Tổng mục tiêu: 1.750 bài, 5 kỳ, **2 hội nghị**, 4 năm.

### 2.2 Ba phép so sánh (thay cho Early/Late của v0.2)

| Phép so sánh | Kỳ | Trả lời câu hỏi | Vai trò |
|---|---|---|---|
| **Chuỗi CVPR** | 2024 → 2025 → 2026 | Chủ đề tăng/giảm; bảng chính là cặp 2025→2026, 2024 cho biết mức tăng kéo dài hay mới xuất hiện | **[Lõi]** bảng xếp hạng chính |
| **Cặp ICCV** | 2023 → 2025 | Thay đổi giữa hai kỳ ICCV | **[Lõi]** bảng phụ |
| **Hai hội nghị cùng năm** | CVPR 2025 vs ICCV 2025 | Chủ đề nào phổ biến hơn ở hội nghị nào | **[Lõi]** quan sát riêng, không dùng để gắn nhãn xu hướng |

**Lý do bỏ Early/Late làm cơ sở kết luận:** CVPR chiếm 1/2 số kỳ ở Early nhưng 2/3 ở Late. Một chủ đề vốn phổ biến ở CVPR sẽ trông như đang tăng dù tỷ trọng trong từng hội nghị đứng yên. Early/Late chỉ còn dùng để mô tả quy mô.

**Hạ phạm vi khi thiếu dữ liệu.** Nếu đến ngày đóng dữ liệu có kỳ chưa đủ hoặc chưa xác minh, app xuất số thực thu và chỉ trình bày các cặp so sánh được. Nếu chỉ còn ICCV 2023 và CVPR 2024, app chỉ hiển thị phân bố theo kỳ và không nghiệm thu câu hỏi tăng/giảm. **Vì vậy CVPR 2025 được ưu tiên thu đầu tiên** (tạo ngay một cặp với CVPR 2024).

### 2.3 Chọn mẫu

1. Lấy danh sách main track từng kỳ; loại workshop và trùng URL chuẩn trước khi chọn.
2. Dùng thuật toán của A: sắp theo SHA-256 của `seed + newline + canonical_url`, seed `20261103`, lấy 350 bài đầu.
3. Đối chiếu hai mẫu cũ, nhất là pilot ICCV 2023, với cùng quy tắc. Nếu khác, ghi rõ sai khác.
4. Lưu danh sách đầu vào, thứ tự chọn, lý do loại, số bài dùng thực tế. **Không thay bài thiếu abstract bằng bài khác.**

---

## 3. Quyết định kỹ thuật

| ID | Quyết định | Trạng thái |
|---|---|---|
| D1–D2 | 5 kỳ và quy tắc chọn mẫu §2; đóng băng danh sách bài mỗi kỳ trước khi tính metrics | 🟡 |
| D3 | Một từ điển Task/Method/Dataset `v3` cho mọi kỳ, mở rộng theo §4.2 | 🟡 |
| D4 | Danh tính tác giả: OpenAlex Author ID; lưu alias, nguồn, ca cần duyệt; kiểm tay các tác giả/tổ chức xuất hiện trong demo | 🟡 |
| D5 | Giữ 8 nhãn, 10 quan hệ. A kiểm tra khả năng dùng cấu hình project/venue mới (`mxh_cv_trend`, `venue:CVPR:2025:main`) mà không đổi schema; nếu phải đổi contract thì cần ví dụ nhập/xuất, test snapshot cũ, cả A và B duyệt | 🟡 |
| D6 | Biểu diễn đồ thị gồm hai phần: (a) đồ thị con tương tác có nhãn và hướng cạnh **[Lõi]**; (b) embedding FastRP/Node2Vec dùng để gợi ý top-5 **chủ đề** tương tự **[Lõi, bản tối thiểu]**; gợi ý nhóm tương tự là **[Mở rộng]** | 🟡 ❓ |
| D7–D8 | Streamlit + Plotly + pyvis + NetworkX + Neo4j. Cypher lấy đường đi thật; CSV/JSON giữ metrics tính sẵn; cả hai dùng chung một snapshot | 🟡 |
| D9 | Qwen3-8B (8,2 tỷ tham số) qua Ollama, tag `qwen3:8b` (Q4_K_M), **tắt thinking** (`think: false`); dự phòng `qwen3:4b` (Qwen3-4B, 4,0 tỷ), cùng họ nên dùng chung prompt. Pilot chỉ đo RAM, token/giây, % JSON hợp lệ để xác nhận, không chọn lại model | ✅ (23/11) |
| D10–D11 | GraphRAG local là luồng chính **[Lõi]**. Global search bằng tóm tắt cộng đồng **[Mở rộng ưu tiên 1]**. Vector index **[Mở rộng]** | 🟡 |

**Vì sao giữ embedding tối thiểu ở phần lõi (khác đề xuất v0.3 bản góp ý).** Tiêu chí 3 điểm ghi "multi-hop trên đồ thị **và biểu diễn đồ thị**". Cụm từ này có thể hiểu là trực quan hóa, cũng có thể hiểu là học biểu diễn (graph embedding). Bản tối thiểu (FastRP trên đồ thị Paper–Topic–Author, top-k chủ đề tương tự, một hình UMAP) tốn khoảng 1 ngày công và tránh được rủi ro mất điểm nếu giảng viên hiểu theo nghĩa thứ hai. Đánh giá link prediction/AUC và độ trôi Procrustes vẫn là phần mở rộng.

---

## 4. Phần I — Thu thập, làm giàu và kiểm tra đồ thị (2 điểm)

### 4.1 Nguồn và thống kê

| Nguồn | Dữ liệu |
|---|---|
| CVF Open Access ♻️ | Tiêu đề, tác giả, kỳ, URL, abstract |
| OpenAlex ♻️ | Author ID, tổ chức, quốc gia, tham chiếu |
| arXiv ♻️ | Abstract khi CVF thiếu, chỉ dùng khi đã xác minh đúng bài |

Mỗi kỳ xuất: số bài chọn, accepted, có văn bản phân tích được, khớp OpenAlex, có affiliation, có từng loại nhãn. Đối chiếu độ phủ giữa các kỳ **trước** khi diễn giải xu hướng.

### 4.2 Nhận dạng thực thể

| Tầng | Mô hình | Vai trò |
|---|---|---|
| T1 ♻️ | Từ điển + luật + bộ lọc ngữ cảnh spaCy (A4/B5) | Baseline |
| T2 | SLM trích thực thể từ abstract theo JSON schema, few-shot | Tìm khái niệm mới, tăng recall |
| T3 | Chuẩn hóa alias về ID từ điển `v3`; khái niệm chưa có vào hàng chờ duyệt | Đồng nhất ID qua các kỳ |

**Quy trình (thứ tự bắt buộc):**

1. **Chọn tập gold trước** (§4.4) và loại các bài gold khỏi mọi bước khai thác ứng viên.
2. SLM đề xuất ứng viên từ các bài **ngoài tập kiểm tra**.
3. A và B duyệt ứng viên có ≥ 5 lần xuất hiện; mỗi khái niệm có định nghĩa, alias, ví dụ.
4. Chọn cấu hình (T1, T2 hay kết hợp) trên **tập phát triển**.
5. Đóng băng từ điển `v3`, prompt, code và cách kết hợp; lưu sha256.
6. Chạy một cấu hình duy nhất trên mọi bài đủ điều kiện; lưu đầu ra SLM, lỗi, quyết định duyệt.
7. Sau cùng mới chấm trên **tập kiểm tra giữ riêng**.

### 4.3 Nhận dạng quan hệ

| Nguồn | Quan hệ | Quy tắc |
|---|---|---|
| Văn bản | STUDIES_TASK, USES_METHOD, EVALUATED_ON | Luật ngữ cảnh ♻️ tách việc thực sự nghiên cứu/sử dụng/đánh giá khỏi chỉ nhắc, phủ định, giả định; SLM phân loại ca mơ hồ. Mỗi cạnh có `derivation="nlp"`, `weight=1`, `text_version_id`, `start_char`, `end_char`, `evidence_text`; kiểm `text[start_char:end_char] == evidence_text` |
| Metadata | AUTHORED, AFFILIATED_WITH, BASED_IN, PUBLISHED_IN, CITES | Kiểm nguồn và hai đầu cạnh; giữ liên hệ tác giả–bài–tổ chức theo từng bài |
| Suy diễn | COAUTHORED_WITH, COLLABORATED_WITH | Trọng số = số bài lõi chung riêng biệt; truy ngược được tập `paper_ids` |

### 4.4 Đánh giá chất lượng

**Tập gold:** 20 abstract mỗi kỳ được giữ lại, chọn theo seed **trước khi mở rộng từ điển**: 5/kỳ làm tập phát triển, 15/kỳ làm tập kiểm tra giữ riêng. Đủ 5 kỳ: 100 bài (25 dev + 75 test); nếu chỉ còn 4 kỳ: 80 bài (20 dev + 60 test). A và B gán nhãn độc lập rồi mới hòa giải; ghi log bất đồng. Phần test chỉ được mở để gán nhãn sau khi từ điển, prompt và cấu hình đã đóng băng; không dùng làm few-shot hay pilot.

| Kiểm tra | Chỉ số nghiệm thu |
|---|---|
| NER | P/R/F1 theo loại và số mẫu, so khớp (span, loại); so baseline T1 với cấu hình đã chọn. Mục tiêu nội bộ F1 ≥ 0,80 |
| RE | P/R/F1 trên bộ (paper ID, loại cạnh, entity ID). Mục tiêu nội bộ precision ≥ 0,85 |
| Đồng thuận | κ cho quyết định phân loại trên danh sách ứng viên cố định; span-F1 giữa hai người báo riêng |
| Cạnh trong đồ thị | ≈ 10 cạnh/loại (hoặc tất cả nếu ít hơn), ghi đúng/tổng từng loại; tỷ lệ đúng toàn đồ thị = trung bình có trọng số theo số cạnh thực, kèm cỡ mẫu và độ bất định |
| Toàn vẹn | Không cạnh treo, offset hợp lệ, nạp hai lần cùng content hash, contract verify pass |

Nếu không đạt mục tiêu nội bộ: công bố kết quả, ví dụ lỗi và ảnh hưởng lên nhãn xu hướng. Không chỉnh cấu hình sau khi đã xem kết quả tập kiểm tra.

---

## 5. Phần II — Phân tích mạng xã hội (1,5 điểm)

### 5.1 Thế giới nhỏ

Đề yêu cầu "trung bình khoảng cách ngắn nhất **toàn mạng**", trong khi mạng rời rạc thì khoảng cách giữa hai thành phần là vô hạn. Vì vậy báo cáo đủ ba số trên mạng đồng tác giả vô hướng (khoảng cách tính theo số cạnh, giữ cả tác giả đứng riêng):

1. `L_LCC`: trung bình khoảng cách trong LCC.
2. `L_reach`: trung bình trên **mọi cặp có đường đi**. Với thành phần i có nᵢ node, Lᵢ có trọng số nᵢ(nᵢ−1)/2; thành phần đơn lẻ đóng góp 0 cặp.
3. `R`: tỷ lệ cặp có đường đi trên tổng số cặp N(N−1)/2.

Kèm số node, cạnh, số thành phần, tỷ lệ LCC, đường kính LCC, histogram khoảng cách.

**Mạng tham chiếu [Lõi]:** trên LCC, so L và C với 20 mạng ngẫu nhiên liên thông cùng dãy bậc (đổi cạnh giữ bậc và giữ liên thông), ghi số lần đổi thành công và phân bố kết quả. Báo σ = (C/C_rand)/(L/L_rand) khi xác định được.

**[Mở rộng]:** hoán đổi trên mạng hai phía tác giả–bài (giữ số tác giả mỗi bài và số bài mỗi tác giả) rồi chiếu lại, để tách riêng hiệu ứng clique; ω; so với mạng tổ chức.

Kết luận luôn đi kèm phạm vi (LCC hay toàn mạng). "Chưa đủ bằng chứng" là một kết luận hợp lệ.

### 5.2 Xếp hạng

PageRank có trọng số (số bài chung) trên mạng đồng tác giả và mạng tổ chức **[Lõi]**: top 20 kèm phạm vi tính. So với degree/betweenness bằng Spearman **[Mở rộng]**. Mạng CITES chỉ báo số cạnh và tỷ lệ bài có trích dẫn nội bộ trước khi diễn giải.

### 5.3 Cộng đồng, hạt nhân và nhóm nổi bật

1. Louvain trên mạng đồng tác giả, seed/trọng số/snapshot cố định; báo Q, kích thước nhóm; hiển thị riêng thành phần nhỏ/đơn lẻ.
2. k-core trên đồ thị đơn vô hướng → k_max và main core.
3. Hạt nhân mỗi cộng đồng: tác giả có PageRank nội bộ cao nhất (hòa thì xét theo ID).
4. **Nhóm nổi bật trong một kỳ:** xếp nhóm theo số bài riêng biệt có tác giả thuộc nhóm; hòa thì xét số tác giả hoạt động, rồi ID. Dùng một bảng thành viên cộng đồng chung cho mọi kỳ trong cùng snapshot.
5. **Mối quan tâm của nhóm:** mẫu số = số bài riêng biệt đủ văn bản của nhóm trong kỳ; tử số = số bài có chủ đề k. Mỗi cặp (nhóm, chủ đề) đếm mỗi bài một lần.
6. Ghi chú: cộng đồng suy từ đồng tác giả có thể khác với lab chính thức.

**[Mở rộng]:** Leiden, NMI giữa các seed.

---

## 6. Phần III — Ứng dụng đồ thị tri thức (4,5 điểm)

### 6.1 SLM

| Mục | Nội dung |
|---|---|
| Mô hình | Qwen3-8B, 8,2 tỷ tham số ([model card](https://huggingface.co/Qwen/Qwen3-8B)), Ollama `qwen3:8b`, tắt thinking; dự phòng Qwen3-4B, 4,0 tỷ ([model card](https://huggingface.co/Qwen/Qwen3-4B)), Ollama `qwen3:4b` |
| Dùng chung | Mỗi người cài Ollama và `ollama pull qwen3:8b` trên máy mình; so model digest (`ollama list`) với digest ghi trong `outputs/trend/slm_pilot/`. Kết quả SLM lưu cache theo sha256 và commit vào repo, nên người kia chạy lại pipeline từ cache mà không cần gọi model |
| Pilot | Khoảng 20 bài trên máy demo: model digest, RAM, token/giây, tỷ lệ JSON hợp lệ, ví dụ xử lý |
| Nhiệm vụ | (1) đề xuất thực thể, (2) xác minh quan hệ mơ hồ, (3) hiểu câu hỏi và sinh câu trả lời có nguồn, (4) tóm tắt cộng đồng [Mở rộng] |
| Tái lập | `temperature = 0`; cache theo sha256(văn bản + prompt + model digest) |

### 6.2 GraphRAG

**Local [Lõi]:** câu hỏi → SLM xác định ý định, thực thể, kỳ, loại chủ đề → liên kết tên/alias với node → chạy **mẫu Cypher có tham số** (Q1, Q1b, Q3) hoặc đọc **bảng xu hướng** → trả metrics, đường đi, bài nguồn → SLM diễn giải bằng ngôn ngữ của câu hỏi.

- Ý định "xu hướng" (ví dụ "Chủ đề nào tăng mạnh nhất ở CVPR?") đọc bảng M1/M2/M4 theo hội nghị và cặp kỳ, mặc định là cặp mới nhất qua cổng so sánh.
- Hội thoại giữ ngữ cảnh (hội nghị, cặp kỳ, chủ đề). Câu hỏi tiếp theo "Nhóm nào đang làm chủ đề đó?" dùng lại ngữ cảnh → bảng nhóm (M8) → Q1b → bài nguồn.
- Q1b nhận danh sách `author_id` của nhóm làm tham số Cypher, lấy từ bảng thành viên cộng đồng; không ghi cộng đồng vào Neo4j vì snapshot đã khóa.
- Cặp câu trên là tiêu chí nghiệm thu demo: kết quả phải khớp với trang Xu hướng, trang Nhóm và danh sách paper ID.

- Số liệu trong câu trả lời **chỉ** lấy từ kết quả truy vấn hoặc bảng metrics cùng snapshot, không để SLM tự sinh.
- Tên mơ hồ → cho người dùng chọn thực thể. Thiếu dữ liệu → nói rõ phần nào chưa xác định.
- Hậu kiểm: mọi ID trong câu trả lời phải tồn tại; kỳ và số đếm khớp kết quả truy vấn.

**Global [Mở rộng ưu tiên 1]:** map–reduce trên tóm tắt cộng đồng và bảng xu hướng cho câu hỏi tổng quát.

**Nghiệm thu [Lõi]:** bộ ≥ 20 câu (1-hop, multi-hop, tổng hợp, ca rỗng; có ít nhất một cặp câu Việt/Anh cho cùng kết quả), đáp án đối chiếu bằng Cypher và kiểm tay bài nguồn. Báo số đúng/tổng theo nhóm câu, tỷ lệ dẫn đúng nguồn, thời gian trả lời.
**[Mở rộng]:** 30 câu, so ba cấu hình SLM đơn / vector RAG / GraphRAG.

### 6.3 Chỉ số xu hướng

Ký hiệu: **n** = số bài lõi riêng biệt, accepted, có đủ văn bản (tiêu đề + abstract), NLP chạy thành công, kể cả bài không trích được chủ đề nào; **x** = số paper ID riêng biệt có cạnh hợp lệ tới chủ đề k. **Mỗi chủ đề đếm một lần trên mỗi bài**, bất kể số tác giả hay số lần nhắc.

| ID | Chỉ số | Định nghĩa | Mức |
|---|---|---|---|
| M1 | Phổ biến trong kỳ | x/n, tỷ trọng, khoảng Wilson 95%, kèm n/số bài được chọn; N/A khi n = 0 | Lõi |
| M2 | Tăng/giảm giữa hai kỳ cùng hội nghị | Δ = 100 × (x_sau/n_sau − x_trước/n_trước), đơn vị điểm phần trăm. Bảng chính CVPR 2025→2026; phụ CVPR 2024→2025, ICCV 2023→2025 | Lõi |
| — | Cổng so sánh | Một cặp kỳ chỉ được gắn nhãn bằng chứng (M2) và ứng viên mới nổi (M4) khi: cả hai kỳ đã xác minh chọn mẫu đúng §2.3; mỗi kỳ ≥ 95% bài có văn bản phân tích được và hai kỳ chênh nhau ≤ 5 điểm phần trăm; NLP thành công ≥ 95% bài mỗi kỳ. Không đạt thì hiện x/n, Δ và nhãn **"chỉ mô tả"** kèm lý do. Ngưỡng chốt trong config trước khi xem kết quả | Lõi |
| — | Độ chắc chắn của M2 | Chỉ áp dụng cho cặp qua cổng so sánh. Fisher exact hai phía trên bảng 2×2, hiệu chỉnh Benjamini–Hochberg trên mọi chủ đề được kiểm định trong cùng cặp kỳ (**trước** khi lọc UI). Nhãn "tăng/giảm có bằng chứng" khi q < 0,05 và đúng dấu Δ; còn lại "chưa đủ bằng chứng". Không bao gồm sai số NLP | Lõi |
| M4 | Ứng viên mới nổi | Cùng hội nghị: kỳ trước < 1%, kỳ sau ≥ 3% và x_sau ≥ 15 (ngưỡng trong config); hiển thị cả hai số đếm; "0 ở kỳ trước" nghĩa là chưa thấy trong mẫu | Lõi |
| M5 | Khác biệt hội nghị năm 2025 | Chênh tỷ trọng CVPR25 − ICCV25 kèm x/n từng bên | Lõi |
| M8–M9 | Ai quan tâm | Top nhóm/tổ chức/tác giả theo số bài riêng biệt và tỷ trọng trong nhóm; tác giả có bài sớm ghi "đã xuất hiện ở kỳ … trong mẫu" | Lõi |
| M3, M6, M7, M10, M11 | Tăng tương đối, diễn biến từng hội nghị, PageRank chủ đề, tiến hóa mạng, dịch chuyển chủ đề của nhóm | Như v0.2, chỉ so khi đủ bài và công bố mẫu số | Mở rộng |

**Ca kiểm thử số học (dữ liệu giả lập):** 14/350 bài CVPR 2024 và 28/350 bài CVPR 2025 → hiển thị 4% → 8%, **tăng 4 điểm phần trăm**. 28 bài có 60 tác giả hoặc nhắc chủ đề nhiều lần thì tử số vẫn là 28.

### 6.4 Truy vấn multi-hop

Mỗi truy vấn dùng đúng chiều cạnh theo contract, có tham số kỳ/hội nghị, đếm paper ID riêng biệt, giới hạn số kết quả, và mở được ít nhất một đường đi thật cùng bài nguồn. File: `queries/trend_*.cypher`.

| ID | Câu hỏi | Đường đi | Mức |
|---|---|---|---|
| Q1 | Tổ chức nào làm chủ đề k? | Chủ đề ← Bài ← Tác giả → Tổ chức (3 hop); affiliation ràng buộc **theo đúng bài** (`paper_id IN r.paper_ids`); thiếu affiliation thì báo độ phủ | Lõi |
| Q1b | Nhóm nổi bật G đang nghiên cứu gì? | Thành viên G (bảng Louvain, truyền vào dưới dạng `$author_ids`) → Bài → Task/Method/Dataset; trả số bài/tổng bài nhóm, top chủ đề theo loại, hạt nhân, bài nguồn; bấm chủ đề để xem ngược lại các nhóm | Lõi |
| Q3 | Cặp quốc gia nào hợp tác về k? | Bài có k → hai nhánh Tác giả → Tổ chức → Quốc gia; hai tác giả khác nhau, hai nước khác nhau, cùng bài; cặp không thứ tự, mỗi bài đếm một lần mỗi cặp | Lõi |
| Q2 | Có liên hệ đồng tác giả trước khi một người bắt đầu làm k? | Chỉ nhận bằng chứng tiếp xúc có trước lần xuất hiện đầu tiên ở k; loại ca không xác định thứ tự; chỉ mô tả quan sát | Mở rộng |
| Q4 | Nhóm làm k trích dẫn nhóm nào? | Bài về k – CITES → bài được trích → tác giả/nhóm; tập rỗng là hợp lệ | Mở rộng |
| Q5 | Hai tác giả/tổ chức liên hệ thế nào? | Đường ngắn nhất có giới hạn độ dài, mở bài tạo liên kết | Mở rộng |

### 6.5 Biểu diễn đồ thị

| Phần | Nội dung | Mức |
|---|---|---|
| Đồ thị con | pyvis: node có nhãn và màu theo loại, cạnh có hướng, bấm node mở bài | Lõi |
| Embedding tối thiểu | FastRP (Neo4j GDS) hoặc Node2Vec trên đồ thị Paper–Topic–Author, seed cố định; nghiệm thu: chọn một chủ đề ở trang 2a và thấy tối đa 5 chủ đề tương tự theo cosine; một hình UMAP chỉ để trực quan | Lõi |
| Nhóm tương tự | Vector nhóm = trung bình embedding các tác giả thành viên; top-5 theo cosine | Mở rộng |
| Đánh giá embedding | Link prediction/AUC, loại khỏi dữ liệu huấn luyện các bài đồng tác giả làm lộ cạnh giữ lại | Mở rộng |
| Độ trôi theo kỳ | Căn chỉnh không gian gốc bằng node neo chung rồi mới đo khoảng cách | Mở rộng |

---

## 7. Giao diện

| Màn hình lõi | Người xem thao tác được |
|---|---|
| 1. Tổng quan và xu hướng | Chọn hội nghị, cặp kỳ, loại chủ đề; xem x/n, độ phủ, bảng phổ biến, tăng/giảm, ứng viên mới nổi, khác biệt hội nghị 2025. Biểu đồ có đơn vị, chú giải, khoảng tin cậy, nhãn kỳ đúng |
| 2a. Chủ đề | Bấm chủ đề → Q1/Q3, đồ thị con, chủ đề tương tự (embedding), danh sách nhóm đang làm chủ đề (link sang 2b) |
| 2b. Nhóm | Bấm nhóm → hạt nhân, chủ đề chính, số bài, bằng chứng NLP, link bài (Q1b); bấm chủ đề quay về 2a |
| 3. Mạng lưới | Chuyển mạng tác giả/tổ chức; top PageRank, cộng đồng, main core; thế giới nhỏ ghi rõ mạng, LCC, độ phủ, mạng tham chiếu |
| 4. Hỏi đáp GraphRAG | Hỏi Việt/Anh; thấy kỳ đang xét, câu trả lời có số liệu, đường đi, nguồn, trạng thái thiếu dữ liệu |

Màn hình riêng cho Mới nổi, Bản đồ chủ đề, Tiến hóa mạng là phần mở rộng.

**Kiểm thử giao diện [Lõi]:** đối chiếu một chủ đề và một nhóm giữa UI, Cypher và danh sách paper ID; các ca mẫu số 0, không có bằng chứng, tác giả nhiều affiliation, một bài do nhiều thành viên của nhóm cùng viết, nhóm ít bài.

---

## 8. Báo cáo, demo, nộp bài

Các mốc dưới đây lấy theo đề bài đầy đủ do nhóm cung cấp ❓ (đối chiếu lại với thông báo chính thức).

| Hạng mục | Yêu cầu |
|---|---|
| Hoàn thành bài | **Trước 23:59 ngày 03/12/2026**: khóa bản chạy, dữ liệu, báo cáo |
| GitHub | Repo có code **và dữ liệu**; README có cách chạy, cấu hình, phiên bản, cách tái tạo snapshot và bảng số liệu |
| Báo cáo | Theo chuẩn arXiv và **nộp lên arXiv**; dùng lại khung LaTeX ♻️ sau khi đối chiếu định dạng; lưu minh chứng gửi bài |
| Slide và link | Gửi lên hệ thống **trước 23:59 ngày 20/12/2026** |
| Thời lượng | 20 phút trình bày + 5 phút demo + 5 phút hỏi đáp |

**Rủi ro arXiv:** người nộp lần đầu ở mục cs.CV thường cần **endorsement**, và bài phải qua kiểm duyệt (moderation) trước khi công bố. Phải kiểm tra yêu cầu endorsement ngay trong tuần đầu, không để đến ngày 03/12.

**Kịch bản demo 5 phút:** 0:00–1:00 chọn cặp kỳ CVPR và một chủ đề có thật trong kết quả; 1:00–2:00 đọc x/n và Δ; 2:00–3:15 mở nhóm và các chủ đề nhóm đang làm; 3:15–4:15 lần đường đi đến bài và câu bằng chứng; 4:15–5:00 hỏi lại qua GraphRAG và đối chiếu. Có video dự phòng. Nếu không có chủ đề nào tăng có ý nghĩa, demo một thay đổi quan sát được và giải thích nhãn.

**Slide** 15–20 trang. **Báo cáo:** quy trình, công thức, kết quả thực đo, lỗi, giới hạn, phân công, nguồn. **Câu hỏi dự kiến:** chọn mẫu, lẫn yếu tố hội nghị, phạm vi LCC, cách xác định nhóm nổi bật, cách kiểm SLM dẫn nguồn, vì sao Qwen3-8B, GraphRAG khác vector RAG ở đâu.

---

## 9. Definition of Done

1. README có lệnh chạy từ gốc repo, cách nạp dữ liệu và khởi động app từ snapshot đóng băng.
2. Lưu hash dữ liệu, phiên bản code/từ điển/model, prompt, seed, đầu ra SLM; dựng lại từ cùng snapshot/cache ra cùng tập ID, cạnh, bảng số liệu.
3. Contract và test hiện có pass; người còn lại đã duyệt PR.
4. Mỗi số liệu demo truy được về snapshot và paper ID.
5. Phần app chỉ xong khi chạy đủ ba thao tác: xem thay đổi trong cùng hội nghị → mở nhóm xem chủ đề → kiểm bằng chứng trên đường đi multi-hop và trong câu trả lời GraphRAG.
6. Bảng nghiệm thu ghi kết quả thực đạt và phần còn thiếu, tách chỉ tiêu nội bộ khỏi điểm giảng viên chấm.

---

## 10. Rủi ro

| Rủi ro | Xử lý |
|---|---|
| Thiếu kỳ mới, thiếu abstract, cách chọn mẫu cũ khác nhau | Thu CVPR 2025 đầu tiên; hiện độ phủ; hạ phạm vi theo §2.2 |
| OpenAlex thiếu affiliation cho bài 2025–2026 (dữ liệu mới, chưa cập nhật đủ) | Đo độ phủ affiliation từng kỳ ở pilot; Q1/Q3 báo độ phủ |
| Bỏ sót khái niệm mới hoặc SLM nhận nhầm | Quy trình §4.2, tập kiểm tra giữ riêng |
| Tách danh tính, tổ chức đổi theo thời gian | Bằng chứng theo paper ID; kiểm tay top demo |
| Mạng phân mảnh, CITES thưa | Ba số khoảng cách §5.1; cho phép kết quả rỗng |
| Thiếu RAM, truy vấn chậm, nguồn gián đoạn | Pilot sớm, cache, model dự phòng `qwen3:4b`, snapshot và video demo local |
| arXiv cần endorsement hoặc bị giữ duyệt | Kiểm tra ngay tuần đầu; hỏi giảng viên endorse |

---

## 11. Cần xác nhận

1. A: phân công §2.1 và kế hoạch `docs/PLAN_trend_app.md`; có cần sửa contract hay chỉ cần cấu hình mới (D5).
2. A và B: cấu hình máy chạy SLM; cách lưu affiliation theo bài; ngưỡng hiển thị chốt sau pilot, **trước** khi xem kết quả tập kiểm tra.
3. Giảng viên: được dùng lại kết quả Đề tài 30 đến đâu; "biểu diễn đồ thị" có yêu cầu embedding không; lịch thuyết trình; mốc arXiv riêng nếu có.

---

## 12. Lịch sử

| Phiên bản | Thay đổi |
|---|---|
| 0.1 (19/11) | Bản nháp đầu |
| 0.2 (19/11) | Theo thang điểm cuối kỳ: NER/RE/đánh giá, thế giới nhỏ, PageRank, k-core, SLM, GraphRAG, slide/báo cáo |
| 0.3 (20/11) | Tiếp nhận góp ý: so sánh cùng hội nghị thay Early/Late; Fisher exact; thêm Q1b nhóm → chủ đề; đếm một lần mỗi bài; tách tập gold dev/test trước khi mở rộng từ điển; ba số khoảng cách toàn mạng; thu gọn lõi còn 4 màn hình (màn hình 2 tách thành hai trang 2a/2b để hai người làm song song) và Q1/Q1b/Q3; thêm mốc nộp và arXiv. Khác góp ý: giữ embedding tối thiểu ở lõi; global search là mở rộng ưu tiên 1; đổi phân công thu thập (A: hai kỳ CVPR, B: ICCV 2025) |
| 0.3.1 (21/11) | Theo góp ý cho plan: cổng so sánh trước khi gắn nhãn; số bài gold theo số kỳ giữ lại, test chỉ mở sau khi đóng băng; embedding lõi chỉ gồm chủ đề tương tự; GraphRAG có ý định xu hướng và ngữ cảnh hội thoại; Q1b nhận `$author_ids` |
| 0.3.2 (23/11) | Chốt D9: `qwen3:8b` (tắt thinking) thay Qwen2.5-7B, dự phòng `qwen3:4b` thay Qwen2.5-3B; thêm cách dùng chung model giữa A và B |
