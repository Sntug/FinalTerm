# Đề tài 30 · Mạng tác giả và tổ chức nghiên cứu thị giác máy tính

Dự án chung: A phụ trách 350 Paper CVPR 2024, B phụ trách 350 Paper ICCV 2023, chỉ main conference. Mục tiêu nhóm: graph Neo4j gồm 8 loại nút, 10 loại quan hệ có bằng chứng; ít nhất 2.000 nút và 5.000 cạnh duy nhất.

**Đọc [bàn giao A2](handoff/a/A2_HANDOFF.md)** để chạy collector, đọc snapshot và tiếp tục A3/B. A2 đã có 350 Paper A; đây là metadata (`graph_ready=false`), không phải nghiệm thu NLP/Neo4j hay pilot toàn nhóm.

**A3:** [bàn giao làm sạch và phân giải thực thể](handoff/a/A3_HANDOFF.md). Chạy offline bằng `py -3.12 -B -X utf8 -m src.clean --config config/a_cvpr2024_a3.json`; giữ 350 Paper, xuất authorships, alias/decision/review theo contract v2. Manifest A3: `data/processed/cvpr2024/a3_350/snapshot_manifest.json`.

| Phạm vi | Đường dẫn |
| --- | --- |
| Collector chung và helper | `src/collect/`, `src/clean/` |
| Schema chuẩn v2, config | `config/contracts/v2/`, `config/` |
| NLP Task/Dataset (A), Method (B) | `src/nlp/` |
| Neo4j, constraints, Cypher (B) | `src/graph/`, `queries/` |
| NetworkX, phân tích và kết quả (B) | `src/analysis/`, `outputs/` |
| Raw theo hội nghị | `data/raw/cvpr2024/`, `data/raw/iccv2023/` |
| Export A hiện hành | `data/processed/cvpr2024/a2_350/snapshot_manifest.json` |
| Registry chung dự kiến / kiểm tra / báo cáo nhóm | `data/paper_registry.csv`, `quality/`, `report/` |

Raw CVPR cần tái lập được đưa vào Git cùng metadata cache; checkpoint/quota gate giữ local. Chính sách và dữ liệu ICCV của B không thay đổi. `.env.example` là mẫu; mỗi người tự tạo `.env`, điền key/Neo4j cục bộ và không commit secrets.

Quy trình, phân công và điều kiện pilot nhóm vẫn theo [plan](handoff/Plan_FinalTerm.docx): 30 A + 30 B qua raw → clean/NLP → Neo4j, kiểm tra ID/coverage và số nút/cạnh. Việc A tiếp tục A2 độc lập theo yêu cầu không chứng minh những điều kiện nhóm đã hoàn tất.

Quy tắc dữ liệu: [DATA_CONTRACT v2](handoff/mxh_contract_v2/docs/DATA_CONTRACT.md), [FIELD_INDEX](handoff/mxh_contract_v2/docs/FIELD_INDEX.md). Hai gói `handoff/mxh_a1_pilot/` và `handoff/mxh_contract_v2/` được giữ nguyên làm dữ liệu lịch sử/fixture; không dùng hướng dẫn CLI cũ của chúng thay hướng dẫn A2 hiện hành.

## A4 — Task/Dataset, Contract v2

A4 dùng spaCy [PhraseMatcher](https://spacy.io/api/phrasematcher), [Matcher](https://spacy.io/api/matcher) và [Sentencizer](https://spacy.io/api/sentencizer), chạy CPU/offline, không gọi LLM/API. Từ điển khởi tạo có 15 Task và 30 Dataset; chỉ xuất node có cạnh được chấp nhận. Không triển khai `USES_METHOD` của B5.

| Mã / cấu hình | Chức năng |
| --- | --- |
| `config/a4_dictionary.json` | ID `task:<slug>` / `dataset:<slug>`, tên, alias, phiên bản và quy tắc mơ hồ; giữ định dạng ID đã quy định ở contract v1 và kế thừa trong v2 |
| `src/nlp/rules.py` | So khớp alias dài nhất và kiểm tra chủ thể/ngữ cảnh theo câu; rule ID ổn định `a4-task-title`, `a4-task-current`, `a4-dataset-evaluate`, `a4-dataset-experiments` |
| `src/nlp/pipeline.py`, `validation.py`, `verify.py` | Đọc manifest A3, kiểm tra schema/hash/raw/binding, tạo bảng trung gian và replay xác định |
| `src/nlp/adapter.py` | Cung cấp bảng cho exporter B, kiểm tra cùng snapshot đầu vào, giữ metadata/evidence và hàng đợi review |
| `config/a4_nlp_700.json`, `a4_graph_700.json` | Đường dẫn CVPR + ICCV và hai thư mục đầu ra riêng |
| `quality/checks/test_a4_nlp.py`, `quality/fixtures/a4_{dev,eval}.json` | Test rule, offset, lỗi dữ liệu, dedupe, replay và tích hợp B3/B4; 50 câu phát triển, 40 câu đánh giá riêng |

Từ thư mục `FinalTerm`, Windows PowerShell:

```powershell
# Cài một lần; sau đó các lệnh xử lý/verify chạy offline.
py -3.12 -m venv .venv-a4
.\.venv-a4\Scripts\python.exe -m pip install -r config/requirements_a4.txt
$a4Python = ".\.venv-a4\Scripts\python.exe"

& $a4Python -B -X utf8 -m src.nlp --config config/a4_nlp_700.json
& $a4Python -B -X utf8 -m src.graph.export_graph --config config/a4_graph_700.json
& $a4Python -B -X utf8 -m src.nlp.verify --config config/a4_nlp_700.json --graph-manifest data/processed/mxh_cv_700/graph_a4/snapshot_manifest.json

& $a4Python -B -X utf8 -m unittest discover -s quality/checks -p 'test_*.py' -v
& $a4Python -B -X utf8 -W ignore -m unittest discover -s src/graph -p 'test_*.py' -v
& $a4Python -B -X utf8 -m src.clean.verify --config config/a_cvpr2024_a3.json
& $a4Python -B -X utf8 -m src.clean.verify --config config/b_iccv2023_a3.json
```

Config giao kèm khóa `model="blank"` để tái lập bằng tokenizer tiếng Anh của spaCy 3.8.18. Có thể dùng `en_core_web_sm` đã cài hoặc `auto` (chọn model nếu có, fallback blank); đều dùng cùng sentencizer và không tự tải model. Đổi model/từ điển/rule/input phải dùng thư mục output mới và cập nhật config exporter: pipeline từ chối ghi đè snapshot khác. Muốn chạy riêng một corpus, dùng config riêng chỉ chứa manifest A3 tương ứng trong `input_manifests`.

Đầu vào là manifest A3 của mỗi corpus, tham chiếu papers/registry/source/text/provenance từ snapshot A2/B2 gốc. Đầu ra trung gian ở `data/processed/mxh_cv_700/a4/`: `nodes.csv`, `edges.csv`, `evidence.jsonl`, `needs_review.csv`, `summary.json`, `snapshot_manifest.json`. Manifest này có `graph_ready=false`, `node_count=edge_count=null` vì thiếu các node Paper và graph chung; số liệu NLP nằm trong summary. Không đưa trực tiếp thư mục này cho loader.

Exporter B nhận khóa tùy chọn `nlp_manifest` như `config/a4_graph_700.json`, replay A4 và hợp nhất đủ 12 bảng contract vào `data/processed/mxh_cv_700/graph_a4/`. Adapter gọi **nguyên bản** `contract_v2.verify.verify` trong thư mục kiểm tra tạm, với đúng bảng và raw nguồn; chỉ công bố manifest `graph_ready=true` khi qua kiểm tra. Có thể dùng loader B với thư mục `graph_a4` sau khi nhóm quyết định nạp DB. Lệnh exporter cũ không có `nlp_manifest` giữ giao diện/hành vi B3/B4; graph B ở `data/processed/mxh_cv_700/graph/` không bị ghi đè. Không sửa loader, schema hoặc gói contract lịch sử.

Evidence lấy nguyên câu trong `text_versions.normalized_text`; `start_char:end_char` là Unicode code point, end loại trừ. ID evidence dùng trực tiếp `contract_v2.text.evidence_id`, cạnh dùng `identifier("edge", src, type, dst)`. Mỗi `(src,type,dst)` có một cạnh, nhiều câu thì hợp `evidence_ids`. Section title/abstract được truy qua `papers.*_text_version_id` và `field_path`; schema không có cột `section` riêng. Evidence `a4-review` chỉ phục vụ review, không gắn vào cạnh accepted. Text thiếu/sai phiên bản, sai hash, nguồn khác Paper hoặc provenance đang tranh chấp không tạo cạnh cho trường đó.

**Kết quả kiểm tra ngày 09/11/2026:**

| Chỉ tiêu | Kết quả |
| --- | ---: |
| Paper / trường văn bản xử lý | 700/700 / 1.400/1.400 |
| Task / Dataset có cạnh | 14/15 / 14/30 mục từ điển |
| STUDIES_TASK / EVALUATED_ON | 97 / 28 |
| CVPR: Task / Dataset edges | 31 / 9 |
| ICCV: Task / Dataset edges | 66 / 19 |
| Evidence NLP hợp lệ | 498; trong đó 135 evidence hỗ trợ cạnh accepted |
| Hồ sơ loại / cần review | 194 / 237, đã dedupe theo Paper/trường/entity/câu/lý do |
| Graph hợp nhất | 4.154 node / 16.784 cạnh |
| Node / cạnh B được giữ nguyên nội dung | 4.126/4.126 / 16.659/16.659 |
| Contract toàn graph | 12 bảng, 75.832 record, 2.083 raw nguồn, 1.400 text version |
| Test | 90 test quality qua; 10 test B qua, 3 test Neo4j live skip |
| Replay | 19/19 file A4 + graph giống bytes khi chạy lại |

Minh chứng: [verification](outputs/a4_700/verification.json), [integration + corpus counts](outputs/a4_700/integration.json), [quality tests](outputs/a4_700/unit_tests.log), [B regression](outputs/a4_700/b_regression_tests.log). Hai đầu vào A3 cũng qua verifier/replay riêng trong `outputs/a4_700/input_*_verification.json`. Bộ câu tổng hợp đánh giá khớp 40/40, không phải phép đo precision trên toàn corpus. Đã kiểm tra reader offline của loader; không kết nối hoặc thay đổi database Neo4j.

Giới hạn: chỉ title/abstract, không đọc PDF/full text hay suy luận xuyên câu. Ưu tiên độ chắc chắn; câu vừa pretrain/vừa evaluate, phủ định, baseline, nghiên cứu trước, giả định hoặc vai trò lẫn lộn có thể bị bỏ dù chứa một mệnh đề hợp lệ. Tên chung không suy phiên bản; tên ghép chưa có trong từ điển (`COCO-Stuff`, `Tiny-ImageNet`, `ImageNet-C`, v.v.) vào review. Vì vậy coverage/recall còn hạn chế; 237 hồ sơ mở cần người đọc nguồn, không được tính thành cạnh hợp lệ.

Khi gộp hai corpus, có thêm **3 alias ORCID xung đột** ngoài A4: alias đó không có mapping hiệu lực trong graph mới, cả hai Author ID và quyết định nguồn vẫn được giữ; `needs_review.csv` ghi các ứng viên. Các quyết định chỉ tạo alias nhưng không được chọn không nằm trong `applied_decision_ids` của snapshot hợp nhất. Không tự merge/split hay sửa authorships/cạnh B. Nếu một quyết định alias xung đột còn sửa danh tính khác, adapter dừng để review. `.gitattributes` giữ nguyên bytes các snapshot ICCV và đầu ra A4 khi checkout trên Windows; không đổi raw, nội dung nguồn hay manifest đã có.

A4 đạt kiểm tra kỹ thuật offline về rule, Contract v2, offset, tích hợp và idempotency; review ngữ nghĩa dữ liệu thực tế và nghiệm thu Neo4j/toàn nhóm vẫn là bước riêng. Nhánh `feature/a4-nlp-task-dataset` được tạo từ `main`/`origin/main` tại `ba1ad72` (đã có A3, B3/B4); không có conflict Git, không commit/push/merge.

## Neo4j pilot trên môi trường macOS của B

Phần dưới ghi lại môi trường lần chạy B; không mô tả máy Windows chạy A4.

Đã thử Neo4j Community 2026.10.1 từ bản server độc lập chính thức thay cho Neo4j Desktop trong kế hoạch, cùng Java 21.0.4 và Python driver 5.28.8. Bản server và dữ liệu nằm trong `.neo4j-pilot/` (không theo dõi bằng Git); mật khẩu ở `.env` cục bộ. Server chỉ nghe trên `127.0.0.1`, Bolt `17687` và HTTP `17474`. Usage reporting, Fleet Manager và fleet discovery đã được tắt trong cấu hình. Lần khởi động đầu tiên dùng mặc định nên có thể đã gửi thống kê ẩn danh và phát discovery trên mạng nội bộ.

Trong Terminal, từ thư mục `FinalTerm`, tạo lại liên kết nếu `/private/tmp` đã bị xóa, rồi khởi động:

```sh
if [ ! -e /private/tmp/finalterm-neo4j-pilot ] && [ ! -L /private/tmp/finalterm-neo4j-pilot ]; then
  ln -s "$PWD/.neo4j-pilot" /private/tmp/finalterm-neo4j-pilot
fi
if [ "$(readlink /private/tmp/finalterm-neo4j-pilot)" = "$PWD/.neo4j-pilot" ]; then
  export NEO4J_HOME=/private/tmp/finalterm-neo4j-pilot
  export JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home
  "$NEO4J_HOME/bin/neo4j" start
else
  echo 'Đường dẫn tạm đã được sử dụng; kiểm tra trước khi khởi động.'
fi
```

Liên kết ASCII cần thiết vì launcher gặp lỗi với đường dẫn Unicode của thư mục này. Không thay thế liên kết nếu đường dẫn đó đã được dùng cho mục đích khác. Mở Neo4j Browser tại <http://127.0.0.1:17474>, kết nối `bolt://127.0.0.1:17687` bằng user `neo4j` và mật khẩu trong `.env`. Để dừng từ cùng Terminal: `"$NEO4J_HOME/bin/neo4j" stop`.

Hướng dẫn nạp và kiểm tra pilot B: [src/graph/B_PILOT.md](src/graph/B_PILOT.md). Thư mục server, cơ sở dữ liệu và `.env` chỉ tồn tại trên máy này; không có trong Git. Trong môi trường Codex có sandbox, tiến trình có thể bị dừng khi lệnh kết thúc; chạy lệnh trên trong Terminal thông thường để giữ server hoạt động.
