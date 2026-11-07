# Hợp đồng dữ liệu v2 cho nhóm A và B

Đọc `docs/DATA_CONTRACT.md` để chốt cách lấy nguồn, phân giải danh tính, cập nhật graph, bằng chứng NLP và tăng phiên bản. `schemas/data_contract.json` chốt tên/thứ tự cột cho 12 bảng; các `*.schema.json` chốt kiểu, enum và null. `schemas/data_contract_v1_archive.json` lưu bản đối chiếu v1.

`pilot_v2/` là dữ liệu A1 đã chuyển định dạng: 60 Paper, giữ Paper/source IDs và raw HTML gốc; chưa làm giàu OpenAlex hay tạo graph. `pilot_v2/snapshot_manifest.json` có graph_ready=false, vì vậy không dùng nó để thay một graph đã có dữ liệu. Các bảng nodes/edges chỉ có header; merge/alias/review chưa có quyết định mới.

Code Python 3.12+ dùng standard library. Gói này thêm migration và helper văn bản/evidence; không sửa collector v1 hay loader của B chưa được cung cấp.

```powershell
# Chạy từ thư mục gói v2. --output phải là một thư mục mới.
py -3.12 -m contract_v2.migrate --input ..\mxh_a1_pilot --output pilot_v2_may_toi
py -3.12 -m contract_v2.verify --root pilot_v2_may_toi
py -3.12 -m unittest discover -s tests -v
```

Input là thư mục giải nén gói A1 v1 đã bàn giao. Không cần tải lại CVF, không gọi API và không tác động Neo4j. Nếu input đã có global identity, affiliation, graph hoặc evidence khác A1, migration dừng thay vì đoán provenance hoặc bỏ dữ liệu. Chương trình không ghi đè output đã tồn tại.

Đưa vào repo bằng một nhánh riêng, đối chiếu module của B trước khi ghép. A cập nhật exporter sang schema v2. B cập nhật loader/Method bằng chứng theo contract. Các helper evidence v1 không đủ trường hash nên không dùng để sinh evidence v2. Ghi lại version trong commit/PR; kiểm tra hai máy trước khi mở lô 350.

Không có commit hoặc push GitHub trong gói bàn giao này. Xem `outputs/VERIFICATION.md` cho phần đã chạy thật và giới hạn còn lại.
