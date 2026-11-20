# PLAN — Phát triển CV Trend Radar

| Mục | Giá trị |
|---|---|
| Phiên bản | 1.0 (chờ A duyệt) |
| Ngày | 20/11/2026 |
| Căn cứ | `docs/SPEC_trend_app.md` v0.3 và yêu cầu cuối kỳ |
| Hạn cứng | Hoàn thành bài **03/12/2026 23:59** · Slide/link **20/12/2026 23:59** |
| Hạn nội bộ | Đóng băng bản nộp **03/12/2026 12:00** (giữ 12 giờ dự phòng) |

---

## 1. Nguyên tắc chia việc để tránh conflict

1. **Chia theo thư mục, không theo file.** Mỗi thư mục chỉ có một chủ. Không ai sửa file thuộc thư mục của người kia; cần thay đổi thì mở issue cho chủ thư mục.
2. **Giao tiếp qua file bàn giao (handoff), không qua code chung.** Hai người trao đổi qua các file CSV/JSON/Cypher có schema cố định (§3). Schema được đóng băng theo lịch; đổi schema phải có cả hai đồng ý.
3. **Trang app tách file.** Streamlit multipage: mỗi trang là một file riêng của một người. Thư viện dùng chung `app/lib/` thuộc B và được đóng băng API sớm.
4. **Báo cáo tách file.** Mỗi mục báo cáo là một file `.tex` riêng; `main.tex` chỉ chứa các lệnh `\input`.
5. **File dùng chung được tách theo người:** `requirements`, `.bib`, hướng dẫn chạy.
6. **PR nhỏ, merge hằng ngày.** Mỗi PR chỉ đụng thư mục của chính mình. Rebase lên `main` trước khi mở PR. Người kia duyệt trong ngày.
7. **Dữ liệu chỉ có một snapshot chính thức.** Sau mốc đóng băng (26/11) không ai đổi dữ liệu đồ thị, trừ sửa lỗi đã được cả hai đồng ý.

---

## 2. Quyền sở hữu thư mục

### 2.1 A (TienHung229)

| Đường dẫn | Nội dung |
|---|---|
| `src/collect/`, `src/clean/`, `src/metadata/` ♻️ | Thu thập, làm sạch (B chỉ chạy, không sửa) |
| `src/nlp/` ♻️ | NER/RE `v3`, tích hợp SLM vào pipeline NLP |
| `src/gold/` (mới) | Chọn tập gold, chia dev/test, chấm P/R/F1, κ |
| `src/audit/`, `src/integration/` ♻️ | Audit cạnh, contract verify |
| `src/trend/` (mới) | Chỉ số M1, M2, M4, M5, M8–M9 |
| `config/contracts/`, `config/a_*`, `config/trend_nlp.json`, `config/trend_metrics.json`, `config/requirements_trend_a.txt` | Cấu hình của A |
| `data/raw/cvpr2025/`, `data/raw/cvpr2026/`, `data/processed/cvpr2025/`, `data/processed/cvpr2026/` | Dữ liệu CVPR mới |
| `data/gold/annotations_A.csv` | Nhãn gold của A |
| `outputs/trend/nlp/`, `outputs/trend/quality/`, `outputs/trend/metrics/` | Kết quả của A |
| `queries/trend_q1.cypher`, `queries/trend_q3.cypher` | Truy vấn multi-hop |
| `app/pages/1_Xu_huong.py`, `app/pages/2a_Chu_de.py` | Trang app 1 và 2a |
| `report/trend/sections/a_*.tex`, `report/trend/a.bib` | Mục báo cáo của A |
| `docs/RUN_A.md` | Lệnh chạy phần của A |

### 2.2 B (Sntug)

| Đường dẫn | Nội dung |
|---|---|
| `src/collect_b/`, `src/graph/`, `src/analysis/` ♻️ | Thu ICCV, dựng và nạp đồ thị, phân tích MXH |
| `src/slm/` (mới) | Client Ollama, cache, đo pilot |
| `src/embed/` (mới) | FastRP/Node2Vec, chủ đề/nhóm tương tự, UMAP |
| `src/rag/` (mới) | GraphRAG local (mở rộng: global) |
| `config/b_*`, `config/trend_graph.json`, `config/trend_sna.json`, `config/trend_slm.json`, `config/trend_rag.json`, `config/requirements_trend_b.txt` | Cấu hình của B |
| `data/raw/iccv2025/`, `data/processed/iccv2025/` | Dữ liệu ICCV mới |
| `data/processed/mxh_cv_trend/graph/` | **Snapshot chính thức** |
| `data/gold/annotations_B.csv` | Nhãn gold của B |
| `outputs/trend/sna/`, `outputs/trend/embed/`, `outputs/trend/rag/`, `outputs/trend/slm_pilot/` | Kết quả của B |
| `queries/trend_q1b.cypher` | Truy vấn nhóm → chủ đề |
| `app/Home.py`, `app/lib/`, `app/pages/2b_Nhom.py`, `app/pages/3_Mang_luoi.py`, `app/pages/4_Hoi_dap.py` | Khung app và trang 2b, 3, 4 |
| `report/trend/main.tex`, `report/trend/sections/b_*.tex`, `report/trend/b.bib` | Khung báo cáo và mục của B |
| `README.md`, `docs/RUN_B.md`, `.github/CODEOWNERS` | Hướng dẫn tổng, phân quyền duyệt |

### 2.3 Chung (sửa qua PR, cả hai phải duyệt)

`docs/SPEC_trend_app.md`, `docs/PLAN_trend_app.md`, `data/gold/gold_set.csv` (danh sách bài gold, do script của A sinh ra rồi khóa), `data/gold/adjudicated.csv` (bản hòa giải).

**`.github/CODEOWNERS`** (B tạo ngày 20/11) ánh xạ các đường dẫn trên tới đúng người, để GitHub tự yêu cầu chủ thư mục duyệt mỗi PR.

---

## 3. File bàn giao (interface) và hạn đóng băng

| ID | File | Người tạo | Người dùng | Đóng băng |
|---|---|---|---|---|
| H1 | Cấu hình project/venue `mxh_cv_trend` (D5) + quy tắc chọn mẫu | A | B | 21/11 |
| H2 | API `src/slm`: `generate_json(prompt, schema, cache_key) -> dict`, `generate_text(...)`, kết quả pilot (model, RAM, tốc độ) | B | A | 21/11 |
| H3 | Danh sách chọn mẫu đã khóa của 5 kỳ (`*_selection.json`) | A (3 kỳ CVPR), B (2 kỳ ICCV) | A | 21/11 |
| H4 | `data/gold/gold_set.csv`: 100 paper ID, cột `split` = dev/test | A (script), cả hai duyệt | Cả hai | 21/11 |
| H5 | Dữ liệu đã làm sạch và verify của từng kỳ mới | A, B | A (NLP) | 23/11 (ICCV 2025, CVPR 2025) · 24/11 (CVPR 2026) |
| H6 | API `app/lib`: `run_cypher(name, **params)`, `load_table(name)`, `render_subgraph(records)`, theme | B | A | 24/11 |
| H7 | Từ điển `v3` + manifest NLP cho tất cả bài | A | B | 25/11 |
| H8 | **Snapshot `mxh_cv_trend`** nạp vào Neo4j hai lần cùng content hash | B | Cả hai | **26/11** |
| H9 | `outputs/trend/sna/communities.csv` (`author_id, community_id`), `pagerank_author.csv`, `pagerank_institution.csv`, `kcore.csv`, `group_ranking.csv` (`venue_edition, community_id, n_papers, n_active_authors, core_author_id`) | B | A (M8–M9), RAG | 27/11 |
| H10 | `outputs/trend/metrics/topic_share.csv`, `topic_change.csv`, `emerging.csv`, `venue_gap_2025.csv`, `topic_leaders.csv` | A | B (RAG, trang 2b) | 27/11 |
| H11 | `queries/trend_q1.cypher`, `trend_q3.cypher` (A), `trend_q1b.cypher` (B): tham số và cột trả về cố định | A, B | RAG, app | 28/11 |
| H12 | `outputs/trend/embed/similar_topics.csv`, `similar_groups.csv` | B | A (trang 2a) | 28/11 |

**Cách làm song song trước khi có file thật:** mỗi người viết code trên **dữ liệu A8 cũ** hoặc **fixture giả** có đúng schema của file bàn giao. Khi file thật đến chỉ cần chạy lại, không sửa code.

---

## 4. Lịch theo sprint

Đường găng (critical path): khóa mẫu (21/11) → gold → từ điển `v3` → NLP (25/11) → **snapshot (26/11)** → bảng phân tích (27/11) → app (29/11–01/12) → báo cáo (03/12).

### Sprint 0 — Khởi động (20–21/11)

**Sprint goal:** khóa mẫu 5 kỳ, chọn tập gold, SLM chạy được trên máy.

| A | B |
|---|---|
| Duyệt spec v0.3 và plan này | Tạo `.github/CODEOWNERS`, khung thư mục mới |
| Quyết định D5: cấu hình project/venue mới có cần đổi contract không → **H1** | Cài Ollama, pilot Qwen2.5-7B trên ~20 abstract: RAM, token/giây, % JSON hợp lệ; chốt 7B hay 3B → **H2** |
| Lấy listing, khóa mẫu CVPR 2025 và CVPR 2026; pilot ~20 bài mỗi kỳ, đo độ phủ abstract và affiliation → **H3** | Lấy listing, khóa mẫu ICCV 2025; pilot ~20 bài → **H3** |
| Đối chiếu mẫu CVPR 2024 với quy tắc chọn | Đối chiếu mẫu ICCV 2023 (gồm pilot) với quy tắc chọn; ghi sai khác |
| Viết `src/gold` chọn 100 bài gold, chia dev/test → **H4** | Kiểm tra yêu cầu endorsement arXiv cho cs.CV; nếu cần thì nhờ giảng viên |

**Checkpoint C0 (21/11 tối):** đủ H1–H4; cả hai đồng ý ngưỡng hiển thị (M4, Q-limit) **trước** khi có dữ liệu.

### Sprint 1 — Dữ liệu và NLP (22–25/11)

**Sprint goal:** 1.750 bài đã làm sạch, từ điển `v3` đóng băng, NLP chạy trên mọi bài.

| Ngày | A | B |
|---|---|---|
| 22/11 | Thu + làm sạch **CVPR 2025** (ưu tiên số 1) | Thu + làm sạch **ICCV 2025** |
| 22–23/11 | Gán nhãn **25 bài dev** của tập gold (độc lập) | Gán nhãn 25 bài dev (độc lập) |
| 23/11 | Verify CVPR 2025 → **H5**; bắt đầu CVPR 2026 | Verify ICCV 2025 → **H5**; viết `app/Home.py`, `app/lib` → **H6** (24/11) |
| 23–24/11 | Chạy SLM đề xuất ứng viên trên bài **ngoài tập gold** của cả 5 kỳ | Viết phần mở rộng `src/analysis` trên dữ liệu A8: ba số khoảng cách, mạng tham chiếu đổi cạnh, PageRank có trọng số, k-core, xếp hạng nhóm theo kỳ |
| 24/11 | **Cùng duyệt ứng viên từ điển (khoảng 2 giờ)**; hòa giải nhãn dev | Cùng duyệt ứng viên; hòa giải nhãn dev |
| 24/11 | Verify CVPR 2026 → **H5**. Nếu chưa xong, **bỏ kỳ này** khỏi snapshot (spec §2.2), không lùi mốc 26/11 | Viết `src/graph` cấu hình `trend_graph.json`, chạy thử trên A8 |
| 25/11 | Chọn cấu hình NER/RE trên tập dev; đóng băng `v3`; chạy NLP trên mọi bài → **H7** | Gán nhãn **75 bài test** (độc lập, làm dần đến 27/11); viết `src/embed` trên A8 |
| 22–27/11 | Gán nhãn 75 bài test (độc lập) | |

**Checkpoint C1 (25/11 tối):** H5 đủ các kỳ được giữ lại, H7 xong, contract verify pass trên đầu ra NLP.

### Sprint 2 — Đồ thị và phân tích (26–28/11)

**Sprint goal:** snapshot đóng băng; có đủ bảng xu hướng, bảng MXH, truy vấn lõi và số liệu chất lượng.

| Ngày | A | B |
|---|---|---|
| 26/11 sáng | Chạy contract verify trên snapshot của B (tool của A) | Dựng snapshot `mxh_cv_trend`, nạp Neo4j hai lần cùng hash → **H8** |
| 26/11 | Chạy `src/trend` trên snapshot (code đã viết sẵn với fixture, gồm ca 14/350 → 28/350) | Chạy `src/analysis` trên snapshot |
| 27/11 | Xuất **H10**; chấm NER/RE trên tập test sau khi đã hòa giải → `outputs/trend/quality/` | Xuất **H9**; chạy embedding → **H12** (28/11) |
| 27/11 | Sinh mẫu audit cạnh (~10/loại) bằng `src/audit` | |
| 28/11 | Viết Q1, Q3 → **H11**; tính M8–M9 với bảng cộng đồng của B | Viết Q1b → **H11**; bắt đầu `src/rag` (luồng local dùng 3 truy vấn) |
| 28/11 | **Cùng chấm audit cạnh, chấm chéo (khoảng 1,5 giờ)** | Cùng chấm audit cạnh |

**Checkpoint C2 (28/11 tối):** H9–H12 đủ; có bảng P/R/F1, κ, audit; ba số khoảng cách và kết luận thế giới nhỏ.

### Sprint 3 — App và GraphRAG (29/11–01/12)

**Sprint goal:** chạy trọn kịch bản demo 5 phút trên snapshot đóng băng.

| Ngày | A | B |
|---|---|---|
| 29/11 | Trang 1 Xu hướng: chọn hội nghị/cặp kỳ/loại chủ đề, bảng M1/M2/M4/M5, khoảng tin cậy | Trang 3 Mạng lưới; hoàn thiện GraphRAG local và hậu kiểm ID/số đếm |
| 30/11 | Trang 2a Chủ đề: Q1/Q3, đồ thị con, chủ đề tương tự, link sang 2b | Trang 2b Nhóm (Q1b) và trang 4 Hỏi đáp |
| 30/11 | Viết 10 câu hỏi kiểm tra kèm đáp án Cypher | Viết 10 câu hỏi kiểm tra kèm đáp án Cypher |
| 01/12 | Đối soát số liệu UI ↔ Cypher ↔ paper ID cho một chủ đề; kiểm các ca biên (§7 spec) | Chấm 20 câu GraphRAG → `outputs/trend/rag/`; đo độ trễ |
| 01/12 | **Cùng chạy thử kịch bản demo 5 phút, ghi lỗi** | Cùng chạy thử |

**Checkpoint C3 (01/12 tối):** demo chạy trọn; danh sách lỗi đã phân loại (sửa trước 03/12 hay ghi vào giới hạn).

### Sprint 4 — Báo cáo và nộp (02–03/12)

**Sprint goal:** repo, dữ liệu, báo cáo arXiv hoàn chỉnh trước 03/12 12:00.

| A | B |
|---|---|
| Mục báo cáo: dữ liệu, NER, RE, đánh giá chất lượng, chỉ số xu hướng (`sections/a_*.tex`) | `main.tex`, mục mở đầu, MXH, SLM/GraphRAG, hệ thống, kết luận (`sections/b_*.tex`) |
| `docs/RUN_A.md` | `README.md`, `docs/RUN_B.md`; kiểm repo có đủ code và dữ liệu |
| Đọc chéo các mục của B, đối chiếu mọi số liệu với output | Đọc chéo các mục của A; quay video demo dự phòng |
| — | **03/12 sáng:** gửi arXiv; lưu minh chứng |
| **03/12 12:00:** cùng gắn tag `v1.0-final` | **03/12 12:00:** cùng gắn tag |

### Sau hạn 03/12 — Trình bày (04–20/12)

| Việc | Người | Hạn |
|---|---|---|
| Khung slide (15–20 trang) theo dàn ý báo cáo | A | 08/12 |
| Slide phần dữ liệu, NLP, xu hướng | A | 10/12 |
| Slide phần MXH, SLM, GraphRAG, demo | B | 10/12 |
| Bộ ~20 câu hỏi dự kiến kèm đáp án (mỗi người 10) | A, B | 12/12 |
| Tập dượt có bấm giờ (20 + 5 + 5 phút), lần 1 và lần 2 | A, B | 14/12, 18/12 |
| Gửi slide và link lên hệ thống | B gửi, A kiểm minh chứng | **19/12** (dự phòng 1 ngày) |

---

## 5. Phần mở rộng (chỉ làm sau C3, theo thứ tự)

| # | Việc | Người |
|---|---|---|
| 1 | GraphRAG global (tóm tắt cộng đồng) | B |
| 2 | Q2 lan truyền qua đồng tác giả; Q5 đường nối | A (Q2), B (Q5) |
| 3 | So sánh SLM đơn / vector RAG / GraphRAG trên 30 câu | B |
| 4 | Mạng tham chiếu hai phía tác giả–bài, ω, Leiden, NMI | B |
| 5 | M3, M6, M7, màn hình Mới nổi riêng | A |

Phần mở rộng làm trên nhánh riêng và chỉ merge nếu không làm thay đổi số liệu lõi.

---

## 6. Quy trình Git

| Quy tắc | Chi tiết |
|---|---|
| Nhánh | A: `a/trend-<việc>`; B: `b/trend-<việc>` (hoặc `Tung`). Không commit thẳng lên `main` |
| PR | Chỉ đụng thư mục của mình (CODEOWNERS sẽ báo nếu vượt). Tiêu đề có mã việc, ví dụ `[H9] bảng cộng đồng` |
| Merge | Người kia duyệt trong ngày; merge theo thứ tự mở PR; rebase lên `main` trước khi merge |
| Dữ liệu lớn | Dữ liệu thô nén `.gz` như hiện tại; kiểm không lộ `.env`/API key trước khi commit |
| Neo4j | Mỗi người chạy instance riêng; chỉ nạp snapshot chính thức, kiểm content hash khớp với H8 |
| Đổi schema bàn giao | Mở issue, cả hai đồng ý, sửa spec trong cùng PR |

---

## 7. Nghi thức Scrum rút gọn

| Nghi thức | Cách làm |
|---|---|
| Daily | Mỗi tối một tin nhắn: đã xong / mai làm / đang vướng (mã H hoặc mã việc) |
| Checkpoint | C0–C3 như trên, khoảng 20 phút: kiểm file bàn giao và test, quyết định cắt phạm vi nếu trễ |
| Review | Tại C3: chạy kịch bản demo |
| Retro | Sau 03/12: 3 dòng mỗi người, ghi vào cuối file này |

---

## 8. Quy tắc cắt phạm vi khi trễ

| Nếu trễ ở | Cắt |
|---|---|
| CVPR 2026 chưa verify xong ngày 24/11 | Bỏ CVPR 2026; bảng chính chuyển thành CVPR 2024→2025 |
| SLM quá chậm | Đổi sang 3B; SLM chỉ xác minh ca mơ hồ, không trích toàn bộ |
| Snapshot trễ sau 26/11 | Giữ nguyên 26/11 với các kỳ đã sẵn sàng; không chờ |
| App trễ ở C3 | Bỏ embedding khỏi trang 2a (giữ bảng H12 trong báo cáo); giữ đủ 4 màn hình lõi |
| Báo cáo trễ | Không làm thêm phần mở rộng nào sau 01/12 |

---

## 9. Ước lượng khối lượng

| Người | Việc chính | Ước lượng |
|---|---|---|
| A | 2 kỳ CVPR, NLP `v3` + SLM, gold và đánh giá, audit, chỉ số xu hướng, Q1/Q3, trang 1 và 2a, 5 mục báo cáo, khung slide | ≈ 8,5 ngày công |
| B | 1 kỳ ICCV, SLM, snapshot, MXH, embedding, Q1b, GraphRAG, khung app + trang 2b/3/4, khung báo cáo + 5 mục, README, arXiv, video | ≈ 9 ngày công |
| Chung | Gán nhãn gold (100 bài/người), duyệt từ điển, chấm audit, chạy thử demo, tập dượt | ≈ 2 ngày công/người |

Thu thập dữ liệu chủ yếu là chờ máy chạy (giới hạn tốc độ của OpenAlex), nên A nhận hai kỳ CVPR. A đã có kinh nghiệm với định dạng CVPR, còn B làm kỳ ICCV như trước.

---

## 10. Retro

*(điền sau 03/12)*
