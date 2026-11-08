Cập nhật cấu hình OpenAlex 08/11/2026: key nạp được; một request nhỏ trả HTTP 200. Ưu tiên biến môi trường không rỗng, fallback .env ở repo root; không phụ thuộc CWD, không thêm dependency. 42 test qua, snapshot pilot giữ nguyên. Đủ để bàn giao collector/config cho B chạy pilot; chưa nghiệm thu 350. Chi tiết: `outputs/a2_cvpr2024/pilot/B_READINESS.md`. Không đưa .env vào gói gửi B.

# A2 — cập nhật pilot ngày 08/11/2026

Nhánh vẫn `feat/a2-collector-v2`, chưa commit/push. Đã triển khai collector dùng chung và chạy đúng 30 Paper CVPR 2024 khóa từ A1. Kết quả: **30 hợp lệ; OpenAlex 27 matched, 0 not_found, 3 needs_review, 0 not_collected**. 159 authorship vẫn unresolved; affiliation chưa gắn vào tác giả CVF.

Export hiện hành: `data/processed/cvpr2024/pilot/snapshot_manifest.json`. Các bảng v2 được trỏ bằng đường dẫn tương đối repo root, trong `pilot/snapshots/<digest>/`. `graph_ready=false`. Verifier nhận `--manifest` độc lập. Schema v2 nguyên byte, raw CVF và export tích hợp cũ được giữ nguyên.

Config A: `config/a_cvpr2024_pilot.json` (target_count=30, registry_input và selection_file khóa). Mẫu dùng chung cho B: `config/collector.example.json`. Runtime không hard-code owner A/số 30. Chỉ fixture ICCV được chạy trong thư mục tạm; không ghi ICCV chính thức.

Báo cáo hiện hành và lệnh PowerShell đã kiểm tra: `outputs/a2_cvpr2024/pilot/PILOT_REPORT.md`. `summary.json`, `live_summary.json`, `matching.json`, `tests.log`, `replay_check.json` là minh chứng. 37 test qua; offline và online từ cache giữ nguyên manifest, không request mới.

Phần còn lại: review C2RV và hai Work có byline khác CVF (Do Vision and Language Encoders Represent the World Similarly?, ADFactory); resolve danh tính/affiliation theo nguồn; sau khi được yêu cầu mới mở 350. Chưa chạy 350, chưa làm NLP/Neo4j. Không đổi schema, không tạo merge hoặc người duyệt giả.

---

Phần dưới là biên bản lịch sử của bước tích hợp ngày 07/11/2026; trạng thái/lệnh collector hiện hành nằm ở phần cập nhật trên và README.

# A2 — bàn giao bước tích hợp offline

Ngày: 07/11/2026. Thành viên A. Repo: `D:/UET_Projects/PTMXH/FinalTerm`.
Nhánh sử dụng: `feat/a2-collector-v2`; HEAD lúc bắt đầu: `f323173`.

## Trạng thái Git và phạm vi

Đầu phiên, repo đã ở nhánh A phù hợp và có `?? handoff/`; các thư mục thực thi chỉ có `.gitkeep`. Nhánh `main` và remote-tracking `origin/main` tại chỗ cùng trỏ `f323173`. Không fetch/pull hoặc đổi nhánh vì tiếp tục nhánh A đang có; chưa xác nhận trạng thái mới nhất trên máy chủ. Không stage, commit, push, reset hoặc clean.

Đã đọc README nhóm, `Plan_FinalTerm.docx`, README/CODEX_HANDOFF của A1, DATA_CONTRACT/FIELD_INDEX/JSON contract v2 và hướng dẫn migration. Không tìm thấy `AGENTS.md` trong repo hoặc các thư mục cha liên quan. Code Neo4j/NLP của B chưa có trong checkout này.

## Phần đã tích hợp

- `src/collect/cvf.py`: parser/listing/seed ranking kế thừa A1; giữ `cvf-html-1.0.0`. Parser vẫn tạo quan sát CVF theo hình dạng v1 nội bộ; `export.py` chuyển thực sự sang v2, thêm text versions, authorship IDs và field provenance.
- `src/collect/cache.py`: cache CVF theo thư mục corpus, kiểm tra URL/hash, retry và resume; HTTP được mock khi test. CLI chỉ cho replay offline.
- `src/collect/bootstrap.py`: đọc dữ liệu A1, chép riêng snapshot A, không import code từ handoff. Giữ compressed HTML bytes, Paper/source IDs và thời điểm thu gốc.
- `src/collect/contract.py`: đọc schema chuẩn từ JSON, không tạo một schema khác bằng hằng Python. Bộ kiểm tra dùng subset ràng buộc hiện có; không tự nhận là validator Draft 2020-12 tổng quát.
- `src/collect/export.py`, `pilot.py`, `verify.py`, `__main__.py`, `common.py`: xuất 12 bảng, manifest, kiểm tra từ raw và chạy lại có kiểm soát. Tệp khác nội dung bị từ chối ghi đè.
- `src/clean/text.py`: helper nfc-ws-1, text/evidence ID v2 từ gói contract; không tạo global Author ID theo tên.
- `quality/checks/test_a2_*.py`: các kiểm tra phù hợp từ A1/v2 đã chuyển import sang repo; thêm kiểm tra cách ly dữ liệu A, retry, resume và bảo toàn tệp đã tồn tại.

Schema chuẩn duy nhất cho code repo: **`config/contracts/v2/data_contract.json`**, các `*.schema.json` cùng thư mục. Cả 14 JSON giống nguyên byte với `handoff/mxh_contract_v2/schemas/`; `data_contract_v1_archive.json` chỉ để đối chiếu lịch sử. Bản bàn giao gốc không bị sửa.

Repo đang có `core.autocrlf=true`. `.gitattributes` mới chỉ giới hạn ở đường dẫn A2, giữ nguyên bytes schema và processed A để checkout không làm hỏng hash manifest. Không đặt quy tắc mới lên code/dữ liệu B.

Config A là `config/a_cvpr2024_pilot.json` và `config/a_cvpr2024_selection.json`. Seed 20261103, giữ đúng 30 Paper/source IDs và thứ tự đã khóa. `target_count=350` chưa phải số đã thu. `pilot_count` khác 30 bị CLI bước này từ chối.

## Dữ liệu đã kiểm tra

| Nội dung | Kết quả |
| --- | ---: |
| Paper core CVPR 2024 | 30 / mục tiêu 350 |
| Lượt authorship | 159, tất cả unresolved |
| Source records / HTML snapshots | 31: 1 listing + 30 detail |
| Text versions | 60: title + abstract |
| Field provenance | 259 |
| Bảng v2 / tổng record | 12 / 569 |
| Request mạng thực | 0 |

Metadata Paper, registry, authorship và text versions của A khớp dữ liệu v2 bàn giao. Source records giữ ID/hash nhưng đổi `raw_path` vào `data/raw/cvpr2024/http/`. Export bổ sung 30 dòng provenance cho `track`, chứng minh bằng listing main conference; đây là thêm dữ liệu theo schema v2 hiện có, không sửa schema. Tổng provenance A vì vậy tăng từ 229 lên 259.

Raw chỉ ghi trong `data/raw/cvpr2024/`; processed chỉ ghi trong `data/processed/cvpr2024/`. Không tạo/ghi registry chung, không thay đổi thư mục ICCV. Bảng graph, alias, merge log, needs review rỗng trong snapshot này; `graph_ready=false` và số nút/cạnh là null. Không suy affiliation/citation/references còn thiếu thành 0, `[]` hoặc `Unknown`.

## Chạy lại

Tại repo root, Python 3.12+ và thư viện chuẩn:

```powershell
py -3.12 -B -X utf8 -m src.collect.bootstrap --input handoff/mxh_a1_pilot --config config/a_cvpr2024_pilot.json
py -3.12 -B -X utf8 -m src.collect --offline --config config/a_cvpr2024_pilot.json
py -3.12 -B -X utf8 -m src.collect.verify --config config/a_cvpr2024_pilot.json
py -3.12 -B -X utf8 -m unittest discover -s quality/checks -p "test_a2_*.py" -v
```

Bootstrap chỉ cần khi chưa có cache, có thể gọi lại khi nội dung giống nhau. Replay/verify không phụ thuộc handoff sau bootstrap. Gói handoff gốc vẫn cần khi chạy các test đối chứng. Raw cache vẫn bị Git ignore như ban đầu: máy thứ hai cần cùng gói A1 hoặc bản sao `data/raw/cvpr2024/`; không chỉ clone code rồi coi là đã có snapshot.

Kết quả chạy thật và giới hạn ở `outputs/a2_cvpr2024/VERIFICATION.md`, `offline_summary.json`, `tests.log`, `preservation_check.json`. `changed_files.json` liệt kê toàn bộ tệp mới/sửa, kể cả raw đang bị ignore. `integration_baseline.json` ghi hash các tệp trước tích hợp.

## Phần A2 còn lại và phạm vi dự kiến

A2 tổng thể **chưa hoàn thành**. Chưa triển khai collector OpenAlex, chưa mở manifest lên 350, chưa thu hàng loạt và chưa thử API thật. Thiếu 320 bài A so với mục tiêu. Ghép định danh, affiliation, references, DOI provenance ngoài pilot và kiểm tra trên máy B vẫn phải làm.

| Phạm vi tệp dự kiến | Công việc tiếp theo |
| --- | --- |
| `src/collect/cache.py`, `cvf.py`; thêm `openalex.py`, `selection.py` | Dùng chung CVF/OpenAlex, cache JSON, timeout/retry/quota theo tài liệu chính thức, che API key, checkpoint/resume và chọn 350 giữ 30 cũ |
| `src/collect/__main__.py`, `pilot.py`, `export.py`, `verify.py`, `common.py` | CLI collector, kiểm tra Paper hợp lệ, manifest lô, xuất v2 và nguồn theo trường; phân biệt manifest ứng viên với bài đã xác minh |
| `src/clean/text.py` hoặc helper nhỏ trong `src/clean/` | Chỉ chuẩn hóa/phục vụ matching cần thiết; không merge Author theo tên hoặc tự nhận affiliation đã đúng |
| `config/a_cvpr2024_*.json` | Config 350, khóa thêm 320 ID theo seed; giữ 30 đã chốt, ghi rõ chọn bù bài không hợp lệ |
| `quality/checks/test_a2_*.py` | Mock OpenAlex, retry/429/quota, gián đoạn và resume, secret redaction, ứng viên mơ hồ, 350 ID duy nhất, source/evidence hợp lệ |
| `data/raw/cvpr2024/`, `data/processed/cvpr2024/` | Raw CVF/OpenAlex, source/selection/snapshot manifests và metadata A đã xác minh |
| `outputs/a2_cvpr2024/`, `handoff/a/A2_HANDOFF.md`, `README.md` | Báo cáo độ phủ/lỗi/giới hạn và lệnh chạy collector thật |

Schema `config/contracts/v2/` giữ nguyên; nếu cần đổi phải nêu migration/version và phối hợp với B. Không dự kiến sửa `src/graph`, `src/nlp`, `src/analysis`, `queries`, `report` hoặc dữ liệu ICCV trong bước collector của A. Việc hỗ trợ B dùng module chung không đồng nghĩa ghi lại dữ liệu B.
