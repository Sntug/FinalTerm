# Bàn giao A3 — làm sạch và phân giải thực thể

Nhánh `feat/a3-clean-resolution`, từ A2 `98b9716`. Chỉ dùng raw/snapshot đã có, không gọi API, không sửa schema v2 hoặc snapshot A2. A3 hoàn tất pipeline và bộ dữ liệu bàn giao; review danh tính thủ công vẫn còn mở. Không suy ra precision, NLP, graph hoặc pilot nhóm đã đạt.

## Chạy trên Windows PowerShell

Tại repo root, Python 3.12+, chỉ thư viện chuẩn:

```powershell
py -3.12 -B -X utf8 -m src.clean --config config/a_cvpr2024_a3.json
py -3.12 -B -X utf8 -m src.clean.verify --config config/a_cvpr2024_a3.json
py -3.12 -B -X utf8 -m unittest discover -s quality/checks -p "test_*.py" -v
```

Pipeline luôn offline. Exit 1 khi input/hash/schema không hợp lệ; exit 2 khi số Paper core hợp lệ khác target; vẫn báo chênh lệch, không chọn bù. Input phải là manifest A2 qua verifier collector, đúng owner/edition/core/main. Chạy lại cùng input/output giữ nguyên byte; output có thay đổi bên ngoài bị từ chối ghi đè. Khi đổi input/rule, chọn thư mục A3 mới; không sửa snapshot đã xuất.

## Input/output và quy tắc

Input: `data/processed/cvpr2024/a2_350/snapshot_manifest.json`, 12 bảng được manifest chỉ tới và raw gzip trong `data/raw/cvpr2024/`. [Bàn giao A2](A2_HANDOFF.md) mô tả collector/cache.

Output: `data/processed/cvpr2024/a3_350/snapshot_manifest.json`. **Luôn đọc đường dẫn bảng từ manifest**: bảng không đổi được tham chiếu trực tiếp tới A2 để tránh bản sao. Giữ cả snapshot A2 và raw khi bàn giao.

| Bảng/file | Nội dung |
| --- | --- |
| `papers.jsonl` | Tương đương `papers_clean`: 350 Paper chuẩn; byte hiện tại đã sạch nên tái sử dụng bảng A2 |
| `paper_registry.csv`, `text_versions.jsonl`, `source_records.jsonl`, `field_provenance.csv` | Registry, văn bản, raw pointers và provenance v2; tái sử dụng nếu không đổi |
| `authorships.csv` | Lượt đứng tên CVF, ID người, nhiều affiliation, trạng thái và nguồn riêng |
| `nodes.csv` | Metadata Author/Institution đã resolve theo schema có sẵn; tên/alias trong `properties_json` |
| `alias_map.csv`, `merge_log.jsonl` | ID nguồn → canonical ID, quyết định `link` có bằng chứng và before/after |
| `needs_review.csv`, `evidence.jsonl` | Vấn đề chưa giải quyết, raw source/field đối chiếu |
| `edges.csv` | Rỗng; `graph_ready=false`, node_count/edge_count vẫn null |
| `cleaning_summary.json` | Số liệu thực và chênh lệch, nằm cạnh manifest A3 |

- Unicode NFC, HTML entities, BOM/NUL và khoảng trắng được xử lý; giữ dấu câu/ký tự có nghĩa. DOI/URL/ID nguồn được chuẩn hóa bảo thủ. Khi text đổi, tạo text version mới, giữ version cũ và raw; không đổi normalizer `nfc-ws-1` của contract. Giữ conference/year/date/scope/owner và ID CVF đã khóa.
- CVF quyết định title và toàn bộ ordered byline. Work đã ghép ở A2 được kiểm tra lại từ raw. DOI/Work ID/CVF URL và link arXiv trực tiếp từ CVF là alias cùng Paper; link arXiv không khẳng định đã đọc nội dung preprint. Title/byline/năm chỉ tạo ứng viên review. Hai canonical Paper ID đụng định danh phải review thủ công; không tự gộp để giảm/tăng quota.
- Author ID dùng `author:openalex:A...`, hoặc `author:orcid:...` khi chỉ có ORCID hợp lệ của đúng lượt đứng tên. Cần toàn bộ thứ tự tác giả khớp, ID không lặp trong bài/không mâu thuẫn trong batch; tên hồ sơ khác byline phải review. ORCID có kiểm tra checksum; không gộp hai OpenAlex ID chỉ vì cùng ORCID/tên. Cùng ID đã đối chứng trên nhiều Paper dùng một Author.
- Institution dùng `institution:openalex:I...` hoặc `institution:ror:...`, kiểm tra ROR checksum. Tên được chuẩn hóa, alias lưu trên cùng ID; không gộp đơn vị mẹ/con theo tên hoặc lineage. Không có node `Unknown`. Chỉ dùng institutions/affiliations của Work, không dùng cơ quan hiện tại của hồ sơ Author.
- Một authorship có nhiều Institution tạo nhiều dòng cùng authorship_id. `affiliation_raw` là **chuỗi JSON array trong cột string hiện hữu**, giữ ranh giới các chuỗi gốc; dùng `json.loads` nếu cần đọc từng chuỗi. Chỉ gán chuỗi cụ thể cho Institution khi `affiliations[].institution_ids` chỉ đúng ID. Chuỗi chưa ghép vẫn nằm ở dòng institution_id rỗng, status=needs_review. Đếm DISTINCT authorship_id, không đếm số dòng CSV thành số người.
- `merge_log` hiện chỉ có `action=link`, `review_mode=rule`, reviewer là `a3-exact-source-link-1.0.0`, không giả người duyệt A/B. `$row` mô tả tạo một alias; `$rows` thay toàn bộ nhóm authorship theo record_key, lưu đủ before/after. Đây là quy ước áp dụng log trong schema v2, không thêm cột. Merge/split canonical ID cần manual A/B theo contract; chưa có quyết định thủ công được cung cấp để áp dụng.

## Kết quả trên 350 CVPR

| Chỉ số | Thực tế |
| --- | --- |
| Input / core hợp lệ / output | 350 / 350 / 350 |
| Paper bỏ / trùng định danh / tự merge canonical ID | 0 / 0 / 0 |
| Author / Institution đã resolve, duy nhất | 1.550 / 294 |
| Lượt đứng tên / dòng authorship nhiều affiliation | 1.968 / 2.109 |
| Lượt có Author ID / thiếu Author ID | 1.628/1.968 / 340/1.968 |
| Lượt có affiliation xác minh / chưa có | 1.502/1.968 / 466/1.968 |
| Dòng không Institution ID / tổng dòng | 469/2.109 |
| Lượt có nhiều Institution / Paper có affiliation xác minh | 112/1.968 / 322/350 |
| Alias / quyết định link | 4.661 / 6.289 |
| Review: Paper / Author / Institution | 22 / 340 / 123 = 485 |

22 review Paper kế thừa A2 là Work bổ sung chưa ghép chắc chắn, không phủ nhận điều kiện core CVF. 340 review Author gồm 140 lượt chưa có Work và 200 lượt xung đột ID/tên; 123 review Institution là các lượt chưa ánh xạ hết affiliation. 485 là số **vấn đề**, không phải số thực thể duy nhất.

Kiểm tra: 71 tests (46 A2 + 25 A3), gồm ICCV fixture, homonym, ID/ORCID/ROR conflict, thiếu abstract, nhiều affiliation, byte replay, output bị sửa và resume khi thiếu manifest. Verifier kiểm 12 bảng, 28.816 records, 1.032 raw sources và dựng lại toàn bộ A3. Bằng chứng: `outputs/a3_cvpr2024/tests.log`, `outputs/a3_cvpr2024/verification.json`.

## B chạy ICCV 2023

Tạo config riêng, không sửa config của A; thay `input_manifest` bằng snapshot A2 thực của B:

```json
{
  "input_manifest": "data/processed/iccv2023/a2_350/snapshot_manifest.json",
  "processed_dir": "data/processed/iccv2023/a3_350",
  "owner": "B",
  "conference": "ICCV",
  "conference_year": 2023,
  "target_count": 350
}
```

Lưu thành `config/b_iccv2023_a3.json`, chạy hai lệnh `src.clean` và `src.clean.verify` với config đó. Các đường dẫn là từ repo root; `--root` hỗ trợ clone khác. Fixture ICCV đã qua, chưa xác nhận 350 ICCV thật của B. ID OpenAlex giống nhau dùng cùng canonical ID ở hai corpus; khi phối hợp hai snapshot cần đối chiếu alias xung đột và trường hợp chỉ có ORCID/ROR ở một phía, không union theo tên. Pipeline nhận A2 và xuất A3 mới, không sửa trực tiếp quyết định của A3 cũ.

## Review và nghiệm thu

Đã đạt đầu ra kỹ thuật A3: 350 Paper core duy nhất, bảng authorship giữ đủ lượt, provenance/alias/decision/review hợp lệ, chạy offline và dùng lại cho B. Không còn lỗi chạy/test đã biết.

Chưa hoàn tất review danh tính/affiliation và kiểm tra precision thủ công. A/B cần quyết định 22 Work ứng viên, tên hồ sơ/ID mâu thuẫn của 340 lượt Author và ánh xạ 123 trường hợp affiliation. Giữ null/status hiện tại cho tới khi có bằng chứng. Thiếu abstract/affiliation không loại Paper core. Không tự phê duyệt merge/split; khi có quyết định, giữ lịch sử cũ và lập snapshot mới theo contract. Không thay đổi quy tắc/schema của B và không thực hiện A4, A5, edges, Neo4j hay NetworkX.
