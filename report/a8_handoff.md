# A8 — Tích hợp, kiểm thử và bàn giao

Đây là biên nhận tích hợp ứng viên, không thay manifest Contract v2 và không phải release/nộp bài cuối.

Snapshot: `snapshot:v2:ffcb00e173370c55b80299a182c81d72f6c461d38f944427c1cb33739e948757`; commit nền lúc chạy: `78de710a22bdb071456952f69266180b4c5dca9e`. Code/chỉnh sửa chưa commit được ghi bằng hash trong integration_manifest.json.

Kiểm tra offline bắt buộc qua: **True**. Data integration partial: **False**. Final: **False**.

## Trạng thái đã kiểm tra

| Hạng mục | Trạng thái | Phụ trách | Minh chứng/lệnh |
|---|---|---|---|
| collector_A | PASS | A | Executed; chi tiết trong validation_summary.json |
| clean_replay_A | PASS | A | Executed; chi tiết trong validation_summary.json |
| metadata_replay_A | PASS | A | Executed; chi tiết trong validation_summary.json |
| collector_B | PASS | B | Executed; chi tiết trong validation_summary.json |
| clean_replay_B | PASS | B | Executed; chi tiết trong validation_summary.json |
| nlp_A4_B5 | PASS | A/B | Executed; chi tiết trong validation_summary.json |
| graph_B3_B4_B5 | PASS | A/B | Executed; chi tiết trong validation_summary.json |
| graph_contract | PASS | A/B | Executed; chi tiết trong validation_summary.json |
| deterministic_replay | PASS | A/B | Executed; chi tiết trong validation_summary.json |
| B3_reader_offline | PASS | B | Executed; chi tiết trong validation_summary.json |
| baseline_B5_delta | PASS | A/B | Executed; chi tiết trong validation_summary.json |
| audit_automatic_and_forms | PASS | A/B | Executed; chi tiết trong validation_summary.json |
| audit_human | PENDING_B | A/B | Primary 0/100; cross 0/20; nodes 0/50; precision=None; chi tiết trong validation_summary.json |
| A7_refresh_and_reconcile | PASS | A/B | Executed; chi tiết trong validation_summary.json |
| neo4j_readonly_content | BLOCKED_ENV | B | Neo4j Python driver is not installed; no DB queries/writes executed; chi tiết trong validation_summary.json |
| neo4j_import_idempotence | BLOCKED_ENV | B | Set A8_NEO4J_TEST_URI/USER/PASSWORD for a separate empty test instance; .env is not used; chi tiết trong validation_summary.json |
| tests | PASS | A/B | Executed; chi tiết trong validation_summary.json |
| preservation | PASS | A/B | Executed; chi tiết trong validation_summary.json |

## Dữ liệu và giới hạn

- Paper core theo hội nghị: `{"CVPR2024":350,"ICCV2023":350}`; scope `{"core":700}`.
- 4182 node, 16979 cạnh; 8 nhãn và 10 loại quan hệ.
- Node: `{"Author":2950,"Country":42,"Dataset":14,"Institution":432,"Method":28,"Paper":700,"Task":14,"VenueEdition":2}`.
- Edge: `{"AFFILIATED_WITH":3237,"AUTHORED":3282,"BASED_IN":432,"CITES":97,"COAUTHORED_WITH":7771,"COLLABORATED_WITH":1140,"EVALUATED_ON":28,"PUBLISHED_IN":700,"STUDIES_TASK":97,"USES_METHOD":195}`.
- Tổng nhóm lấy từ ID/khóa trong snapshot hợp nhất; không cộng số Author/Institution của hai corpus.
- Dùng A5 CVPR + A3 ICCV; chạy lại NLP Task/Dataset/Method và exporter B vào thư mục a8 riêng. Không sửa schema, ID, dữ liệu B hoặc graph B5 cũ.
- A8 giữ source_records, provenance, alias/decision và review của A5; ambiguity giữ review/cách ly alias, không tự merge theo tên.
- Human audit là bước riêng. Phiếu cũ outputs/a6 giữ nguyên snapshot B5; phiếu ứng viên A8 ở outputs/a8/audit. Không chuyển nhãn chấm giữa snapshot hoặc tự chấm thay A/B.
- Kiểm tra tự động/hash/offset không chứng minh precision ngữ nghĩa >90%. Review risks không tự động là lỗi thật.

## Chờ B và việc A/B cần làm

| Task | Trạng thái | Thiếu/ảnh hưởng | Cần bổ sung và kiểm tra lại |
|---|---|---|---|
| B6 | PENDING_B | Chưa có chương trình/kết quả NetworkX và case study | B cung cấp module, lệnh chạy, bảng/hình gắn đúng snapshot A8; Chạy lệnh B cung cấp và đối chiếu snapshot_id/hash; file tồn tại chưa đủ PASS |
| B7 | PENDING_B | Chưa có phần báo cáo graph B7; audit/đọc chéo chưa hoàn tất | A/B chấm phiếu A8, phân xử lỗi; B bổ sung phần báo cáo graph; Chạy src.audit summarize với config/a8_audit.json, rồi chạy lại A8 |
| B8 | PENDING_B | Chưa có báo cáo nhóm cuối hoặc bằng chứng nộp bài | B hợp nhất báo cáo và cùng A chốt snapshot/Neo4j, links và phiên bản nộp; Review báo cáo nhóm và release/links thực tế; không tự tuyên bố đã nộp |

B2/B4/B5 có thể được ghi PASS chỉ qua checks tương ứng ở trên. B3 có reader/importer offline; chứng nhận live, idempotence và rollback chỉ có khi chạy trên DB thật đúng snapshot.

## Chạy lại trên Windows PowerShell

Từ FinalTerm, Python 3.12. Không cần tải lại 700 bài hoặc API key cho replay offline.

```powershell
py -3.12 -m venv .venv-a4
$a8Python = ".\.venv-a4\Scripts\python.exe"
& $a8Python -m pip install -r config/requirements_a7.txt
if (!(Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
& $a8Python -B -X utf8 -m src.integration.a8 run
# Chỉ đọc DB được .env trỏ tới, không import/xóa:
& $a8Python -B -X utf8 -m src.integration.a8 neo4j-check
```

`.env` chỉ chứa cấu hình cục bộ; không commit key/password. `.env.example` dùng port mẫu, cần đặt URI đúng instance B muốn đối chiếu. Driver Neo4j là tùy chọn: nếu chưa có, CLI ghi BLOCKED_ENV; cài driver theo môi trường B3 trước khi kiểm tra live.

Để thử import, dùng một instance Neo4j test mới, rỗng và tách biệt. Đặt A8_NEO4J_TEST_URI/USER/PASSWORD trong môi trường cục bộ rồi chạy `python -m src.integration.a8 test-import`. URI chỉ chấp nhận bolt localhost trên port riêng, từ chối 7687/17687, URI có credential và DB không rỗng. Lệnh không dùng .env, không tự tạo credential hay server; nếu thiếu môi trường thì BLOCKED_ENV. Helper gọi nguyên loader B ba lần (nhập, nhập lại, lỗi sau nodes để kiểm rollback), giữ dữ liệu test để kiểm tra và không ghi last_import của B. Tuyệt đối không chạy loader trực tiếp vào database chính trong bước thử này.

Lệnh neo4j-check/test-import đã có CLI và kiểm thử offline; phần live chưa được xác minh nếu bảng trạng thái không ghi PASS. Đối chiếu cả snapshot tag, content hash và counts theo label/type/core/conference; chỉ count trùng chưa đủ.

## Khi B bổ sung

1. Giữ snapshot cũ. Chọn input thật bằng bộ config A8; dùng output NLP/graph/audit mới nếu input/rule/seed thay đổi, cập nhật config A7 cùng snapshot.
2. Chạy lại A8; pipeline có sẵn từ chối ghi đè snapshot khác. Nếu B chỉ thêm báo cáo/analysis, bổ sung path/lệnh của B vào dependency trong config và kiểm chứng đầu ra; không đánh PASS do file tồn tại.
3. A/B chấm đúng phiếu ứng viên, chạy `python -m src.audit summarize --config config/a8_audit.json`, phân xử incorrect/unverifiable/bất đồng rồi chạy lại A8. Runner giữ phiếu đã điền, không gọi run để ghi đè.
4. B thử import trên instance test rỗng; sau đó nhóm tự chọn snapshot/DB chính để nạp. Chạy neo4j-check với .env đúng và A8 lần nữa để biên nhận phản ánh kết quả mới.
5. B6/B7/B8 đối chiếu snapshot ID/hash, hoàn thiện báo cáo nhóm và release/links. Chỉ chốt/nộp khi không còn FAIL và các điều kiện live/audit/báo cáo đã được người phụ trách xác nhận.

Biên nhận: outputs/a8/integration_manifest.json; chi tiết từng check và lệnh: outputs/a8/validation_summary.json; log tests: outputs/a8/*_tests.log. Báo cáo số liệu chuẩn vẫn là [A7](a7_data_preprocessing_nlp.md).
