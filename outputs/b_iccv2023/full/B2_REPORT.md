# B2 - ICCV 2023: báo cáo (HOÀN TẤT 350/350 matched, needs_review 0; đã chạy bước A3 chuẩn hóa / ghép ID)

Ngày 08/11/2026, nhánh Tung. Chưa commit/push.

## Quy tắc chọn mẫu (đã cập nhật)
- `src/collect_b/select_iccv.py`: các bài pilot khóa (giữ thứ tự, trừ bài bị loại) + các bài còn lại xếp theo SHA-256("20261103\n"+cvf_url) tăng dần, bỏ các bài trong `config/b_iccv2023_excluded.json`, lấy đủ 350. Script chỉ ghi `data/processed/iccv2023/input_registry.csv`; `pilot_input_registry.csv` (pilot lịch sử, 30 dòng) không còn bị ghi lại, nội dung giữ nguyên.
- `config/b_iccv2023_excluded.json`: 19 bài bị loại vì OpenAlex needs_review (paper_id, reason, openalex_candidate, excluded_at). Trong đó có 2 bài pilot bị thay thế (hạng 11 và 20 trong 30 bài pilot); 28 bài pilot còn lại giữ nguyên vị trí đầu danh sách.
- Hội tụ sau 1 vòng thay thế: 19 bài thay thế đều matched, không cần loại thêm.

## Lệnh đã chạy
- `-m src.collect_b.select_iccv` -> `input_registry.csv` (350 bài, 350 id/url duy nhất).
- `-m src.collect --config config/b_iccv2023_350.json` (dùng cache; chỉ 19 request CVF và 38 request OpenAlex cho bài mới): exit 0; chạy lại lần nữa exit 0.
- `-m src.collect.verify --manifest data/processed/iccv2023/full/snapshot_manifest.json`: exit 0 (passed, collection_complete=true), cả trước và sau khi xóa snapshot cũ.
- `-m unittest discover -s quality/checks -p "test_a2_*.py"`: 42 test OK, exit 0.
- Giao với `data/processed/cvpr2024/paper_registry.csv`: 0 theo cvf_url, 0 theo tiêu đề chuẩn hóa.

## Số liệu (350 bài)
- OpenAlex: matched 350, needs_review 0, not_found 0, not_collected 0.
- Paper 350; authorship 1853 (vẫn unresolved, affiliation_verified 0/350); graph_ready=false.
- Coverage: abstract 350/350; references_checked 350/350; affiliation có trong OpenAlex work đã khớp 345/350 (98,57%).
- Snapshot id: `snapshot:v2:693392780e155da50970af544c61519f5954b5c0ccf8bb0c17bcaea6053e0391` (thư mục `full/snapshots/d2a761c0...`); snapshot cũ `2bdc1791...` đã xóa.

## 19 bài bị loại (lý do chi tiết trong file loại trừ)
- Title khớp nhưng byline khác (11): Paredes-Valles_Taming_Contrast_Maximization, Weinzaepfel_CroCo_v2, Liu_LoTE-Animal, Gurbuz_Generalized_Sum_Pooling, Zhou_ProPainter, Kirillov_Segment_Anything, Feng_Generalizing_Neural_Human_Fitting, Zhu_EgoObjects, Yang_LAC, Wei_Generalized_Differentiable_RANSAC, Spencer_Kick_Back_Relax.
- Ứng viên đạt quy tắc nhưng bị đánh dấu cần xem lại (5): Kim_Misalign_Contrast_then_Distill, Khirodkar_Ego-Humans, Yeo_Rapid_Network_Adaptation, Zorzi_RePolyWorld, Zhou_BT2.
- Byline khớp nhưng title không khớp (3): Boutros_IDiff-Face, Song_Emotional_Listener_Portrait, Wang_Building3D.
- Hai bài pilot bị thay thế (hạng 11 và 20) nằm trong các nhóm trên.

## 19 bài thay thế (xếp theo SHA-256, đều matched)
Zhang_Generalizing_Event-Based_Motion_Deblurring, Mani_SurfsUP, Tang_When_Prompt-based_Incremental_Learning, Yang_SEFD, Cancelli_Exploiting_Proximity-Aware_Tasks, Zhu_BiFF, Zhou_Gloss-Free_Sign_Language_Translation, Mensink_Encyclopedic_VQA, Lin_Learning_Vision-and-Language_Navigation_from_YouTube, LI_Calibrating_Uncertainty_Crowd_Counting, Ma_Towards_Fair_and_Comprehensive_Comparisons, Ding_VertexSerum, Fujimura_NLOS-NeuS, Ponghiran_Event-based_Temporally_Dense_Optical_Flow, Ye_Self-Evolved_Dynamic_Expansion_Model, Guan_PIDRo, Segu_DARTH, Liu_Beating_Backdoor_Attack_at_Its_Own_Game, Zeng_MPCViT.

## Ghi chú
- Lịch sử: lần chạy trước (trước khi loại bài) có 331 matched / 19 needs_review; cấu hình `OPENALEX_API_KEY` đã đặt, cache `data/raw/**` nằm ngoài Git.
- Hai file pilot tạm trước đây đã xóa; `config/b_iccv2023_selection.json` không tạo (collector chỉ cần registry_input).
- File mới/đổi: `config/b_iccv2023_excluded.json`, `src/collect_b/select_iccv.py`, `data/processed/iccv2023/input_registry.csv`, `data/processed/iccv2023/full/`, `outputs/b_iccv2023/full/`.

## A3 (chuẩn hóa / ghép ID)
Config: `config/b_iccv2023_a3.json` (input `data/processed/iccv2023/full/snapshot_manifest.json`, output `data/processed/iccv2023/a3_350`, owner B, ICCV 2023, target 350). Config của A có đúng 6 khóa này, không có khóa output/report riêng; A3 chỉ ghi vào `processed_dir`.

### Lệnh và exit code (python3.12 -B -X utf8, từ repo root)
- `-m src.clean --config config/b_iccv2023_a3.json`: exit 0 (delivery_complete=true, network_requests=0).
- `-m src.clean.verify --config config/b_iccv2023_a3.json`: exit 0 (passed, 12 bảng, 29.456 bản ghi, 1.051 raw source, deterministic_replay=true, graph_ready=false).
- Chạy lại `src.clean`: exit 0; SHA-1 của cả 8 file đầu ra giống hệt lần 1 (byte-identical).
- `-m unittest discover -s quality/checks -p "test_*.py"`: 71 test OK, exit 0.

### Số liệu
| Chỉ số | Giá trị |
|---|---|
| Paper input / valid / output | 350 / 350 / 350 |
| Dropped / duplicate / identifier conflict | 0 / 0 / 0 (không auto-merge Paper) |
| Author duy nhất / Institution duy nhất | 1.546 / 300 |
| Authorship (distinct authorship_id) / số dòng | 1.853 / 2.275 |
| Authorship nhiều affiliation | 272 |
| Có Author ID (resolved) / không có | 1.654 / 199 |
| Có affiliation đã xác minh / không | 1.558 / 295 |
| Dòng không có institution_id | 361 |
| Paper có affiliation xác minh | 344/350 |
| Alias | 4.784 |
| merge_log | 6.438 quyết định, toàn bộ `link` (không merge/split) |
| needs_review | 354 (đều `open`) |

### needs_review theo loại
- Paper: 0.
- Author: 199 `identity_conflict` = 108 (tên hồ sơ OpenAlex khác byline CVF/Work, alias cần đối chiếu thủ công) + 91 (không có OpenAlex Author ID hợp lệ hay ORCID theo work; ORCID hồ sơ đơn lẻ không đủ).
- Institution: 155 `affiliation_unresolved` (affiliation thô không ánh xạ hết sang Institution ID đã xác minh; giữ ở dòng null).

### Đối chiếu chéo với CVPR 2024 (A, `a3_350/nodes.csv`, chỉ đọc)
- Author: B 1.546, A 1.550, canonical ID chung 146.
- Institution: B 300, A 294, canonical ID chung 162.
- ID chung dùng cùng canonical ID (OpenAlex). Chưa đối chiếu alias xung đột hay trường hợp chỉ có ORCID/ROR một phía; không gộp theo tên.

### Còn lại cần review thủ công
- 199 Author identity_conflict (108 tên khác + 91 thiếu ID) và 155 affiliation_unresolved; chưa có quyết định merge/split, manual_identity_review_complete=false. Giữ null/status hiện tại tới khi có bằng chứng.
- Cần A/B phối hợp kiểm tra alias xung đột giữa hai corpus trước khi dựng đồ thị. graph_ready=false; chưa làm A4/A5, edges, Neo4j, NetworkX.
- Git: `config/b_iccv2023_a3.json` và `data/processed/iccv2023/a3_350/` (8 file) là untracked, không bị .gitignore chặn; chưa commit.
