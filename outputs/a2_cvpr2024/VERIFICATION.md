# Xác minh bước tích hợp A2 offline

Ngày 07/11/2026. Nhánh `feat/a2-collector-v2`, HEAD `f323173` không đổi.
Repo root: `D:/UET_Projects/PTMXH/FinalTerm`.

Đã hoàn tất bước tích hợp/offline. **A2 tổng thể chưa hoàn thành**: có 30/350 Paper A, chưa triển khai OpenAlex và chưa thu thêm 320 bài.

## Môi trường và lệnh đã chạy

- Windows; CPython 3.12.14 của runtime Codex: 26 test thành công.
- CPython 3.12.10 qua launcher `py -3.12`: 26 test thành công; bootstrap, replay và verify thành công. Chi tiết môi trường ở `runtime.json`, log ở `tests.log`.
- Chỉ dùng thư viện chuẩn; không cài dependency, không đọc API key. `jsonschema` không có trong hai môi trường, nên chưa chạy đối chứng bằng validator Draft 2020-12 độc lập tại máy này.

```powershell
py -3.12 -B -X utf8 -m src.collect.bootstrap --input handoff/mxh_a1_pilot
py -3.12 -B -X utf8 -m src.collect --offline --config config/a_cvpr2024_pilot.json
py -3.12 -B -X utf8 -m src.collect.verify --config config/a_cvpr2024_pilot.json
py -3.12 -B -X utf8 -m unittest discover -s quality/checks -p "test_a2_*.py" -v
git diff --check
```

## Kết quả

| Kiểm tra | Kết quả |
| --- | --- |
| Hash gói A1 | 164 tệp trong SHA256SUMS, không lỗi |
| Hash gói v2 | 111 tệp trong SHA256SUMS, không lỗi |
| Schema chuẩn | 14 JSON giống nguyên byte bản bàn giao; xem `schema_checksums.json` |
| Metadata A | 30 Paper core CVPR 2024 main, 159 lượt authorship |
| Raw sources | 31 nguồn: 1 full listing có 2.715 ứng viên, 30 trang detail; hash nguồn và ID đều khớp |
| Text/provenance | 60 text versions, 259 field provenance records |
| 12 bảng v2 | 569 record hợp lệ theo subset schema hiện dùng và đối chiếu lại với raw |
| Đối chứng bản v2 đã bàn giao | Paper, registry, authorship và text versions của A khớp |
| Replay lần hai trong repo | 79 tệp (raw, processed, summary và `.gitkeep` raw) giữ nguyên hash; cùng snapshot ID |
| Các ca lỗi | Cache thiếu/hỏng, đường dẫn thoát vùng A, 403/429, hết retry, đầu ra đã sửa bị từ chối; resume không tải lại |
| Request mạng thực | 0; các test HTTP dùng mock, integration test chặn network |
| Tệp gốc | 293/294 nguyên byte; chỉ README được chủ động cập nhật; 278 tệp handoff ban đầu đều nguyên byte |
| Git | `git diff --check` qua; index rỗng, HEAD không đổi, chưa commit/push |

Snapshot: `snapshot:v2:b8ab3407e9bd5cab2b8359c30eef49df3da6f83fec7c299cc1b56b13498693ab`.

Code version là `a2-offline-integration-1.0.0`; parser giữ `cvf-html-1.0.0`; normalizer giữ `nfc-ws-1`; schema giữ `2.0.0`. Đây không phải tên commit đã tạo.

So với metadata v2 bàn giao của riêng A, export thêm 30 dòng provenance cho `track` từ listing main conference (229 → 259 dòng). Source record đổi đường dẫn raw theo vùng A; source ID/content hash/HTML gzip và Paper ID không đổi. Không có thay đổi schema.

## Sự cố đã xử lý và giới hạn

Lần chạy test đầu gặp `PermissionError` do ACL của `tempfile.TemporaryDirectory` trên Windows trong sandbox. Helper test hiện tạo thư mục duy nhất dưới `outputs/a2_cvpr2024` với quyền kế thừa và dọn đúng thư mục đó sau test. Thư mục probe trong repo đã được dọn; bộ test cuối không còn lỗi này.

Repo có `core.autocrlf=true`. `.gitattributes` chỉ áp dụng phạm vi A2, ngăn Git đổi bytes schema/processed A làm lệch manifest. Đã kiểm tra thuộc tính; các đường dẫn graph/ICCV của B không nhận quy tắc mới.

Không còn lỗi trong các kiểm tra offline đã chạy. Chưa kiểm chứng API CVF/OpenAlex thật, quota/retry OpenAlex, matching/identity/affiliation hoặc 350 Paper. Pilot adapter dừng nếu gặp DOI mới cần provenance; sẽ bổ sung ở bước collector. Dữ liệu hiện vẫn `openalex_status=not_collected`, identity unresolved, graph_ready=false; không có kết quả NLP/Neo4j hoặc phép đo độ chính xác graph.

Code test được chuyển vào `quality/checks`, dùng import `src.*`. Không chạy pipeline hoặc test bằng cách import trực tiếp code từ handoff. Kiểm tra gói gốc là checksum và đối chứng dữ liệu đọc-only; không tuyên bố đã chạy lại nguyên bộ kiểm tra graph/quality v1 của gói bàn giao.

Biên bản và phạm vi triển khai collector tiếp theo: `handoff/a/A2_HANDOFF.md`. Danh sách tệp thay đổi đầy đủ (gồm raw bị Git ignore): `changed_files.json`.
