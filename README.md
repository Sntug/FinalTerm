# Đề tài 30 · Mạng tác giả và tổ chức nghiên cứu thị giác máy tính

Một dự án chung cho A (350 bài CVPR 2024) và B (350 bài ICCV 2023), chỉ lấy bài main conference. Cả nhóm dựng một graph Neo4j gồm 8 loại nút và 10 loại quan hệ có bằng chứng. Mốc nghiệm thu là ít nhất 2.000 nút và 5.000 cạnh duy nhất.

| Đường dẫn | Dùng để làm gì |
| --- | --- |
| `src/collect/`, `src/clean/` | Collector chung, ghép bản ghi nguồn và chuẩn hóa Paper, Author, Institution. |
| `src/nlp/`, `config/` | Rule Task và Dataset (A), Method (B), từ điển dùng chung, phạm vi lấy mẫu và hợp đồng dữ liệu. |
| `src/graph/`, `queries/` | Sinh nút/cạnh, nạp Neo4j, lưu ràng buộc và truy vấn Cypher (B). |
| `src/analysis/`, `outputs/` | Phân tích NetworkX từ Neo4j, bảng chỉ số, biểu đồ và hình case study (B). |
| `data/raw/cvpr2024/`, `data/raw/iccv2023/` | Snapshot nguồn và manifest riêng cho mỗi hội nghị. Dữ liệu thô nằm ngoài Git. |
| `data/paper_registry.csv` | Vị trí registry chung do A tạo. Ghi URL/ID, hội nghị, trạng thái và owner của từng bài. |
| `data/processed/` | Dữ liệu chuẩn hóa dùng chung, gồm source records, papers/authorships, nodes/edges/evidence, alias map, merge log và needs review. Phân biệt Paper core và reference theo hợp đồng dữ liệu. |
| `quality/`, `quality/checks/` | Mẫu audit và các kiểm tra định danh, chất lượng cạnh, nhập lại Neo4j. |
| `report/` | Báo cáo nhóm, tài liệu tham khảo và bản nộp. |

## Bắt đầu pilot

1. Tạo repo GitHub chung từ thư mục này. B sao chép `.env.example` thành `.env` và điền thông tin Neo4j cục bộ khi đã có database.
2. Schema hiện hành là v2 tại `config/contracts/v2/data_contract.json` và các `*.schema.json` cùng thư mục. Quy tắc nguồn/ID nằm trong `handoff/mxh_contract_v2/docs/DATA_CONTRACT.md`. A tạo registry và collector chung theo hợp đồng này.
3. A đăng ký 30 bài CVPR 2024. B đăng ký 30 bài ICCV 2023 với `owner=B` và thử nạp vào Neo4j.
4. Chạy đủ 60 bài từ raw qua clean/NLP tới Neo4j. Kiểm tra ghép ID, dữ liệu thiếu và số nút/cạnh trước khi thu hàng loạt 350 bài mỗi người.

Khung thư mục của nhóm được giữ nguyên. Phần tích hợp offline và các lệnh đã có được ghi bên dưới; chưa có pipeline NLP/Neo4j trong checkout này.

## A2: collector CVF/OpenAlex và pilot

Pilot ngày 08/11/2026 đã xử lý đúng 30 bài A khóa từ A1: 30 Paper hợp lệ, 27 Work matched, 0 not_found, 3 needs_review. Toàn bộ authorship vẫn unresolved; không gán affiliation chỉ dựa vào tên. Chưa chạy 350 bài.

Code dùng chung cho CVPR 2024 và ICCV 2023. Config có owner, conference/year, target_count, registry_input, seed, đường dẫn, timeout/retry và giãn request. A dùng `config/a_cvpr2024_pilot.json`; B tự tạo config từ `config/collector.example.json` và cung cấp registry của mình. Registry phải có đúng target_count dòng, không trùng ID/URL. Với config A, selection_file còn kiểm tra đúng 30 ID, URL, source ID và thứ tự đã khóa.

Chạy tại repo root, Python 3.12+ và thư viện chuẩn:

```powershell
py -3.12 -B -X utf8 -m src.collect --config config/a_cvpr2024_pilot.json
py -3.12 -B -X utf8 -m src.collect --config config/a_cvpr2024_pilot.json --offline
py -3.12 -B -X utf8 -m src.collect.verify --manifest data/processed/cvpr2024/pilot/snapshot_manifest.json
py -3.12 -B -X utf8 -m unittest discover -s quality/checks -p "test_a2_*.py" -v
```

Các lệnh trên đã qua trên Windows/Python 3.12.10. Có 37 test, kể cả fixture ICCV trong thư mục tạm. Chi tiết coverage, nguồn, review và log: [báo cáo pilot](outputs/a2_cvpr2024/pilot/PILOT_REPORT.md). Biên bản: [A2_HANDOFF](handoff/a/A2_HANDOFF.md).

| Vị trí | Nội dung |
| --- | --- |
| `config/contracts/v2/` | Contract và schema v2 nguyên byte từ bàn giao |
| `src/collect/`, `src/clean/text.py` | Collector, cache, Work matching, exporter/verifier và helper văn bản |
| `data/raw/cvpr2024/` | Raw CVF/OpenAlex, metadata cache, quota gates và collector_checkpoint.json |
| `data/processed/cvpr2024/pilot/snapshot_manifest.json` | Manifest hiện hành; paths tương đối repo root |
| `data/processed/cvpr2024/pilot/snapshots/<digest>/` | 12 bảng bất biến theo contract v2 và manifest lưu trữ |
| `outputs/a2_cvpr2024/pilot/` | Summary, matching audit, báo cáo và log chạy/test |

Verifier nhận đường dẫn manifest riêng. Consumer đọc bảng theo manifest, không giả định bảng nằm trực tiếp dưới data/processed. Snapshot có graph_ready=false; nodes/edges rỗng, node_count/edge_count=null. Chưa ghi registry chung hoặc dữ liệu ICCV của B.

Cache giữ bytes nguồn, thời điểm và hash. `--offline` không gọi mạng. Chạy lại dùng cache và giữ nguyên snapshot nếu dữ liệu không đổi. Cache sai hash hoặc bảng bất biến bị sửa làm lệnh dừng. Các bản partial/cũ được giữ trong snapshots; manifest hiện hành cập nhật sau verify. Resume tái tính từ cache, không tin checkpoint thay cho hash. Chỉ chạy một writer cho mỗi config.

Khi nguồn hết quota hoặc Retry-After dài, chương trình lưu checkpoint/gate và thoát 2; lệnh trên dùng để tiếp tục sau thời điểm được phép. HTTP 403 CVF dừng ngay. OpenAlex dùng header Authorization khi có OPENALEX_API_KEY trong biến môi trường hoặc .env, không lưu key trong URL/log/cache. Pilot hiện dùng truy cập cơ bản không key. Chính sách API và các giới hạn đã kiểm tra được dẫn nguồn trong báo cáo.

Máy mới cần raw/cache để replay offline vì raw vẫn bị Git ignore. Để khôi phục riêng cache CVF A1, có thể dùng `py -3.12 -B -X utf8 -m src.collect.bootstrap --input handoff/mxh_a1_pilot`; lệnh này đọc gói như dữ liệu, không import code từ handoff. Registry A1 đầu vào ở data/processed/cvpr2024/paper_registry.csv được giữ nguyên. Cache OpenAlex phải chuyển riêng hoặc chạy collector online. `.gitattributes` bảo toàn bytes schema và processed A qua checkout Windows.

## OpenAlex key và kiểm tra bàn giao cho B

Kiểm tra ngày 08/11/2026: key nạp được, đúng một GET `https://api.openalex.org/works?per_page=1` qua Bearer header trả HTTP 200. Không chạy lại collector 30/350 bài ở bước này. Báo cáo không chứa key/header/body: `outputs/a2_cvpr2024/pilot/auth_check.json`.

Thứ tự nạp: **OPENALEX_API_KEY trong môi trường nếu không rỗng**, sau đó mới dùng OPENALEX_API_KEY trong `.env` ở repo root. Biến môi trường rỗng/không có cho phép fallback. Đường dẫn mặc định lấy từ vị trí mã nguồn (`REPO_ROOT`), không tìm `.env` theo thư mục terminal; khi chủ động dùng `--root`, đó là root cấu hình. Chỉ đọc key, không ghi `.env` hoặc thay các biến môi trường khác. Hỗ trợ giá trị một dòng, dấu nháy và comment; không nội suy biến hay thực thi biểu thức shell. Không cần python-dotenv/dependency ngoài, không cài hoặc thay môi trường global.

Lệnh riêng kiểm tra một request, không retry, không cache hoặc tải response body:

```powershell
py -3.12 -B -X utf8 -m src.collect.auth_check
```

Chạy lệnh module tại repo root hoặc bảo đảm repo có trên Python import path. Việc tìm module của Python và việc tìm `.env` là hai việc riêng; loader key đã được test từ working directory khác. Chỉ trả boolean key_loaded/success, HTTP status và loại lỗi đã lọc: authentication (401/403), rate_limit (429), network, http hoặc configuration/missing_key. Lỗi xác thực không trở thành Work not_found.

Collector/config đã sẵn sàng gửi B để chạy pilot ICCV trên máy B. Gửi `src/collect`, `src/clean`, `config/contracts/v2`, `config/collector.example.json`, `quality/checks/test_a2_*.py`, README và các quy tắc Git hiện có. Không đưa `.env` vào gói bàn giao; B tự điền key từ `.env.example`. B cần cung cấp registry ICCV của mình ở registry_input, sửa config từ mẫu, giữ raw/export/report tách riêng, rồi chạy test/pilot. Fixture ICCV đã qua; chưa chạy dữ liệu B thật.

Trước lô 350, cần registry đủ 350 và manifest đã chốt (A giữ 30 cũ); không chỉ đổi target_count trong config A pilot đang khóa 30. Ba Work A cần review và danh tính/affiliation chưa resolve vẫn giữ trạng thái hiện có. Xem `outputs/a2_cvpr2024/pilot/B_READINESS.md`.
