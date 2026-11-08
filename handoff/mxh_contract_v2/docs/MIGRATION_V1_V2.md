# Chuyển từ A1 v1 sang hợp đồng v2

Không đổi dữ liệu nguồn v1 hoặc ghi đè thư mục input. Gói A1 v1 vẫn là bản lịch sử có thể tái lập bằng code v1. Hợp đồng v2 áp dụng cho các bản export mới; không chỉ thay nhãn version rồi coi dữ liệu đã đạt điều kiện mới.

| V1 | V2 | Cách xử lý |
|---|---|---|
| Registry 15 cột | Giữ 15 cột | Giữ ID/thứ tự/giá trị; export mới ghi schema_version=2.0.0 |
| pilot_papers.jsonl là quan sát CVF | papers.jsonl là Paper chuẩn | Giữ raw quan sát ở legacy_v1, dùng bảng chuẩn riêng |
| paper.source_record_id | representative_source_record_id | Giữ cùng ID nguồn, ghi provenance của từng trường riêng |
| title_raw/abstract_raw trong quan sát | text_versions.jsonl | Chuẩn hóa nfc-ws-1, hash toàn trường, khóa parser và source |
| author entries name/name_raw/order | Thêm authorship_id cho mỗi entry | Dùng công thức ID lượt đứng tên đã có, không tạo ID người |
| Authorship 11 cột | 15 cột | Bổ sung nguồn identity, nguồn affiliation, trạng thái affiliation và decision_ids |
| Không có field provenance | field_provenance.csv | Ghi nguồn/selector của trường CVF đang được chọn; không giả tạo nguồn OpenAlex |
| Source record schema 1.0.0 | Export wrapper schema 2.0.0 | Raw bytes/content_sha256/source_record_id giữ nguyên; bản JSON cũ còn trong legacy_v1 |
| Evidence v1 chưa tạo | Evidence v2 có text pinning | File mới rỗng ở A1; không tự chế câu, offset hoặc dấu review |
| Merge/alias chưa có | File đúng schema, chưa có dòng | Không tạo quyết định hoặc người duyệt giả |
| Chưa có graph | nodes/edges chỉ có header | graph_ready=false, node_count/edge_count=null; loader không được nhập như một graph hoàn chỉnh |

Lệnh chạy ở thư mục v2:

```powershell
py -3.12 -m contract_v2.migrate --input ..\mxh_a1_pilot --output pilot_v2_may_toi
py -3.12 -m contract_v2.verify --root pilot_v2_may_toi
```

Output phải mới và nằm ngoài input. Nếu B đã có graph hoặc dữ liệu enrichment khác pilot A1, không chạy script này lên bộ dữ liệu đó. Script hiện hỗ trợ đúng A1 được bàn giao; cần adapter/migration phù hợp cho dữ liệu B, đặc biệt evidence và identity đã resolve. Không bỏ trường cũ rồi tự lấp người duyệt hoặc nguồn còn thiếu.

Để quay lại bản dữ liệu A1, dùng nguyên gói v1 hoặc bản legacy/raw và code v1. Đây là rollback định dạng metadata đã được bảo toàn. Nó không tự rollback một database Neo4j đang chạy; B3 phải áp dụng chiến lược dựng lại từ snapshot đã chọn.

Khi A2/B2 thu thêm bài bằng collector v1, cần chuyển exporter sang v2 hoặc xây adapter được kiểm tra. Không nhập trực tiếp record v1 vào consumer yêu cầu v2. Khi thay parser/normalizer/rule, tạo text/evidence mới, không sửa mất bản cũ.
