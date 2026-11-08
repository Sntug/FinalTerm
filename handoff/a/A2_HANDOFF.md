# Bàn giao A2 — CVPR 2024

Tài liệu chuẩn về vận hành và bàn giao A2, cập nhật 08/11/2026. Nhánh chuẩn bị bàn giao: `feat/a2-cvpr350`. **350 Paper A đã thu/xuất đủ; graph_ready=false.** Không thực hiện đầy đủ A3, NLP A4 hoặc Neo4j B3, không kết luận pilot nhóm hoàn tất.

## Dữ liệu hiện hành

| Chỉ số | Số lượng |
| --- | --- |
| Paper hợp lệ, ID duy nhất, owner=A, main CVPR 2024 | 350/350 |
| Pilot giữ nguyên / thêm mới / loại hoặc chọn bù | 30 / 320 / 0 |
| OpenAlex matched / not_found / needs_review / not_collected | 328 / 0 / 22 / 0 |
| Abstract / DOI | 350/350 / 328/350 Paper |
| Affiliation có trong raw Work matched | 323/350 Paper |
| Affiliation đã xác minh gắn vào tác giả CVF | 0/350 Paper; 0/1.968 authorship |
| References đã đọc / không rỗng | 328/350 / 321/350 Paper |
| Nguồn / text versions / bảng / tổng records | 1.032 / 700 / 12 / 8.766 |

Snapshot: `snapshot:v2:f18c4b6c1e243abf26cccdfa520296599d2a5e2b96aa7da971cf8708ecc70ce8`. 7 Work có references rỗng theo OpenAlex; không suy rằng bài gốc không có tài liệu tham khảo. Xem [22 Work cần review](../../outputs/a2_cvpr2024/a2_350/WORK_REVIEW.md).

| Thành phần | Đường dẫn từ repo root |
| --- | --- |
| Config / registry input | `config/a_cvpr2024_350.json`, `config/a_cvpr2024_350_registry.csv` |
| Selection lock / bản sao bắt buộc | `config/a_cvpr2024_350_selection.json`, `data/processed/cvpr2024/a2_350/selection_lock.json` |
| Manifest export cho A3/B | `data/processed/cvpr2024/a2_350/snapshot_manifest.json` |
| Raw và metadata cache | `data/raw/cvpr2024/http/`, `data/raw/cvpr2024/openalex/` |
| Checkpoint local | `data/raw/cvpr2024/checkpoints/a2_350.json` |
| Báo cáo/bằng chứng | `outputs/a2_cvpr2024/a2_350/` |

Đọc 12 bảng bằng đường dẫn trong manifest, không giả định bảng nằm trực tiếp dưới `data/processed`. Raw paths cũng tính từ repo root. Export và selection đã khóa là bất biến; không sửa để vượt kiểm tra hash.

## Cách chạy

Python 3.12+ (đã kiểm tra 3.12.10), chỉ thư viện chuẩn; [requirements](../../config/requirements_a2.txt) không có package ngoài. Chạy tại thư mục gốc clone:

```powershell
py -3.12 -B -X utf8 -m src.collect.verify --manifest data/processed/cvpr2024/a2_350/snapshot_manifest.json
py -3.12 -B -X utf8 -m src.collect --config config/a_cvpr2024_350.json --offline
py -3.12 -B -X utf8 -m unittest discover -s quality/checks -p "test_a2_*.py" -v
```

Resume có mạng: dùng lệnh collector trên và bỏ `--offline`. Selection đã có; `py -3.12 -B -X utf8 -m src.collect.selection --config config/a_cvpr2024_350.json` chỉ kiểm tra/reuse lock, không tải detail. Chọn thêm theo SHA-256(seed + newline + canonical_url), seed 20261103, tie-break URL, giữ thứ tự 30 pilot. Không chỉ sửa target_count trong config pilot.

Key: ưu tiên `OPENALEX_API_KEY` môi trường không rỗng, rồi `.env` tại repo root (độc lập CWD; Python vẫn cần tìm được module). Không ghi key vào URL/log/cache; dùng Bearer header. Kiểm tra riêng một request: `py -3.12 -B -X utf8 -m src.collect.auth_check`; chỉ trả trạng thái đã lọc. `.env.example` chỉ chứa placeholder/default, không gửi `.env`.

Cache/resume kiểm tra hash; checkpoint mỗi bài, báo tiến độ mỗi 25 bài; 1 giây giữa request mỗi nguồn, timeout 30 giây, tối đa 2 retry. HTTP 429/Retry-After dài lưu gate/checkpoint, exit 2; tiếp tục sau retry_at. 401/403 không được coi là not_found. Không xóa gate, đổi key/host để né hạn mức; không chạy hai writer cùng config.

## Contract, ID và provenance

Schema thực thi: [config/contracts/v2](../../config/contracts/v2/data_contract.json), giữ nguyên 14 JSON từ bàn giao. Quy tắc đầy đủ: [DATA_CONTRACT](../mxh_contract_v2/docs/DATA_CONTRACT.md), [FIELD_INDEX](../mxh_contract_v2/docs/FIELD_INDEX.md); không tự sửa schema/cột.

- Paper ID CVF không đổi khi thêm DOI/Work; arXiv là liên kết phiên bản, không tạo Paper core khác. Main conference, title, ordered authors và năm được đối chiếu CVF. Thiếu DOI/affiliation/Work không loại Paper.
- Title tương tự chỉ tạo ứng viên. Chấp nhận Work sau đối chiếu title/byline và DOI hoặc venue/year hoặc liên kết phiên bản. Không union tác giả; không gán cơ quan hiện tại ngược về bài.
- Giữ raw bytes, fetched_at, source ID và content hash; field_provenance chỉ đúng nguồn/field/rule. Phân biệt hash raw với hash toàn trường text đã chuẩn hóa; giữ text_version_id và offset evidence theo contract.
- Giữ null/trạng thái thiếu theo schema, không tạo reviewer/merge giả. `referenced_works` khác `cited_by_count`; citation_count phải có nguồn/thời điểm. Chưa tạo graph hoặc phân giải Author.

## Kiểm tra và giới hạn

46 test đã qua; verifier kiểm schema, raw hash, khóa ngoại và membership. Offline/resume có 0 request, không nhân đôi và manifest nguyên byte; 30 bản ghi pilot giữ nguyên. Validator nội bộ bao phủ các ràng buộc v2 đang dùng, không tự nhận là validator Draft 2020-12 tổng quát. [Bằng chứng kiểm tra/thu thật](../../outputs/a2_cvpr2024/a2_350/A2_350_REPORT.md).

Lượt thu có 320 request CVF, 657 lần gọi OpenAlex cho 623 response mới; có 429 tạm thời đã retry thành công. Không còn source error/pending. Chưa ghi từng status trung gian nên không quy toàn bộ 34 lần gọi thêm cho 429. Lỗi khóa checkpoint Windows ở lượt offline đầu đã được sửa và test lại. Log lỗi và transport audit vẫn được giữ.

Còn review 22 Work, xác minh 1.968 authorship/affiliation ở A3 và đánh giá precision thủ công; các phần này không bị gán hoàn thành bởi kết quả A2 metadata.

## Bàn giao

Commit code/helper, config mẫu, schema, tests và fixture lịch sử, registry/locks/export, raw nguồn **cùng metadata cache**, báo cáo/kiểm tra cần thiết. Các raw CVPR được source_records của snapshot hiện hành/lịch sử tham chiếu đều nằm trong gói Git; clone gói đã commit có thể verify/replay offline mà không tải lại nguồn. Giữ local secrets, môi trường ảo, checkpoint/quota gate, file tạm và các log/bản kiểm kê dư thừa đã liệt kê cụ thể trong `.gitignore`.

A3 đọc manifest và hàng đợi review, không sửa snapshot A2. B dùng [collector.example.json](../../config/collector.example.json), tự cung cấp registry đúng owner/conference/year/target_count và đường dẫn ICCV riêng; khi mở rộng, pilot/seed/listing lock phải thuộc ICCV. Mẫu config không phải dữ liệu ICCV. Fixture ICCV đã qua, không xác nhận B đã chạy dữ liệu thật. Không thay đổi dữ liệu/chính sách raw ICCV của B.

## Lịch sử ngắn

- A1: pilot 30 CVPR + 30 ICCV CVF; v2 bổ sung provenance/text versions. Hai gói handoff gốc giữ nguyên để truy vết và làm fixture.
- A2 pilot: 30 Paper A, 27 Work matched, 3 needs_review; metadata snapshot được giữ nguyên.
- A2 350: thêm 320 theo ranking đã chốt; hoàn tất metadata theo số liệu trên. Người dùng cho phép A tiếp tục độc lập, không thay cho nghiệm thu pilot nhóm.
