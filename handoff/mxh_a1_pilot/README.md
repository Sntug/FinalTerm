# Pilot A1 cho mạng học thuật Computer Vision

Gói này hoàn thành A1 của `Plan_FinalTerm.docx`: schema v1, registry, 30 Paper CVPR 2024 thô và thống kê trường thiếu. Đồng thời kiểm tra 30 URL ICCV 2023 của B và bổ sung metadata CVF để hai bên có cùng định dạng. File đầu vào B được giữ nguyên bytes ở `data/input/`.

**Phạm vi:** 60 bài pilot từ CVF. Chưa thu 350+350, chưa gọi OpenAlex, chưa giải quyết Author identity, chưa chạy NLP/Neo4j hoặc đo số nút/cạnh. Các phần này vẫn thuộc các bước tiếp theo trong plan. Không thay đổi 8 nhãn nút hay 10 loại quan hệ.

## Đọc kết quả

| Tệp | Dùng để làm gì |
|---|---|
| `outputs/REVIEW_A1_B.md` | Kết luận A1, đánh giá B và giới hạn còn lại |
| `data/processed/a_cvpr2024_pilot_registry.csv` | 30 bài của A, schema v1 |
| `data/processed/b_iccv2023_pilot_registry_v1.csv` | 30 bài của B đã kiểm tra, giữ ID và thứ tự gốc |
| `data/processed/paper_registry.csv` | Danh sách chung 60 bài |
| `data/processed/paper_metadata.csv` | Title, authors dạng JSON, abstract và URL; bản xem thuận tiện |
| `data/raw/a_cvpr2024_pilot_papers.jsonl` | 30 Paper thô của A |
| `data/raw/b_iccv2023_pilot_papers.jsonl` | Metadata CVF bổ sung cho 30 URL B |
| `data/raw/pilot_papers.jsonl` | Bản JSON chuẩn để xử lý, 60 dòng |
| `data/raw/source_records.jsonl` | Nguồn, thời điểm UTC, hash và đường dẫn snapshot |
| `data/raw/http/` | HTML nén gzip và metadata cache, cho phép chạy offline |
| `data/processed/authorships.csv` | Lượt đứng tên theo bài; ID người/cơ quan chưa xác minh để trống |
| `data/processed/selection_manifest.json` | Seed, cách chọn và danh sách được khóa |
| `outputs/field_coverage.csv` | Có/thiếu theo trường và theo A/B |
| `outputs/b_registry_review.csv` | Kết quả kiểm tra từng dòng B |
| `outputs/B_registry_schema_v1.diff` | Diff registry B từ 7 cột sang 15 cột |
| `outputs/quality_checks.json` | Kết quả kiểm tra snapshot/khóa ngoại/định dạng |
| `schemas/`, `docs/DATA_CONTRACT.md` | Hợp đồng dữ liệu cho cả hai thành viên |
| `docs/CODEX_HANDOFF.md` | Cách tiếp tục trong repo bằng Codex |

## Chạy trên Windows PowerShell

Mở terminal ở thư mục có `src`, `config`, `data` và `README.md`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m src.collect --offline
.\.venv\Scripts\python.exe -m src.quality
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

A1 dùng thư viện chuẩn Python, không có gói pip bắt buộc. `requirements.txt` giữ vị trí cho dependencies được pin khi triển khai A2/B3. Phiên bản thực tế của môi trường tạo dữ liệu nằm ở `outputs/runtime.json`; xem kết quả kiểm thử ở `outputs/VERIFICATION.md`. Các lệnh Windows được cung cấp để chạy lại, chưa phải bằng chứng đã thử trên Windows.

Trên Linux/macOS, dùng `python3` thay cho `py -3.12` hoặc Python trong venv. Nếu chạy ngoài thư mục gốc, đặt working directory về đây để import được `src`.

## Thu từ mạng hoặc tiếp tục sau lỗi

```powershell
.\.venv\Scripts\python.exe -m src.collect
```

Lệnh dùng lại cache hợp lệ, chỉ tải URL chưa có. Nó tải hai danh sách main conference và 60 trang metadata, không tải PDF/arXiv, không gọi OpenAlex. Mỗi request cách nhau tối thiểu 1 giây tính từ thời điểm bắt đầu request trước; timeout 30 giây; tối đa hai lần retry cho lỗi mạng/5xx, backoff 1 rồi 2 giây. HTTP 403/429 dừng ngay. Không có cache thì `--offline` thất bại rõ ràng. Cache sai hash cũng thất bại, không âm thầm tải lại.

Để thử tải lại từ đầu mà không làm mất snapshot bàn giao, tạo một bản sao của thư mục gói rồi xóa `data/raw/http/` **trong bản sao**. Sau khi chạy, source hash và snapshot có thể đổi vì nguồn đã cập nhật. Không sửa bằng tay raw snapshots; nếu parser đổi thì tăng parser_version và tái tạo đầu ra.

## Quy tắc chốt cùng B

- `paper_id` tiếp tục dùng `cvf:EDITION:SLUG`; khi tìm được DOI/OpenAlex, thêm alias, không đổi ID âm thầm.
- Registry v1 có 15 cột, giữ 7 cột gốc của B và thêm 8 cột. Không nhét mọi dữ liệu vào registry.
- Ô trống CSV và `null` JSON biểu thị chưa biết. Không dùng `Unknown` làm node tổ chức hay dùng 0 thay citation chưa thu.
- `cvf_verified` chỉ xác nhận kiểm tra tự động tại CVF. Nó không xác nhận affiliation, định danh người hay độ chính xác toàn graph.
- `owner` biểu thị trách nhiệm corpus A/B. Đóng góp code phải theo commit thực tế của mỗi người.
- 30 bài A chọn từ full listing theo SHA-256 với seed 20261103. B giữ nguyên manifest đã gửi, seed chưa biết. Khi mở lên 350, giữ 30 bài đã khóa rồi chọn thêm 320 trong phần còn lại.

## Đưa vào GitHub

Giải nén vào một thư mục riêng để kiểm tra. Trong repo nhóm, tạo nhánh `feat/a1-pilot-schema-v1`, chép từng thư mục cần thiết vào repo và xem diff. Nếu repo B đã có file cùng đường dẫn, đối chiếu hoặc nhờ Codex ghép thay đổi trước khi ghi đè.

```powershell
git switch -c feat/a1-pilot-schema-v1
git status --short
git diff
# Thêm các đường dẫn đã kiểm tra, chạy lại ba lệnh xác minh rồi commit.
git add src tests schemas config docs data outputs README.md requirements.txt pyproject.toml .gitignore .gitattributes .env.example
git diff --cached --stat
git diff --cached -- src schemas config
git commit -m "feat: add A1 CVF pilot and shared data contract v1"
```

Gói không có `.git`, remote hoặc commit giả và chưa được push lên GitHub. `.env.example` chỉ là mẫu; không commit `.env`. Snapshot chỉ có metadata HTML, không có PDF toàn bài, API key hay password. Raw cache được giữ để tái lập pilot, không đặt `data/` vào `.gitignore` trong gói này. Khi dữ liệu lớn hơn, nhóm có thể chuyển raw sang nơi khác và ghi rõ cách tải lại.

Khi mở CSV trong Excel, dùng **Data → From Text/CSV**, chọn UTF-8 và dấu phẩy, rồi tải thành Table. Trường `authors_json` phải đọc bằng JSON, không tách tùy ý bằng dấu phẩy. File JSONL và CSV là bản dữ liệu có thể diff; không cần chuyển sang Excel để pipeline chạy.
