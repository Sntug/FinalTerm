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

A4 đạt kiểm tra kỹ thuật offline về rule, Contract v2, offset, tích hợp và idempotency; review ngữ nghĩa dữ liệu thực tế và nghiệm thu Neo4j/toàn nhóm vẫn là bước riêng. A4 đã merge qua PR #6; commit merge trên main là `beea14c`.

## A5 — Đối chiếu metadata và nguồn

A5 kiểm tra lại metadata CVF/OpenAlex từ raw/cache, rà định danh Paper, Author và Institution, đối chiếu preprint/DOI có chọn lọc. Không thêm Paper core hoặc tự gộp người/tổ chức theo tên. Mã ở `src/metadata/`: `sources.py` giữ cache/receipt cho nguồn bổ sung; `audit.py` tạo comparison/evidence/review và utility điền DOI có kiểm soát; `pipeline.py` xuất snapshot; `verify.py` kiểm tra schema, nguồn và replay. Các utility chuẩn hóa ID, parser CVF, Work assessment, kiểm tra identity và serialization của A2/A3 được tái sử dụng. Không sửa collector/cleaner, A4, exporter hoặc loader B.

Chạy từ `FinalTerm` trong Windows PowerShell, Python 3.12. A5 chỉ dùng thư viện chuẩn; môi trường `.venv-a4` được dùng để chạy cả regression spaCy:

```powershell
$a5Python = ".\.venv-a4\Scripts\python.exe"
# Tùy chọn: chỉ tra kế hoạch giới hạn, ưu tiên cache/receipt đã có.
& $a5Python -B -X utf8 -m src.metadata --config config/a_cvpr2024_a5.json --fetch-only
# Xuất và kiểm tra hoàn toàn offline từ raw/cache.
& $a5Python -B -X utf8 -m src.metadata --config config/a_cvpr2024_a5.json
& $a5Python -B -X utf8 -m src.metadata.verify --config config/a_cvpr2024_a5.json
& $a5Python -B -X utf8 -m unittest discover -s quality/checks -p 'test_*.py' -v
& $a5Python -B -X utf8 -W ignore -m unittest discover -s src/graph -p 'test_*.py' -v
```

`config/a_cvpr2024_a5.json` đọc manifest A3 CVPR, khóa 350 Paper. Kế hoạch chọn tối đa 8 Paper thiếu Work/DOI nhưng có link arXiv trực tiếp từ CVF và 2 ứng viên DOI duy nhất có title tương ứng trong cache OpenAlex. Không tải lại 328 Work đã ghép, không tải PDF. arXiv đọc HTML citation metadata (giữ phiên bản URL nếu CVF chỉ rõ); [Crossref REST](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) đọc bản ghi DOI trực tiếp. Cache mới ở `data/raw/cvpr2024/a5/`, giữ nguyên bytes phản hồi, hash, URL và thời gian UTC. Tái sử dụng transport không redirect, Retry-After, backoff và publish của A2; không có API key hard-code. Receipt lỗi giữ trạng thái unavailable, không sinh source record thành công. Offline cache miss là unverified. Không tự retry lại receipt đã lưu; muốn kiểm tra nguồn ở thời điểm mới, dùng cache/output mới và tôn trọng checkpoint backoff của nguồn.

Đầu ra `data/processed/cvpr2024/a5_350/`:

| Tệp | Nội dung |
| --- | --- |
| 12 bảng Contract v2, `snapshot_manifest.json` | Bản kiểm chứng riêng, gồm source/evidence bổ sung, giữ dữ liệu A2/A3 gốc; `graph_ready=false`, số node/edge trong manifest là null |
| `metadata_comparison.csv` | Bảng phân tích riêng, không đổi schema chung: Paper/entity/field, giá trị hiện tại/quan sát dạng JSON, nguồn, evidence, kết quả, lý do; lọc `conflict`/`version_difference`/`unresolved` để review |
| `lookup_results.json`, `summary.json` | Receipt nguồn và số liệu có phân biệt matched, missing, unverified, unresolved, conflict, version_difference, unavailable |
| `graph_impact.json` | Paper/trường bị thay đổi, nhu cầu dựng lại graph và kiểm chứng binding A4 |
| `paper_snapshots/current/` | Paper/registry và manifest tương ứng để B dùng trực tiếp giao diện exporter hiện tại |

Trạng thái kiểm chứng nằm trong comparison và evidence/review theo FK, không thêm cột tùy ý vào `source_records`. `matched` là nhất quán với nguồn nêu trong dòng; định dạng ID hợp lệ không đồng nghĩa danh tính đã xác minh. Bằng chứng metadata không có offset NLP. Mọi cập nhật DOI phải có title, đầy đủ byline theo thứ tự, venue/year bản conference và DOI registry phù hợp; cập nhật đồng bộ Paper/registry/provenance/alias và decision chứa before/after. DOI trùng giữa hai Paper khóa, title gần giống, ORCID/ROR mâu thuẫn hoặc Institution chưa rõ đều cần review. Không lấy affiliation từ hồ sơ tác giả hiện tại; không union byline conference và preprint. Review A3 được giữ, không đánh resolved tự động chỉ vì thấy nguồn khác.

HTML arXiv có thể chỉ ghi ID không có hậu tố `vN`; khi đó `source_version=null`. Raw/hash/captured_at vẫn xác định đúng phản hồi đã đối chiếu, nhưng không được diễn giải thành đã biết số revision cụ thể.

**Kết quả thực tế 10/11/2026:**

| Chỉ tiêu | Kết quả |
| --- | ---: |
| Paper / lượt authorship đã rà | 350/350 / 1.968/1.968 |
| DOI / OpenAlex được đối chiếu lại từ Work cache | 328/350 / 328/350 |
| Liên kết arXiv có định dạng hợp lệ từ CVF | 210/350; không coi là đã đọc toàn bộ preprint |
| Nguồn bổ sung / request mới | 10: 8 trang arXiv + 2 Crossref; 10 request, không lỗi truy cập |
| Preprint đối chiếu title/byline | 5/8 khớp; 3/8 khác biệt cần review; 202 link còn lại chưa tra nội dung |
| Source records | 1.032 → 1.042, không xóa nguồn cũ |
| Dòng comparison | 9.591: 7.752 matched, 295 unverified, 640 missing, 899 unresolved, 3 version_difference, 2 conflict |
| Canonical Paper/Author/Institution/affiliation tự sửa | 0 / 0 / 0 / 0; chưa đủ chứng cứ để sửa an toàn |
| Còn thiếu Author ID / Institution ID | 340/1.968 / 466/1.968 lượt; 469 dòng affiliation thiếu ID do multi-affiliation |
| Review đang mở | 1.389 hồ sơ: giữ 485 cũ, thêm 904; không phải 1.389 Paper/người duy nhất |
| Kiểm tra tương thích B trong bộ nhớ | 4.126 node giữ nguyên, 16.659 cặp cạnh/weight được bảo toàn; giữ evidence cũ, không dangling reference |
| Contract / replay | 12 bảng, 37.978 record, 1.042 raw nguồn, 700 text version; 20/20 file A5 giống bytes khi chạy lại |

Hai conflict là byline Crossref của ConsistDreamer và VP3D khác CVF (dấu tên/chính tả). Ba preprint khác byline gồm Do Vision and Language Encoders… (thứ tự tác giả), Text2Loc và State Space Models for Event Cameras (dấu tên). Giữ nguyên tên/thứ tự tác giả CVF, DOI còn thiếu và các affiliation chưa resolve; các quan sát nguồn bổ sung vẫn sẵn cho người review. Không dùng Scholar hàng loạt; chưa tra Scholar/PubMed vì chưa có trường hợp mà nguồn đó là bằng chứng quyết định cho đợt tra giới hạn này. Các bài y sinh chưa resolve vẫn cần tra chọn lọc nếu tiếp tục review, không được coi đã xác minh PubMed.

Minh chứng ở [verification](outputs/a5_cvpr2024/verification.json), [integration](outputs/a5_cvpr2024/integration.json), [tests](outputs/a5_cvpr2024/tests.log), [B regression](outputs/a5_cvpr2024/b_regression.log) và [fetch receipts](outputs/a5_cvpr2024/fetch.json). 110 test quality qua (20 A5 và 90 regression A2/A3/A4); 10 test B qua, 3 test Neo4j live skip. Các test dùng fixture offline cho DOI đúng/sai, near-title, byline/preprint và revision, trùng tên khác ID, thay đổi nơi làm việc theo Paper/năm, Institution alias/ROR, cache/429, provenance, replay và khả năng dùng trong exporter.

B nhận `snapshot_manifest.json` cùng 12 bảng và raw/receipt A5. Với config exporter B3/B4, thay input CVPR bằng `{"name":"CVPR2024", "snapshots_dir":"data/processed/cvpr2024/a5_350/paper_snapshots", "a3_dir":"data/processed/cvpr2024/a5_350"}`; input ICCV giữ như cũ. Utility `src.metadata.pipeline.exporter_input(config)` tạo đúng cấu hình này. A5 chỉ kiểm tra `build()` trong bộ nhớ, không xuất graph cuối/không nạp DB. Nếu chọn tích hợp cả NLP, phải replay/rebind A4 bằng manifest A5 và output mới vì adapter A4 khóa source snapshot; văn bản/ID nguồn NLP hiện không thay đổi và snapshot A4 cũ được giữ nguyên.

A5 đã có đầu ra kiểm chứng offline và pipeline tương thích; chưa phải toàn bộ ID/affiliation đã resolve hoặc mọi DOI/arXiv đều được nguồn độc lập xác nhận. Nhánh `feature/a5-metadata-verification` tạo từ `beea14c` (đã có A4), sau đó đồng bộ main `84f3a90` chứa B5 bằng fast-forward, không conflict. Sau đồng bộ, 114 test quality và verifier A5/B5 qua; `.gitattributes` bảo toàn bytes snapshot B5 trên Windows. Phần A5 được bàn giao trên nhánh để review trước khi merge.

## A6 — Review dữ liệu và quality audit

A5 đã merge qua PR #8; A6 bắt đầu từ main `e442724` đã có cả A5/B5. Các thay đổi `.gitignore` riêng của người dùng được giữ nguyên, không stash; không có conflict Git.

A6 dùng `config/a6_audit.json`, đọc A5 CVPR + A3 ICCV và graph B5 đúng snapshot. Mã kiểm tra nằm trong `src/audit/checks.py`, điều phối/validator trong `pipeline.py`, lấy mẫu và tổng hợp phiếu trong `sampling.py`; tests: `quality/checks/test_a6_audit.py`. Tái sử dụng validator/replay A3/A5/B5 và Contract v2 gốc. Các cạnh cộng tác được kiểm tra độc lập bằng tập Paper/tác giả/affiliation; CITES đối chiếu referenced works, evidence NLP dùng validator offset Unicode chuẩn. Không thay schema, pipeline hoặc dữ liệu B.

Từ `FinalTerm`, Windows PowerShell:

```powershell
$a6Python = ".\.venv-a4\Scripts\python.exe"
& $a6Python -B -X utf8 -m src.audit run --config config/a6_audit.json
& $a6Python -B -X utf8 -m unittest discover -s quality/checks -p 'test_*.py' -v
# Sau khi A/B điền phiếu:
& $a6Python -B -X utf8 -m src.audit summarize --config config/a6_audit.json
```

**Báo cáo A6 chuẩn:** [a6_review_summary.md](outputs/a6/a6_review_summary.md). Các file cùng thư mục gồm `a6_review_issues.csv`, `a6_edge_audit_sample.csv`, `a6_node_audit_sample.csv`, báo cáo máy và manifest ràng buộc snapshot. `run` chạy offline; chỉ thử truy vấn MATCH đếm Neo4j khi có driver/kết nối, nếu không ghi `not_run`/`blocked`, không coi là đã qua Neo4j.

Mẫu dùng seed `20261103` của collector: 100 cạnh khác nhau (10/loại), A/B mỗi người 50 primary và 10 lượt đọc chéo; CSV cạnh có 120 dòng vì có 20 lượt đọc chéo. Chọn 50 node rủi ro từ node thật. Mọi phiếu ban đầu là `pending_review`; Codex không điền kết quả chấm độc lập. Đọc hướng dẫn trong báo cáo, chỉ sửa 5 cột người chấm được phép; `summarize` từ chối nếu ID/evidence/membership/assignment hoặc input snapshot đổi. `unverifiable` được tính là chưa đúng, `pending_review` bị loại khỏi mẫu số đã chấm; tỷ lệ khi chưa chấm là null. Không suy precision toàn graph >90% từ mẫu.

`run` từ chối ghi đè phiếu đã sửa. Nếu đổi snapshot/rule/seed, dùng `output_dir` mới; `summarize` chỉ cập nhật báo cáo dẫn xuất, giữ phiếu gốc. Trạng thái A6/A7 dựa trên kiểm tra máy và phần chấm thật, không dựa vào số mẫu đã tạo. B cần xem các issue owner B/A|B: evidence CITES chưa trỏ cụ thể reference field, các xung đột ORCID, tên trùng và ngữ cảnh Method cần đọc nguồn. Hiện A6 đã có phần tự động và phiếu chấm; việc chấm A/B, phân xử bất đồng và nghiệm thu chất lượng vẫn đang chờ.

## A7 — Báo cáo dữ liệu, tiền xử lý và NLP

Nội dung chuẩn: [báo cáo A7](report/a7_data_preprocessing_nlp.md), gồm nguồn/phạm vi, chuẩn hóa và định danh, luật Task/Dataset, bảng thống kê theo hội nghị, hai hình và giới hạn audit. A8 cập nhật config A7 sang ứng viên graph/NLP dùng A5 CVPR + A3 ICCV và luật A4/B5; tổng nhóm dùng union canonical ID, affiliation dùng DISTINCT authorship làm mẫu số. Chạy A8 để tạo ứng viên trước khi chạy riêng A7; không thay raw/schema, phiếu A6 cũ hoặc code B.

```powershell
$a7Python = ".\.venv-a4\Scripts\python.exe"
& $a7Python -m pip install -r config/requirements_a7.txt
& $a7Python -B -X utf8 -m src.reporting.a7 --config config/a7_report.json
& $a7Python -B -X utf8 -m unittest discover -s quality/checks -p 'test_a7_report.py' -v
```

Đầu ra: `outputs/a7/metrics.json`, `outputs/a7/figures/*.{png,svg}` và các khối bảng có marker trong báo cáo. PNG 300 dpi để chèn Word, SVG để chỉnh cỡ không mất nét. Mã `src/reporting/a7.py` tái sử dụng reader/validator Contract, replay NLP và cách tổng hợp phiếu A6; chạy offline sau khi cài thư viện. Phần văn bản ngoài marker được giữ khi chạy lại. Đổi snapshot bằng config, không sửa manifest cũ; B thiếu input tùy chọn hiện `PENDING_B`, graph lệch corpus không được công bố làm tổng nhóm mới, hash/schema sai làm lệnh dừng.

A7 có thể hoàn thiện nội dung từ dữ liệu hiện có dù B6–B7 chưa xong. Các phần NetworkX/case study và chốt snapshot nhóm vẫn `PENDING_B`; chấm/đọc chéo audit còn cần cả A và B. Chưa có precision thủ công thì giữ null, không kết luận toàn graph >90%. Chi tiết số liệu, nguồn và giới hạn chỉ duy trì trong báo cáo A7.

## A8 — Tích hợp, kiểm thử và bàn giao

Hướng dẫn/trạng thái chuẩn: [bàn giao A8](report/a8_handoff.md). Runner `src/integration/a8.py` gọi lại collector/clean/A5 validators, NLP A4/B5, exporter/reader B3/B4, audit và A7; không xây pipeline graph khác. Input A5 CVPR + A3 ICCV; output riêng `data/processed/mxh_cv_700/a8/{nlp,graph}`. Graph B5 và dữ liệu A/B cũ được giữ nguyên. Có đủ 700 core vẫn là ứng viên, chưa là release cuối nếu audit/live/B6–B8 chưa qua.

```powershell
# Tạo môi trường một lần; sau khi cài dependencies, replay chạy offline.
py -3.12 -m venv .venv-a4
$a8Python = ".\.venv-a4\Scripts\python.exe"
& $a8Python -m pip install -r config/requirements_a7.txt
if (!(Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
& $a8Python -B -X utf8 -m src.integration.a8 run
# Đối chiếu DB theo snapshot/content hash, chỉ MATCH đọc dữ liệu:
& $a8Python -B -X utf8 -m src.integration.a8 neo4j-check
```

Biên nhận ở `outputs/a8/integration_manifest.json`, chi tiết/lệnh/log ở `validation_summary.json` và `*_tests.log`. Trạng thái: PASS/FAIL/PENDING_B/BLOCKED_ENV/NOT_RUN; bỏ qua tests không phải PASS. Mặc định runner không import/xóa DB, và vô hiệu hóa live tests tự ghi DB của B trong lượt regression offline. Thiếu Neo4j driver/kết nối ghi BLOCKED_ENV; `last_import.json` cũ không chứng minh DB hiện tại.

Audit đúng ứng viên ở `outputs/a8/audit`, giữ phiếu cũ `outputs/a6`. Sau khi A/B chấm, chạy `python -m src.audit summarize --config config/a8_audit.json` rồi A8; runner không ghi đè phiếu đã điền. Đổi nguồn/rule/snapshot cần output NLP/graph/audit mới và cập nhật các config A8 + A7 cho cùng binding. Không chỉnh manifest đã khóa.

Thử import chỉ qua `python -m src.integration.a8 test-import` trên instance test riêng, rỗng, với `A8_NEO4J_TEST_URI/USER/PASSWORD` do người vận hành cấu hình. Helper từ chối port mặc định/chính, DB có dữ liệu và URI chứa credential; không dùng `.env`, không tự tạo mật khẩu/server hoặc dọn DB. Nó gọi loader B để thử nhập lặp và rollback; phần live chỉ được công nhận khi receipt đúng snapshot ghi PASS. Khi B bổ sung analysis/báo cáo, cập nhật đường dẫn dependency trong `config/a8_integration.json` và thực hiện lệnh B bàn giao; file xuất hiện chỉ chuyển NOT_RUN cho tới khi kiểm chứng, không tự thành DONE.

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
