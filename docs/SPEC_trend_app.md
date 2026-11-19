# SPEC — CV Trend Radar: Đồ thị tri thức và ứng dụng phân tích xu hướng nghiên cứu Thị giác máy tính

| Mục | Giá trị |
|---|---|
| Phiên bản | 0.2 (nháp, chờ A duyệt) |
| Ngày | 19/11/2026 |
| Tác giả | B (Sntug) |
| Người duyệt | A (TienHung229), giảng viên |
| Mô hình | Agile/Scrum rút gọn cho nhóm 2 người |
| Ký hiệu | ✅ đã chốt · 🟡 đề xuất, chờ A chốt · ❓ câu hỏi mở · ♻️ dùng lại từ Đề tài 30 |

---

## 0. Ánh xạ yêu cầu cuối kỳ → sản phẩm

Spec này được tổ chức theo đúng thang điểm. Mỗi mục điểm có sản phẩm kiểm chứng được và có story tương ứng ở mục 9.

| Thang điểm | Điểm | Sản phẩm | Story | Mục |
|---|---|---|---|---|
| **I. Làm giàu và phân tích dữ liệu** | **2,0** | | | §4 |
| Thu thập, lựa chọn dữ liệu làm giàu | 0,5 | 1.750 bài lõi của 5 venue, có abstract và metadata OpenAlex | E1-1 | §2, §4.1 |
| Mô hình nhận dạng thực thể (node) | 0,5 | NER hai tầng: từ điển + luật ♻️ và SLM; so sánh trên tập gold | E1-2, E1-3 | §4.2 |
| Mô hình nhận dạng quan hệ (cạnh) | 0,5 | RE: luật ngữ cảnh ♻️ và SLM xác minh, mỗi cạnh có evidence | E1-4 | §4.3 |
| Đánh giá chất lượng đồ thị | 0,5 | P/R/F1 trên tập gold, Cohen's kappa, audit mẫu cạnh ♻️, chỉ số toàn vẹn | E1-5 | §4.4 |
| **II. Thuật toán phân tích MXH** | **1,5** | | | §5 |
| Thế giới nhỏ | 0,5 | L và C so với đồ thị ngẫu nhiên; hệ số σ, ω | E2-1 | §5.1 |
| Xếp hạng node (PageRank) | 0,5 | PageRank cho tác giả, tổ chức, bài báo, chủ đề | E2-2 | §5.2 |
| Cộng đồng và hạt nhân | 0,5 | Louvain/Leiden + phân rã k-core | E2-3 | §5.3 |
| **III. Ứng dụng đồ thị tri thức** | **4,5** | | | §6 |
| Mô hình ngôn ngữ nhỏ ≤ 9 tỷ tham số | 1,0 | Qwen2.5-7B-Instruct chạy local; dùng cho NER/RE, tóm tắt cộng đồng, sinh câu trả lời; có đánh giá | E3-1 | §6.1 |
| Đồ thị tri thức + RAG (ưu tiên GraphRAG) | 0,5 | GraphRAG local + global search trên Neo4j; so sánh với vector RAG thường | E3-2, E3-3 | §6.2 |
| Ứng dụng multi-hop + biểu diễn đồ thị | 3,0 | App xu hướng: 5 truy vấn multi-hop, embedding đồ thị, giao diện 7 màn hình | E4-* | §6.3, §7 |
| **IV. Slide, trình bày, báo cáo** | **2,0** | Slide, báo cáo, bản demo, bộ câu hỏi dự kiến | E5-* | §8 |

---

## 1. Bối cảnh và mục tiêu

### 1.1 Bối cảnh

Nhóm đã có đồ thị Neo4j của Đề tài 30 (snapshot A8: 4.182 node, 16.979 cạnh) dựng từ 700 bài lõi: 350 bài ICCV 2023 (B) và 350 bài CVPR 2024 (A). Schema gồm 8 nhãn (Author, Paper, Institution, VenueEdition, Task, Method, Dataset, Country) và 10 quan hệ. Pipeline thu thập → làm sạch → NLP → đồ thị → phân tích (B6) → audit (A8) đã chạy và tái lập được.

Số liệu B6 cần lưu ý khi thiết kế:

| Chỉ số (700 bài) | Giá trị | Hệ quả |
|---|---|---|
| Mạng đồng tác giả | 2.950 node, 7.771 cạnh, 416 thành phần liên thông | Mạng rất phân mảnh |
| Thành phần liên thông lớn nhất (LCC) | 502 node (17%) | Thế giới nhỏ chỉ đo được trên LCC |
| Hệ số gom cụm trung bình | 0,92 | Bị thổi phồng vì mỗi bài tạo thành một clique; phải so với mô hình ngẫu nhiên giữ nguyên cấu trúc |
| Cạnh CITES trong tập lõi | 97 | Mạng trích dẫn quá thưa để xếp hạng bài đáng tin |
| Louvain trên LCC | 19 cộng đồng, Q = 0,87 | Dùng lại được |

### 1.2 Mục tiêu sản phẩm

Ứng dụng trả lời ba câu hỏi, mỗi câu kèm số liệu và độ tin cậy:

1. **Chủ đề nào đang nổi, chủ đề nào đang giảm** trong CV giai đoạn 2023–2026?
2. **Ai đang dẫn dắt** các chủ đề đó: tác giả, tổ chức, cộng đồng nào?
3. **Chủ đề lan truyền thế nào** qua mạng đồng tác giả, qua trích dẫn, giữa các tổ chức?

Ngoài các màn hình phân tích, người dùng có thể **hỏi bằng tiếng Việt hoặc tiếng Anh** qua GraphRAG, ví dụ: "Những tổ chức nào ở Trung Quốc chuyển sang Gaussian Splatting năm 2025?".

### 1.3 Không làm (out of scope)

- Dự báo xu hướng tương lai: 5 mốc dữ liệu là không đủ.
- Thu thập toàn bộ kỷ yếu. Mỗi hội nghị chỉ lấy mẫu 350 bài.
- Sửa các lỗi dữ liệu đã biết của snapshot A8 (tác giả bị tách danh tính, ghép nhầm tổ chức). App chỉ đo và báo cáo các lỗi này.
- Fine-tune mô hình ngôn ngữ. Chỉ dùng prompting và few-shot.
- Deploy công khai có xác thực người dùng.
- Mở rộng thêm nhãn hoặc quan hệ ngoài 10 quan hệ của contract (trừ khi A đồng ý ở D5).

---

## 2. Phạm vi dữ liệu

### 2.1 Các mốc thời gian

| Mốc | Hội nghị | Trạng thái | Người phụ trách |
|---|---|---|---|
| 2023 | ICCV 2023 | ✅ ♻️ 350 bài | B |
| 2024 | CVPR 2024 | ✅ ♻️ 350 bài | A |
| 2025 | CVPR 2025 | ⬜ cần thu thập | 🟡 A |
| 2025 | ICCV 2025 | ⬜ cần thu thập | 🟡 B |
| 2026 | CVPR 2026 | ⬜ cần thu thập | 🟡 B |

Tổng: **1.750 bài lõi, 5 venue-edition, 4 năm.**

### 2.2 Giới hạn phương pháp cần chấp nhận

1. **Lẫn yếu tố hội nghị.** Năm 2023 chỉ có ICCV, năm 2024 và 2026 chỉ có CVPR. Năm 2025 có cả hai, nên mức chênh CVPR25–ICCV25 được dùng làm **ngưỡng nhiễu do hội nghị** (M5).
2. **Cỡ mẫu.** Với chủ đề chiếm khoảng 10% số bài, khoảng tin cậy 95% của tỷ trọng trên 350 bài là khoảng ±3,1 điểm phần trăm. Mọi so sánh phải kèm khoảng tin cậy.
3. **Trích dẫn.** CITES chỉ tính trong tập lõi; bài 2026 gần như chưa được trích dẫn. Không xếp hạng "bài hot" theo số trích dẫn giữa các năm.

### 2.3 Hai giai đoạn so sánh

| Giai đoạn | Venue | Số bài |
|---|---|---|
| **Early** | ICCV 2023 + CVPR 2024 | 700 |
| **Late** | CVPR 2025 + ICCV 2025 + CVPR 2026 | 1.050 |

Chuỗi 5 mốc chỉ dùng để hiển thị mô tả, không dùng để kết luận.

---

## 3. Các quyết định thiết kế

| ID | Quyết định | Đề xuất | Trạng thái |
|---|---|---|---|
| D1 | Venue và năm | Như bảng 2.1 | ✅ |
| D2 | Mẫu cho venue mới | 350 bài/venue, cùng thuật toán chọn của A (`sha256(seed + newline + canonical_url)`, seed `20261103`) | 🟡 |
| D3 | Định nghĩa "chủ đề" | Các từ điển Task/Method/Dataset ♻️ được **mở rộng** bằng ứng viên do SLM đề xuất từ cả 5 venue, người duyệt, rồi **đóng băng `v3`** | 🟡 |
| D4 | Danh tính tác giả xuyên năm | OpenAlex author ID; báo cáo tỷ lệ tách danh tính, không tự gộp | 🟡 |
| D5 | Hợp đồng dữ liệu | Mở rộng contract v2: `project_id` mới `mxh_cv_trend`, venue id dạng `venue:CVPR:2025:main`. `config/contracts/` thuộc A, nên **A sửa** | 🟡 |
| D6 | Biểu diễn đồ thị | FastRP (Neo4j GDS); dự phòng Node2Vec trong Python | 🟡 |
| D7 | Giao diện | Streamlit + Plotly + pyvis, dùng lại code NetworkX của B6 | 🟡 |
| D8 | Nguồn dữ liệu cho app | Neo4j (Cypher multi-hop, vector index) + bảng metrics tính sẵn (CSV/JSON) | 🟡 |
| D9 | Mô hình ngôn ngữ nhỏ | **Qwen2.5-7B-Instruct** (7,6 tỷ tham số), lượng tử hóa Q4 qua Ollama. Dự phòng Qwen2.5-3B nếu máy không đủ RAM | 🟡 |
| D10 | Mô hình embedding văn bản | `nomic-embed-text` hoặc `bge-m3` qua Ollama, dùng cho vector index | 🟡 |
| D11 | Kiến trúc RAG | GraphRAG hai chế độ: local (entity → đồ thị con k-hop) và global (tóm tắt cộng đồng), xem §6.2 | 🟡 |

### Vì sao D3 quan trọng nhất

Từ điển hiện tại được dựng từ dữ liệu 2023–2024. Nếu dùng nguyên trạng, các chủ đề mới xuất hiện năm 2025–2026 sẽ không bao giờ được phát hiện, và app sẽ kết luận sai là "không có gì mới nổi". Quy trình mở rộng nằm ở §4.2.

---

## 4. Phần I — Làm giàu và phân tích dữ liệu (2 điểm)

### 4.1 Thu thập và lựa chọn dữ liệu làm giàu (0,5 điểm)

| Nguồn | Dữ liệu | Vai trò |
|---|---|---|
| CVF Open Access ♻️ | Tiêu đề, abstract, danh sách tác giả, URL | Văn bản đầu vào cho NER và RE |
| OpenAlex API ♻️ | Author ID, tổ chức, quốc gia, danh sách tham chiếu | Danh tính, quan hệ trực thuộc, CITES |
| arXiv (bổ sung) ♻️ | Abstract khi CVF thiếu | Lấp chỗ trống |

**Tiêu chí lựa chọn** (đưa vào báo cáo): cùng loại venue hạng A*; chọn mẫu ngẫu nhiên tái lập được; chỉ bài `validation_status = accepted` mới vào đồ thị; ghi nhận sha256 của mọi file thô.

**Thống kê bắt buộc:** số bài, tỷ lệ có abstract, tỷ lệ khớp OpenAlex, tỷ lệ authorship bị loại (Đề tài 30 là 12,3%), tách theo từng venue.

### 4.2 Mô hình nhận dạng thực thể (0,5 điểm)

Các loại thực thể: **Task, Method, Dataset** (từ văn bản), **Author, Institution, Country** (từ metadata).

| Tầng | Mô hình | Vai trò |
|---|---|---|
| T1 ♻️ | Từ điển + luật + bộ lọc ngữ cảnh của spaCy (A4/B5): loại bỏ prior work, phủ định, giả định, pretrain, ví dụ ứng dụng | Baseline, độ chính xác cao |
| T2 | SLM (D9) trích xuất thực thể từ abstract theo JSON schema cố định, few-shot | Phát hiện khái niệm mới và tăng recall |
| T3 | Liên kết thực thể (entity linking): chuẩn hóa alias về ID trong từ điển `v3`; khái niệm SLM tìm ra nhưng chưa có trong từ điển được đưa vào hàng chờ duyệt | Đồng nhất ID xuyên năm |

**Quy trình mở rộng từ điển (D3):**

1. Chạy T2 trên abstract của cả 5 venue và gom các khái niệm ứng viên theo tần suất.
2. A và B duyệt ứng viên có tần suất ≥ 5. Mỗi khái niệm được chấp nhận phải có định nghĩa, alias và ít nhất một ví dụ.
3. Đóng băng từ điển `v3` (lưu sha256).
4. Chạy lại NER trên **toàn bộ 1.750 bài** bằng cùng một phiên bản code và từ điển.

**So sánh mô hình** (trên tập gold ở §4.4): bảng P/R/F1 của T1, T2 và T1 ∪ T2. Cấu hình có F1 cao nhất được dùng để dựng đồ thị chính thức.

### 4.3 Mô hình nhận dạng quan hệ (0,5 điểm)

| Quan hệ | Nguồn | Mô hình |
|---|---|---|
| STUDIES_TASK, USES_METHOD, EVALUATED_ON | Văn bản | Luật ngữ cảnh ♻️ (vị trí trong câu, động từ khóa, bộ lọc) + **SLM xác minh**: với mỗi cặp (bài, thực thể) ứng viên, SLM phân loại {đúng quan hệ, chỉ nhắc tới, phủ định} và trích câu bằng chứng |
| AUTHORED, AFFILIATED_WITH, BASED_IN, PUBLISHED_IN, CITES | Metadata | Ánh xạ xác định từ OpenAlex/CVF ♻️ |
| COAUTHORED_WITH, COLLABORATED_WITH | Suy diễn | Tính từ AUTHORED và AFFILIATED_WITH; trọng số = số bài lõi chung ♻️ |

Mỗi cạnh lấy từ văn bản phải lưu `text_version_id`, offset và câu bằng chứng (theo contract `validate_nlp_evidence`).

### 4.4 Phương án đánh giá chất lượng đồ thị (0,5 điểm)

| Cấp | Phương pháp | Chỉ tiêu |
|---|---|---|
| Thực thể và quan hệ | **Tập gold**: 100 abstract (20 mỗi venue, chọn ngẫu nhiên theo seed), A và B gán nhãn độc lập | P/R/F1 theo loại; NER F1 ≥ 0,80; RE precision ≥ 0,85 |
| Độ đồng thuận | Cohen's kappa giữa A và B trên tập gold | κ ≥ 0,7; lệch được giải quyết bằng thảo luận và ghi log |
| Cạnh trong đồ thị | Audit mẫu ngẫu nhiên khoảng 10 cạnh mỗi loại, chấm chéo ♻️ (quy trình A8) | Tỷ lệ đúng ≥ 95% |
| Danh tính node | Kiểm tra các node rủi ro (trùng tên, tách ORCID) ♻️ | Báo cáo tỷ lệ tách/gộp sai |
| Toàn vẹn | Contract verify; không có cạnh treo; nạp hai lần ra cùng content hash ♻️ | Pass 100% |
| Độ phủ | % bài có ≥ 1 Task, % bài có ≥ 1 Method, % tác giả có tổ chức | Báo cáo theo từng venue |

---

## 5. Phần II — Thuật toán phân tích mạng xã hội (1,5 điểm)

Chạy trên ba mạng: **đồng tác giả** (Author–Author), **hợp tác tổ chức** (Institution–Institution), **trích dẫn** (Paper→Paper). Mỗi chỉ số được tính cho đồ thị toàn bộ và cho hai giai đoạn Early, Late. Mở rộng `src/analysis/` ♻️.

### 5.1 Chứng minh thế giới nhỏ (0,5 điểm)

1. Đo trên **LCC** của mạng đồng tác giả và mạng tổ chức: độ dài đường đi ngắn nhất trung bình `L`, đường kính, hệ số gom cụm `C`.
2. So với hai mô hình ngẫu nhiên, mỗi mô hình 20 bản sao với seed cố định:
   - Erdős–Rényi cùng số node và số cạnh (`L_rand`, `C_rand`);
   - Configuration model giữ nguyên dãy bậc. Mô hình này cần thiết vì C = 0,92 bị thổi phồng do clique của từng bài.
3. Tính `σ = (C / C_rand) / (L / L_rand)`, kết luận thế giới nhỏ khi σ > 1; tính thêm `ω = L_rand / L − C / C_latt`.
4. So sánh `L` thực tế với `ln N / ln ⟨k⟩`.
5. Biểu đồ phân phối độ dài đường đi ngắn nhất (histogram).
6. **Ghi rõ giới hạn:** LCC chỉ chiếm 17% số tác giả trong dữ liệu Đề tài 30. Phải báo cáo kích thước LCC trên 1.750 bài trước khi kết luận.

### 5.2 Xếp hạng node bằng thuật toán đồ thị (0,5 điểm)

| Mạng | Thuật toán | Đầu ra |
|---|---|---|
| Đồng tác giả (có trọng số) | PageRank, so với degree và betweenness | Top 20 tác giả; tương quan Spearman giữa các chỉ số |
| Hợp tác tổ chức | PageRank có trọng số | Top 20 tổ chức |
| Trích dẫn | PageRank (α = 0,85) ♻️ | Top bài trong tập lõi, có ghi chú về độ thưa |
| Đồng xuất hiện chủ đề | PageRank theo từng giai đoạn | Chủ đề đi vào trung tâm (dùng cho M7) |

### 5.3 Phát hiện cộng đồng và tìm hạt nhân (0,5 điểm)

1. **Cộng đồng:** Louvain ♻️ và Leiden trên LCC đồng tác giả; báo cáo số cộng đồng, modularity Q, phân phối kích thước; so sánh độ ổn định giữa nhiều seed (NMI).
2. **Gán nhãn cộng đồng:** mỗi cộng đồng được mô tả bằng top tổ chức, top chủ đề và một đoạn tóm tắt do SLM sinh. Tóm tắt này dùng lại cho GraphRAG global.
3. **Hạt nhân:**
   - Phân rã **k-core**: tìm k_max và danh sách thành viên của lõi lớn nhất (main core);
   - Hạt nhân của từng cộng đồng: node có PageRank cao nhất trong cộng đồng, kèm bậc trong nội bộ cộng đồng.
4. Trực quan hóa: đồ thị LCC tô màu theo cộng đồng, node thuộc main core được tô nổi bật.

---

## 6. Phần III — Ứng dụng đồ thị tri thức (4,5 điểm)

### 6.1 Mô hình ngôn ngữ nhỏ ≤ 9 tỷ tham số (1 điểm)

**Lựa chọn:** Qwen2.5-7B-Instruct (7,6 tỷ tham số), chạy local qua Ollama với lượng tử hóa Q4_K_M.

| Tiêu chí | Qwen2.5-7B | Llama-3.1-8B | Gemma-2-9B |
|---|---|---|---|
| Số tham số | 7,6 tỷ | 8,0 tỷ | 9,2 tỷ (**vượt giới hạn 9 tỷ**) |
| Xuất JSON có cấu trúc | Tốt | Khá | Khá |
| Tiếng Việt | Khá | Khá | Khá |
| Ngữ cảnh | 32K (mở rộng đến 128K) | 128K | 8K |

*Số liệu trong bảng phải được kiểm tra lại với model card trước khi đưa vào báo cáo.* Gemma-2-9B bị loại vì vượt 9 tỷ tham số.

**Vai trò của SLM trong hệ thống:**

| # | Nhiệm vụ | Nơi dùng |
|---|---|---|
| 1 | Trích xuất thực thể (NER tầng T2) | §4.2 |
| 2 | Xác minh quan hệ và trích câu bằng chứng | §4.3 |
| 3 | Tóm tắt cộng đồng | §5.3, §6.2 |
| 4 | Chuyển câu hỏi thành truy vấn (nhận diện thực thể + chọn mẫu Cypher) | §6.2 |
| 5 | Sinh câu trả lời có trích dẫn nguồn | §6.2 |

**Đánh giá SLM:** F1 trên tập gold (nhiệm vụ 1–2); tỷ lệ JSON hợp lệ; tốc độ token/giây và thời gian xử lý 1.750 abstract; độ chính xác câu trả lời trên bộ 30 câu hỏi (§6.2).

### 6.2 Đồ thị tri thức + GraphRAG (0,5 điểm)

**Biểu diễn KG:** Neo4j với 8 nhãn và 10 quan hệ (ontology đưa vào báo cáo dưới dạng sơ đồ). Mỗi node Paper có thuộc tính `abstract` và `embedding`; mỗi node Task/Method/Dataset có `description` và `embedding`; vector index của Neo4j được tạo trên các thuộc tính này.

**Hai chế độ truy xuất:**

| Chế độ | Dùng cho câu hỏi | Luồng xử lý |
|---|---|---|
| **Local search** | Cụ thể, nhiều bước: "Ai ở MIT làm NeRF và từng đồng tác giả với người ở Google?" | (1) SLM trích thực thể trong câu hỏi → (2) liên kết với node qua tên + vector index → (3) mở rộng đồ thị con k-hop (k ≤ 3) hoặc chạy mẫu Cypher Q1–Q5 → (4) tuyến tính hóa đồ thị con thành ngữ cảnh → (5) SLM trả lời, trích ID bài/tác giả |
| **Global search** | Tổng quát: "Xu hướng chính của CV năm 2025 là gì?" | Map–reduce trên các tóm tắt cộng đồng (§5.3) và bảng metrics xu hướng → SLM tổng hợp |

**Đánh giá (bắt buộc để bảo vệ lựa chọn GraphRAG):**

- Bộ **30 câu hỏi** gồm 10 câu 1-hop, 10 câu multi-hop, 10 câu tổng quát, có đáp án tham chiếu sinh từ Cypher.
- So sánh ba cấu hình: **SLM không RAG**, **vector RAG** (chỉ tìm abstract), **GraphRAG**.
- Chỉ số: độ chính xác do người chấm, tỷ lệ câu trả lời có trích dẫn đúng, tỷ lệ bịa (hallucination), độ trễ.

### 6.3 Ứng dụng xu hướng với multi-hop và biểu diễn đồ thị (3 điểm)

#### 6.3.1 Các chỉ số xu hướng

Ký hiệu: `k` là một chủ đề, `t` là một venue hoặc một giai đoạn, `n_t` là số bài, `x_t(k)` là số bài có chủ đề `k`.

| ID | Chỉ số | Định nghĩa | Dùng để |
|---|---|---|---|
| M1 | Tỷ trọng | `share_t(k) = x_t(k) / n_t`, khoảng tin cậy 95% Wilson | So sánh giữa các venue |
| M2 | Thay đổi tỷ trọng | `Δ(k) = share_late − share_early`; z-test hai tỷ lệ; hiệu chỉnh Benjamini–Hochberg | Xếp hạng tăng/giảm |
| M3 | Hệ số tăng trưởng | `(share_late + ε) / (share_early + ε)`, `ε = 0,5 / n` | Chủ đề tăng mạnh từ nền thấp |
| M4 | Mới nổi | `share_early < 1%` **và** `share_late ≥ 3%` **và** `x_late ≥ 15` (ngưỡng đặt trong config) | Danh sách emerging |
| M5 | Ngưỡng nhiễu hội nghị | `gap(k) = |share_CVPR25 − share_ICCV25|`; nhãn **robust** khi `|Δ| > gap` **và** q < 0,05 | Lọc xu hướng giả |
| M6 | Độ dốc mô tả | Hồi quy OLS của share theo năm trên 5 mốc | Chỉ để hiển thị |
| M7 | Độ trung tâm của chủ đề | PageRank trên mạng đồng xuất hiện chủ đề, theo từng giai đoạn | Chủ đề đi vào trung tâm |
| M8 | Người dẫn dắt | Top tác giả, tổ chức, quốc gia theo số bài thuộc chủ đề nổi ở giai đoạn Late | "Ai dẫn dắt" |
| M9 | Người tiên phong | Tác giả đã có bài thuộc chủ đề nổi ngay trong giai đoạn Early | "Ai đi trước" |
| M10 | Tiến hóa mạng | Theo giai đoạn: node, cạnh, mật độ, % LCC, Q, L, C, tỷ lệ tác giả quay lại | Mạng thay đổi ra sao |
| M11 | Dịch chuyển cộng đồng | Phân bố chủ đề của mỗi cộng đồng ở hai giai đoạn, đo bằng khoảng cách Jensen–Shannon | "Nhóm nào chuyển hướng" |

#### 6.3.2 Suy luận multi-hop

Mỗi truy vấn có file `queries/trend_*.cypher`, vừa là tính năng của app vừa là mẫu truy vấn cho GraphRAG local.

| ID | Câu hỏi | Đường đi | Số hop |
|---|---|---|---|
| Q1 | Tổ chức nào dẫn dắt chủ đề `k`? | `k ← Paper ← Author → Institution` | 3 |
| Q2 | Chủ đề có lan qua đồng tác giả không? | `Author(late, k) – COAUTHORED_WITH – Author → Paper(early) → k` | 3–4 |
| Q3 | Cặp quốc gia nào hợp tác nhiều nhất trên `k`? | `k ← Paper ← Author → Institution → Country` | 4 |
| Q4 | Các nhóm làm `k` trích dẫn nhóm nào? | `k ← Paper – CITES → Paper ← Author → Institution` | 4 |
| Q5 | Đường nối ngắn nhất giữa hai tác giả/tổ chức và chủ đề chung | `shortestPath` trên COAUTHORED_WITH + mở rộng sang chủ đề | biến thiên |

**Kiểm định Q2:** so sánh tỷ lệ "người nhận chủ đề có đồng tác giả đã làm chủ đề đó trước" với đường cơ sở hoán vị ngẫu nhiên giữ nguyên bậc (1.000 lần). Chỉ kết luận "lan qua đồng tác giả" khi giá trị quan sát vượt phân vị 95% của đường cơ sở.

#### 6.3.3 Biểu diễn đồ thị (embedding)

| ID | Tính năng | Cách làm |
|---|---|---|
| E1 | Bản đồ chủ đề | FastRP/Node2Vec trên đồ thị dị thể Paper–Topic–Author của từng giai đoạn → UMAP 2D; hai bản đồ Early và Late cạnh nhau |
| E2 | Độ trôi chủ đề | Căn chỉnh Procrustes (neo bằng các chủ đề có ở cả hai giai đoạn) → khoảng cách cosine của mỗi chủ đề |
| E3 | Đánh giá embedding | Dự đoán liên kết trên COAUTHORED_WITH (giữ lại 10% cạnh làm test), AUC so với baseline common-neighbors; mục tiêu AUC > 0,75 |

---

## 7. Các màn hình

| # | Màn hình | Câu hỏi trả lời | Thành phần chính | Phần điểm |
|---|---|---|---|---|
| 1 | Tổng quan | Bức tranh chung | Thẻ KPI, top tăng/giảm, số bài theo venue, chất lượng dữ liệu | I |
| 2 | Mạng lưới | Cấu trúc MXH | Thế giới nhỏ (L, C, σ so với ngẫu nhiên), top PageRank, cộng đồng, main core | II |
| 3 | Xu hướng chủ đề | Cái gì nổi, cái gì giảm | Line chart 5 mốc kèm khoảng tin cậy, bảng M2/M3/M5, lọc theo Task/Method/Dataset | III |
| 4 | Mới nổi | Cái gì mới xuất hiện | Bảng M4, slope chart Early → Late | III |
| 5 | Chi tiết chủ đề | Ai dẫn dắt, lan truyền thế nào | M8, M9, Q1–Q4, kết quả Q2 so với hoán vị, bài tiêu biểu | III |
| 6 | Bản đồ chủ đề | Chủ đề dịch chuyển ra sao | UMAP Early/Late, bảng độ trôi, tiến hóa mạng M10/M11 | III |
| 7 | Hỏi đáp | Câu hỏi tự do | Khung chat GraphRAG, hiển thị đồ thị con dùng làm ngữ cảnh và các nguồn trích dẫn | III |

Mọi biểu đồ theo thời gian ghi rõ `n` và cảnh báo về lẫn yếu tố hội nghị.

---

## 8. Phần IV — Slide, trình bày, báo cáo (2 điểm)

| Sản phẩm | Yêu cầu |
|---|---|
| **Báo cáo** | Cấu trúc theo bốn phần thang điểm; mỗi chỉ số có công thức, kết quả, diễn giải và giới hạn; bảng phân công; link GitHub. Dùng lại khung LaTeX ♻️ `report/final_report.tex` |
| **Slide** | 15–20 slide; một ý chính mỗi slide; mỗi slide số liệu có một kết luận viết thành câu; có slide kiến trúc hệ thống và slide giới hạn |
| **Demo** | Kịch bản 5 phút theo luồng: một câu hỏi xu hướng → màn hình xu hướng → chi tiết chủ đề → multi-hop → hỏi đáp GraphRAG. Có video dự phòng nếu demo trực tiếp lỗi |
| **Chuẩn bị hỏi đáp** | Danh sách khoảng 20 câu hỏi dự kiến kèm câu trả lời, ví dụ: vì sao chọn 350 bài mỗi venue, vì sao C cao mà vẫn gọi là thế giới nhỏ, lẫn yếu tố hội nghị xử lý thế nào, vì sao chọn Qwen 7B, GraphRAG hơn vector RAG ở điểm nào, SLM bịa thì phát hiện ra sao |

---

## 9. Backlog: user stories và tiêu chí chấp nhận

Mức ưu tiên theo MoSCoW: **M** = Must, **S** = Should, **C** = Could. 1 SP ≈ nửa buổi làm việc.

### Epic E1 — Làm giàu dữ liệu (Phần I, 2 điểm)

| ID | Story | Ưu tiên | SP | Tiêu chí chấp nhận |
|---|---|---|---|---|
| E1-1 | Thu thập 350 bài cho mỗi venue CVPR 2025, ICCV 2025, CVPR 2026 | M | 5 | Mỗi venue 350 bài `accepted`; `src.collect.verify` exit 0; có bảng thống kê §4.1 |
| E1-2 | Mở rộng và đóng băng từ điển `v3` bằng ứng viên SLM | M | 3 | Có file từ điển và sha256; A và B đều duyệt; mỗi khái niệm có định nghĩa và ví dụ |
| E1-3 | NER hai tầng chạy trên 1.750 bài | M | 3 | Cùng `code_version` cho mọi venue; có bảng so sánh T1, T2, T1∪T2 |
| E1-4 | RE với SLM xác minh, có evidence | M | 3 | Mỗi cạnh văn bản có offset và câu bằng chứng; contract verify pass |
| E1-5 | Tập gold 100 abstract, đánh giá đồ thị | M | 4 | Có P/R/F1, κ, kết quả audit cạnh và bảng độ phủ |
| E1-6 | Đồ thị gộp 5 venue trong Neo4j | M | 2 | Nạp hai lần ra cùng content hash; test của B pass |

### Epic E2 — Phân tích MXH (Phần II, 1,5 điểm)

| ID | Story | Ưu tiên | SP | Tiêu chí chấp nhận |
|---|---|---|---|---|
| E2-1 | Chứng minh thế giới nhỏ | M | 3 | Có L, C, σ, ω trên LCC so với ER và configuration model (20 bản sao); histogram; ghi rõ giới hạn |
| E2-2 | Xếp hạng PageRank cho bốn mạng | M | 2 | Có top 20 mỗi mạng và tương quan Spearman với degree/betweenness |
| E2-3 | Cộng đồng và hạt nhân | M | 3 | Louvain + Leiden, Q, NMI giữa các seed; k-core, main core; hạt nhân từng cộng đồng; hình vẽ |

### Epic E3 — SLM và GraphRAG (Phần III, 1,5 điểm)

| ID | Story | Ưu tiên | SP | Tiêu chí chấp nhận |
|---|---|---|---|---|
| E3-1 | Cài đặt và đánh giá SLM | M | 2 | Chạy local; có bảng lựa chọn mô hình; đo tốc độ; tỷ lệ JSON hợp lệ ≥ 95% |
| E3-2 | GraphRAG local + global | M | 4 | Có vector index; local search dùng Q1–Q5; có tóm tắt cộng đồng; câu trả lời kèm ID nguồn |
| E3-3 | Đánh giá trên 30 câu hỏi, so với vector RAG | M | 2 | Bảng so sánh ba cấu hình; GraphRAG thắng ở nhóm câu multi-hop, nếu không thì báo cáo trung thực |

### Epic E4 — Ứng dụng xu hướng (Phần III, 3 điểm)

| ID | Story | Ưu tiên | SP | Tiêu chí chấp nhận |
|---|---|---|---|---|
| E4-1 | Tính các chỉ số M1–M6 | M | 3 | Đủ 5 venue × mọi chủ đề; có q-value và nhãn robust; chạy lại ra kết quả giống hệt |
| E4-2 | Người dẫn dắt và tiên phong (M8, M9) | M | 2 | Khớp với kết quả Q1 chạy trên Neo4j |
| E4-3 | Năm truy vấn multi-hop Q1–Q5 | M | 3 | Mỗi truy vấn < 3 giây; app hiển thị đường đi minh họa |
| E4-4 | Kiểm định lan truyền Q2 | M | 2 | Có giá trị quan sát, phân phối hoán vị và kết luận |
| E4-5 | Embedding E1–E3 | M | 3 | Hai bản đồ UMAP; bảng độ trôi; AUC so với baseline |
| E4-6 | Tiến hóa mạng và dịch chuyển cộng đồng (M7, M10, M11) | S | 3 | Đủ bảng; top 5 cộng đồng dịch chuyển nhiều nhất |
| E4-7 | Giao diện 7 màn hình | M | 5 | Đủ §7; số liệu trên app khớp với bảng metrics; có chú thích `n` |

### Epic E5 — Báo cáo và trình bày (Phần IV, 2 điểm)

| ID | Story | Ưu tiên | SP | Tiêu chí chấp nhận |
|---|---|---|---|---|
| E5-1 | Báo cáo | M | 4 | Đủ §8; mọi số liệu khớp với output |
| E5-2 | Slide | M | 2 | 15–20 slide theo §8 |
| E5-3 | Demo và video dự phòng | M | 1 | Kịch bản 5 phút; video ≤ 5 phút |
| E5-4 | Bộ câu hỏi dự kiến và tập dượt | M | 1 | Khoảng 20 câu hỏi có đáp án; tập dượt ≥ 2 lần, có bấm giờ |

**Đã bỏ so với v0.1:** biểu đồ Sankey cho dòng trích dẫn (CITES quá thưa), gợi ý node liên quan theo embedding (không có điểm trong thang), file `RETRO.md` riêng.

---

## 10. Kế hoạch sprint

Mỗi sprint kéo dài 2–3 ngày; ngày cụ thể được điền khi biết hạn nộp (❓1).

| Sprint | Mục tiêu (Sprint Goal) | Stories | SP |
|---|---|---|---|
| **0** | Chốt spec, contract, SLM chạy được trên máy | Duyệt spec; D2, D5, D9; E3-1; pilot khoảng 20 bài CVPR 2026 | 2 |
| **1** | Có dữ liệu 5 venue và đồ thị đã làm giàu | E1-1, E1-2, E1-3, E1-4, E1-6 | 16 |
| **2** | Có kết quả đánh giá chất lượng và phân tích MXH | E1-5, E2-1, E2-2, E2-3, E4-1 | 15 |
| **3** | Có GraphRAG, multi-hop và embedding | E3-2, E3-3, E4-2, E4-3, E4-4, E4-5 | 16 |
| **4** | Có app hoàn chỉnh và bản trình bày | E4-7, E4-6, E5-1, E5-2, E5-3, E5-4 | 16 |

**Nghi thức Scrum rút gọn:**

- **Sprint planning**: khoảng 15 phút, chọn story từ backlog.
- **Daily**: một tin nhắn mỗi ngày gồm "đã xong / sẽ làm / đang vướng".
- **Review**: demo cuối sprint, đối chiếu với bảng §0.
- **Retro**: 3 dòng, ghi vào mục 14 của spec này.
- **Backlog**: GitHub Issues, mỗi story một issue, gắn nhãn epic và ưu tiên.

---

## 11. Definition of Done

1. Code chạy được từ thư mục gốc repo bằng một lệnh, đã ghi vào README.
2. Tái lập được: seed cố định; chạy lại cho ra cùng sha256 hoặc cùng số liệu. Với SLM: `temperature = 0`, ghi lại tên và digest của mô hình.
3. Logic không tầm thường có test; mọi test hiện có vẫn pass.
4. Contract verify pass với mọi thay đổi dữ liệu.
5. Người còn lại đã đọc chéo qua PR.
6. Số liệu trên app khớp với bảng metrics và với báo cáo.
7. Story được đánh dấu xong trong bảng §0.

---

## 12. Rủi ro

| Rủi ro | Khả năng | Ảnh hưởng | Giảm thiểu |
|---|---|---|---|
| Từ điển bỏ sót chủ đề mới 2025–2026 | Cao | Cao | Quy trình D3 với SLM đề xuất ứng viên |
| Lẫn yếu tố hội nghị bị nhầm thành xu hướng | Cao | Cao | M5, so sánh theo giai đoạn, chú thích trên biểu đồ |
| Máy không đủ RAM cho mô hình 7B | Trung bình | Cao | Kiểm tra ở Sprint 0; dự phòng Qwen2.5-3B |
| SLM chạy chậm trên 1.750 abstract | Trung bình | Trung bình | Cache theo sha256 của input; chạy nền qua đêm |
| SLM bịa trong câu trả lời GraphRAG | Cao | Trung bình | Bắt buộc trích ID nguồn; hậu kiểm ID có tồn tại trong đồ thị; đo tỷ lệ bịa |
| LCC nhỏ làm yếu kết luận thế giới nhỏ | Cao | Trung bình | Báo cáo kích thước LCC; đo thêm trên mạng tổ chức |
| Hết quota OpenAlex | Trung bình | Trung bình | API key, delay 1 giây, cache |
| Neo4j Community thiếu GDS | Trung bình | Thấp | Node2Vec và Leiden chạy trong Python |
| Tác giả bị tách danh tính làm sai M9 và Q2 | Trung bình | Trung bình | Báo cáo tỷ lệ; kiểm tra thủ công top tác giả |

---

## 13. Câu hỏi mở

| # | Câu hỏi | Người trả lời |
|---|---|---|
| ❓1 | Hạn nộp và ngày thuyết trình là khi nào? Thời lượng trình bày bao lâu? | Giảng viên |
| ❓2 | Có chấp nhận mở rộng phạm vi sang 5 venue 2023–2026 không? | Giảng viên |
| ❓3 | Kết quả Đề tài 30 (NLP, B6, audit A8) có được dùng lại cho Phần I và II không, hay phải làm mới? | Giảng viên |
| ❓4 | Phân công: A làm CVPR 2025, B làm ICCV 2025 và CVPR 2026? Ai phụ trách epic nào? | A |
| ❓5 | A có đồng ý mở rộng contract (D5) và từ điển (D3) không? | A |
| ❓6 | Máy chạy SLM có bao nhiêu RAM? | A, B |

---

## 14. Retro và lịch sử thay đổi

| Phiên bản | Ngày | Thay đổi |
|---|---|---|
| 0.1 | 19/11/2026 | Bản nháp đầu tiên |
| 0.2 | 19/11/2026 | Viết lại theo thang điểm cuối kỳ: thêm §0 (ánh xạ thang điểm), Phần I (NER/RE/đánh giá), Phần II (thế giới nhỏ, PageRank, k-core), SLM, GraphRAG, Phần IV; bỏ Sankey, gợi ý node, file RETRO riêng |
