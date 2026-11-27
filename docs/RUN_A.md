# Trend app · Dữ liệu CVPR

## Khóa mẫu (H1/H3)

Từ gốc repo, dùng Python 3.12 để replay từ listing đã lưu trong Git và chạy test offline.

```powershell
py -3.12 -B -m src.collect.trend_selection
py -3.12 -B -m src.collect.trend_selection --year 2026
py -3.12 -B -m unittest src.collect.test_trend_selection
```

**CVPR 2025.** [Cấu hình H1](../config/a_trend_project.json) cố định seed `20261103`. Từ listing CVF main track, parser chỉ lấy URL trang chi tiết bài đúng kỳ, bỏ trùng URL chuẩn, xếp tăng theo SHA-256 của UTF-8 `seed + "\n" + canonical_url`, hòa thì xét URL. Chọn 350/2.871 bài đầu. Khi thu metadata, bài thiếu abstract vẫn giữ ID và thứ hạng. [Danh sách xếp hạng](../data/processed/cvpr2025/candidates_ranked.csv) ghi toàn bộ ứng viên. [Lock](../config/a_cvpr2025_350_selection.json) ghi nguồn listing, hash raw, hash thứ hạng và hash registry. B và A dùng [input registry](../data/processed/cvpr2025/input_registry.csv) cho H4/H5. DOI và source ID của trang chi tiết để trống đến khi có bằng chứng từng bài. Replay từ chối ghi đè file khác byte.

**CVPR 2024.** Replay kiểm hash listing, hash bảng xếp hạng và registry đầu vào của lock cũ, rồi đối chiếu ID theo thứ tự với registry A5. Trong 2.715 ứng viên, mẫu thực tế khớp top 350 ở **350/350 ID và 350/350 vị trí**, kể cả 30 bài pilot giữ lại. Điều kiện chọn mẫu đạt. Độ phủ văn bản và tỷ lệ NLP chạy thành công cần đo riêng trước khi gắn nhãn xu hướng. [Kết quả đối chiếu](../outputs/trend/quality/cvpr2024_selection.csv)

**D5.** Giữ schema v2, 8 nhãn và 10 loại cạnh. Fixture kiểm đường đi `Paper → PUBLISHED_IN → venue:CVPR:2025:main` qua graph exporter và bước đọc/kiểm hash trước import với `project_id=mxh_cv_trend`. Verifier metadata hiện đối chiếu project với `mxh_cv_700` trong contract cũ. H5 có thể tiếp tục xuất metadata trung gian theo quy ước này. Exporter và verifier H7 dùng `mxh_cv_trend` và `graph_ready=true` theo giao diện H8 trong PR #24. H8 vẫn cần kiểm contract đầy đủ và hai lượt nạp Neo4j trên snapshot thật.

**CVPR 2026.** Cùng seed và quy tắc trên, khóa 350/4.042 ứng viên main track. H4 dùng [registry theo thứ hạng](../data/processed/cvpr2026/input_registry.csv). [Lock](../config/a_cvpr2026_350_selection.json) lưu hash của listing và registry. Pilot metadata ở phần H5 đo độ phủ trên 20 bài đầu tiên.

## Tạo và kiểm tập gold (H4)

Từ gốc repo, dùng lệnh đầu để sinh CSV, lệnh sau để đối chiếu từng byte mà không ghi file.

```powershell
py -3.12 -B -m src.gold
py -3.12 -B -m src.gold --check
```

Script chỉ đọc cấu hình H1 và năm lock H3, dùng bản `trend` cho ICCV 2023. Mỗi kỳ có 350 ID. Sau khi kiểm hash danh sách trong lock, script xếp ID tăng dần theo SHA-256 của UTF-8 `H4\n20261103\n<paper_id>` (hai dấu `\n` là ký tự xuống dòng), hòa thì xét ID. Lấy 5 ID đầu làm dev, 15 ID kế làm test. Trong [gold_set.csv](../data/gold/gold_set.csv), `selection_rank` là thứ hạng gốc trong H3 và `source_snapshot_id` xác định lock nguồn. Chạy lại gặp CSV khác byte sẽ báo lỗi.

A và B cùng duyệt danh sách 100/1.750 ID. Loại cả 100 ID khỏi pilot SLM, few-shot và khai thác ứng viên từ điển. Hai người gán nhãn dev độc lập, chỉ mở abstract test sau khi đóng băng từ điển, prompt và cấu hình. Nếu nhóm bỏ một kỳ, bỏ đúng 20 ID của kỳ đó theo PLAN.

## Chuẩn bị abstract cho H7

Chạy từ gốc repo. Chọn `dev` để chuẩn bị abstract cho hai người gán nhãn độc lập. Chọn `candidates` để lấy văn bản ngoài toàn bộ tập gold cho bước đề xuất khái niệm.

```powershell
py -3.12 -B -m src.nlp.h7_inputs --edition CVPR2025 --manifest data/processed/cvpr2025/h5/snapshot_manifest.json --group dev
py -3.12 -B -m src.nlp.h7_inputs --edition CVPR2025 --manifest data/processed/cvpr2025/h5/snapshot_manifest.json --group candidates
```

| Kỳ | Thư mục chứa `snapshot_manifest.json` | Abstract dev / ID dev |
|---|---|---:|
| CVPR2024 | `data/processed/cvpr2024/a5_350` | 5/5 |
| CVPR2025 | `data/processed/cvpr2025/h5` | 5/5 |
| CVPR2026 | `data/processed/cvpr2026/h5` | 5/5 |
| ICCV2023 | `data/processed/iccv2023/trend/h5` | 5/5 |
| ICCV2025 | `data/processed/iccv2025/h5` (PR #24, commit `f913f51`) | 5/5 |

Đầu ra ở `outputs/trend/nlp/inputs/<kỳ>_<nhóm>.jsonl`. Mỗi dòng gồm ID bài, văn bản chuẩn hóa, `text_version_id`, nguồn CVF, hash H4 và ID snapshot. Script kiểm lại H4, đối chiếu registry với H3 và lọc ID trước khi mở HTML của từng bài. Bài ngoài phạm vi core/main, chưa xác minh hoặc thiếu provenance abstract được bỏ qua. Nguồn abstract ngoài CVF hoặc hash sai sẽ báo lỗi. Khi gán nhãn dev, tính offset trên trường `normalized_text`. Manifest NLP cuối được tạo ở bước sau khi đã duyệt và đóng băng cấu hình.

## Gán nhãn gold độc lập

Mỗi người làm việc trên bản CSV local của mình. Dùng 25 abstract dev từ năm gói ở trên. Gold theo SPEC §4.4 chỉ chấm abstract. Pipeline sản xuất đọc cả title và abstract; khi chấm gold, chỉ lấy dự đoán gắn đúng `text_version_id` của abstract. Hai người hoàn thành lượt gán độc lập rồi mới chia sẻ để hòa giải. Test chỉ mở sau khi đóng băng từ điển, prompt và cấu hình.

| Cột CSV | Cách điền |
|---|---|
| `annotator`, `annotation_origin` | Bên chịu trách nhiệm (A hoặc B) và nguồn tạo nhãn thực tế. Phân biệt lượt người tự gán, nhãn có hỗ trợ và lượt người đã duyệt. |
| `split`, `venue_edition`, `paper_id` | Chép split từ H4 và kỳ/ID từ gói văn bản. |
| `text_version_id`, `normalized_text_sha256` | Chép nguyên từ dòng JSONL của bài để cố định văn bản. |
| `start_char`, `end_char`, `evidence_text` | Một dòng cho mỗi lần nhắc. Chọn cụm ngắn nhất còn đủ nhận diện khái niệm, giữ thành phần phân biệt phiên bản hoặc biến thể. Đếm ký tự Unicode từ 0, đầu đóng và cuối mở. Sao chép nguyên văn chữ hoa, dấu và khoảng trắng. Kiểm `normalized_text[start_char:end_char] == evidence_text`. |
| `entity_type` | `Task` cho bài toán, `Method` cho phương pháp/mô hình, `Dataset` cho bộ dữ liệu cụ thể. Tên đầy đủ và chữ viết tắt riêng biệt có thể có hai span trỏ cùng khái niệm. |
| `entity_id`, `entity_name` | Với khái niệm đã biết, dùng ID và tên chuẩn theo từ điển. Với khái niệm mới, để ID rỗng, điền tên mô tả nhất quán trong cột tên để hòa giải. Gold được giữ riêng khỏi nguồn khai thác ứng viên v3. |
| `relation_type` | Ghi `STUDIES_TASK` khi tác giả nghiên cứu bài toán, `USES_METHOD` khi họ sử dụng hoặc triển khai phương pháp, `EVALUATED_ON` khi họ đánh giá trên bộ dữ liệu. Để trống nếu lần nhắc chỉ là bối cảnh, so sánh, phủ định, dự định, dữ liệu huấn luyện hoặc chưa đủ bằng chứng. |

Ví dụ giả lập: trong `We evaluate on ExampleSet.`, span Dataset là `ExampleSet`, offset `[15,25)`, quan hệ `EVALUATED_ON`. Khi một cụm xuất hiện nhiều lần, xác định vị trí và quan hệ riêng theo ngữ cảnh từng lần.

## Xuất và verify NLP Trend sau khi đóng băng

Cấu hình `config/trend_nlp.json` đọc danh sách H5 theo đúng thứ tự trong `config/trend_graph.json` của PR #24. Đường chạy luật dùng từ điển hợp nhất có `version="v3"` và ba danh sách `tasks`, `methods`, `datasets`. Tham số `model="blank"` chọn tokenizer spaCy tiếng Anh. Nhóm cần hoàn tất duyệt từ điển và chọn cấu hình trên dev trước khi chạy toàn corpus.

```powershell
py -3.12 -B -m src.nlp --config config/trend_nlp.json
py -3.12 -B -m src.nlp.verify --config config/trend_nlp.json
```

Đích bàn giao là `data/processed/mxh_cv_trend/nlp/`. Kiểm tra `summary.json` có số cạnh dương cho đủ năm kỳ, verify replay pass và manifest có `graph_ready=true`, phiên bản code/model, hash từ điển và hash các bảng. Prefix evidence mới có dạng `v3-task-…`, `slm-method-…` hoặc tương tự theo đúng loại thực thể. Các bản A4/B5 cũ dùng cấu hình và kiểu manifest trung gian của chúng.

## Metadata CVPR 2025 và 2026 (H5)

Chạy từ gốc repo với Python 3.12. Replay dùng các phản hồi CVF và OpenAlex đã lưu. Để thu lần đầu, bỏ `--offline` ở lệnh collector và cấu hình `OPENALEX_API_KEY` trong môi trường hoặc file `.env` local.

```powershell
$year = 2026  # Đổi thành 2025 để replay kỳ trước
py -3.12 -B -X utf8 -m src.collect --config "config/a_cvpr${year}_350.json" --offline
py -3.12 -B -X utf8 -m src.clean --config "config/a_cvpr${year}_h5.json"
py -3.12 -B -X utf8 -m src.clean.h5_coverage --year $year
```

H7 đọc từng bảng theo trường `files` của [manifest 2025](../data/processed/cvpr2025/h5/snapshot_manifest.json) hoặc [manifest 2026](../data/processed/cvpr2026/h5/snapshot_manifest.json). Bảng dùng chung với snapshot collector có thể nằm ngoài thư mục `h5/`. Lệnh cuối verify lại snapshot, so rank, ID và URL với lock rồi xuất [độ phủ 2025](../outputs/trend/quality/cvpr2025_h5.json) hoặc [độ phủ 2026](../outputs/trend/quality/cvpr2026_h5.json). Một bài có affiliation khi có ít nhất một tác giả liên kết được với tổ chức qua bằng chứng của chính bài đó. Ở mức lượt tác giả, đếm `authorship_id` riêng biệt để một tác giả có nhiều tổ chức vẫn chỉ tính một lần. Các liên kết thiếu bằng chứng giữ null. Xem `needs_review.csv` theo manifest.

Để tái tạo [pilot metadata CVPR 2026](../outputs/trend/quality/cvpr2026_pilot.json), chạy `py -3.12 -B -X utf8 -m src.integration.cvpr_metadata_pilot`. Pilot đếm tổ chức xuất hiện trong Work OpenAlex đã khớp. H5 đo liên kết đã qua bước xác minh danh tính và affiliation theo bài.

Với CVPR 2026, quy tắc `openalex-work-match` v1.2.0 kiểm tra tiêu đề, đủ tác giả theo đúng thứ tự và bằng chứng DOI, hội nghị/năm hoặc liên kết phiên bản. Dạng tên “họ, tên” được đối chiếu với cách ghi gốc tại cùng vị trí trên CVF. Liên kết arXiv kiểm mã bài trên URL chính thức, phiên bản chỉ định và năm xuất bản. Trong báo cáo H5, nhóm `linked_version_only` cho biết tổ chức được ghi trên Work liên kết. Khi dùng Q1/Q3, cần ghi rõ nguồn này vì affiliation có thể thay đổi giữa bản preprint và thời điểm hội nghị.
