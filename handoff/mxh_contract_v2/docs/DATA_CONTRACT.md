# Hợp đồng dữ liệu phiên bản 2

Chốt kỹ thuật ngày 06 tháng 11 năm 2026, phiên bản **2.0.0**, thay hợp đồng 1.0.0 cho các bước tiếp theo. Phạm vi vẫn là 350 CVPR 2024 của A và 350 ICCV 2023 của B, 8 nhãn nút và đúng 10 quan hệ. Đây là quy tắc triển khai chung; việc phản hồi đề xuất không chứng minh code Neo4j của B đã đáp ứng. Chưa được cung cấp `D_pilot.py` nên chưa review file đó.

Registry giữ nguyên 15 cột. Paper ID, CVF URL, source ID và thứ tự tác giả của pilot không đổi. Bản nguồn v1 được lưu nguyên; exporter v2 có schema_version mới. Phiên bản schema, parser, chuẩn hóa, từ điển, rule và snapshot là các khái niệm riêng, không tăng đồng loạt khi không có thay đổi tương ứng.

## Đánh giá năm đề xuất của B

| Đề xuất | Quyết định và điểm làm rõ |
|---|---|
| Ưu tiên nguồn | Nhận. Ưu tiên theo từng trường, không xem toàn bộ CVF là chân lý tuyệt đối. Giữ các quan sát mâu thuẫn để review. |
| Merge và split log | Nhận. Sáu cột chỉ đủ mô tả merge đơn giản; cần action, nhiều ID đầu vào/đầu ra, thay đổi before/after và bản ghi bị ảnh hưởng để tách lại đúng. |
| Cập nhật graph | Nhận. MERGE không thu hồi cạnh mất căn cứ. Cùng snapshot phải giữ cùng nội dung graph, không chỉ cùng số lượng. |
| Hash văn bản NLP | Nhận. Dùng normalized_text_sha256 của toàn bộ title hoặc toàn bộ abstract; giữ content_sha256 riêng cho bytes nguồn. Offset là nửa mở [start_char,end_char). |
| Trạng thái và phiên bản | Nhận. Optional chỉ tăng minor khi reader/validator cũ thực sự chấp nhận. Thêm cột vẫn có thể phá một chương trình kiểm tra header cố định. |

## 1 Chọn nguồn và lưu quyết định theo trường

| Trường hoặc nhóm | Nguồn chọn và quy tắc |
|---|---|
| Hội nghị, năm, track | Danh sách main conference CVF đúng kỳ. Không suy từ một lần abstract nhắc CVPR/ICCV. |
| Title và danh sách tác giả có thứ tự | Bản hội nghị CVF đại diện. Không union tác giả CVF, arXiv và OpenAlex. Nếu HTML CVF mâu thuẫn PDF hội nghị hoặc có lỗi rõ ràng, chuyển trường đó sang needs_review để đọc bản gốc. |
| Abstract dùng NLP | CVF nếu có. Nếu thiếu, dùng abstract của OpenAlex đã ghép chắc chắn hoặc arXiv được đối chiếu rõ phiên bản. Ghi source, field path và text_version_id của chính văn bản thay thế. |
| DOI và Work/Author/Institution ID | Nguồn định danh đã đối chiếu. DOI/title giống nhau hoặc OpenAlex trả một ứng viên không tự đủ để xác nhận đúng tác giả. Giữ paper_id đã chốt khi bổ sung ID ngoài. |
| Affiliation | Khai báo của đúng tác giả trên đúng bài, ưu tiên bản hội nghị/PDF có chứng cứ; OpenAlex authorships của work đã ghép dùng bổ sung. Không dùng cơ quan hiện tại gán ngược. |
| Publication date | Ngày bản hội nghị ở CVF/BibTeX với độ chi tiết nguồn. Ngày arXiv ở source record của arXiv; không ghi đè conference_year hoặc ngày bản hội nghị. |
| References và citation_count | referenced_works/danh mục tham khảo xác định CITES. citation_count là số liệu theo nguồn và thời điểm, không tạo danh sách cạnh trích dẫn. |
| Quốc gia tổ chức | Metadata của đúng tổ chức/định danh đã xác minh; không đoán từ tên hoặc quốc tịch tác giả. |

`field_provenance.csv` chỉ rõ nguồn được chọn cho từng trường khoa học không rỗng. `source_record_id` + `field_path` trỏ tới nguồn thực, `selection_rule` giải thích lựa chọn, `candidate_source_record_ids` giữ các nguồn đã so sánh. Tên tác giả hiển thị đảo từ Last, First sang First Last là phép định dạng của parser, không phải phân giải danh tính.

Field path có tiền tố: `html:` cho bộ chọn HTML/thuộc tính hoặc text; `json:` cho đường dẫn JSON nguồn. Ví dụ `html:meta[name=citation_title]@content`, `html:div#abstract.text`, `json:authorships[0].institutions[0].id`. Parser/rule định nghĩa cách đọc selector; không coi đường dẫn trong một JSON đã hợp nhất là bằng chứng nguồn duy nhất.

Một khác biệt khoảng trắng có thể xử lý bằng rule công bố. Mâu thuẫn thật chưa giải quyết được ghi `field_provenance.validation_status=needs_review` và một dòng needs_review. Vẫn giữ nguồn đại diện để đọc, nhưng không dùng thông tin tranh chấp tạo quan hệ phụ thuộc. Paper chỉ đổi `status=needs_review` khi chính điều kiện nhận bài như title, authors hoặc venue còn không chắc chắn. Thiếu OpenAlex/affiliation không tự làm hỏng kiểm tra CVF.

## 2 Trường bắt buộc và quy tắc null

Danh sách đầy đủ, thứ tự cột, kiểu dữ liệu, enum, trường nullable và JSON Schema cho từng record nằm ở `schemas/data_contract.json` và các `*.schema.json`. Bản tra cứu dễ đọc nằm ở `docs/FIELD_INDEX.md`. Tất cả cột/key đã liệt kê phải tồn tại. Nullable nghĩa là giá trị được phép null, không có nghĩa được bỏ cột/key. Quy tắc điều kiện theo loại bằng chứng và tính toàn vẹn khóa ngoại vẫn phải kiểm tra thêm ngoài JSON Schema.

CSV là UTF-8 có BOM, dấu phẩy, LF, quoting chuẩn. JSON/JSONL là UTF-8. Ô CSV rỗng tương ứng null cho trường nullable. List ghi JSON array string, gồm cả `[]`; object vận chuyển ghi JSON object string. Integer không viết thành số thực. Không dùng `nan`, `None`, `Unknown` làm dữ liệu thật.

Null nghĩa là chưa biết/chưa thu. Số 0 hoặc `[]` chỉ dùng khi nguồn đã được kiểm tra và xác nhận giá trị đó. Timestamps là UTC RFC3339. Ngày công bố giữ YYYY, YYYY-MM hoặc YYYY-MM-DD kèm date_precision; không thêm ngày 01 khi chỉ biết tháng.

## 3 Registry và Paper

15 cột registry theo đúng thứ tự:

`paper_id, doi, cvf_url, conference, conference_year, owner, status, schema_version, track, scope, venue_id, title, selection_rank, source_record_id, verified_at`

`status` chỉ gồm registered, cvf_verified, needs_review, excluded. Giữ tên cột status để không buộc hai người đổi tên không cần thiết. `cvf_verified` chỉ nói kiểm tra CVF đã qua, không nói Author đã resolve hoặc graph đạt chất lượng >90%. `source_record_id` trong registry chỉ là nguồn đại diện, không thay cho provenance theo trường.

`papers.jsonl` là bảng Paper chuẩn cho xử lý; raw CVF/OpenAlex/arXiv và snapshot nguồn lưu riêng. So với quan sát v1, bảng chuẩn dùng `representative_source_record_id` và bổ sung `title_text_version_id`, `abstract_text_version_id`, `citation_count_source_record_id`, `citation_count_observed_at`. Danh sách authors gồm authorship_id, name, name_raw, author_order; đây là các lượt đứng tên, không tự là global Author ID. `paper_metadata.csv` của gói v1 chỉ là bản xem dữ liệu, không là đầu vào chuẩn v2.

Paper ID vẫn là `cvf:EDITION:SLUG`, DOI là alias bổ sung. Hai bản CVF/arXiv của cùng bài chỉ tạo một Paper. `scope=core` hoặc reference phải phân biệt khi đếm; không dùng reference để che thiếu phần core.

## 4 Authorship và danh tính

`authorships.csv` giữ 11 cột cũ và thêm `identity_source_record_id`, `affiliation_source_record_id`, `affiliation_status`, `decision_ids`.

`source_record_id` cũ chứng minh lượt đứng tên CVF; hai nguồn mới lần lượt chứng minh phép gắn global Author ID và phép gắn Institution ID theo bài. Không dùng một source CVF chung để ngầm khẳng định affiliation OpenAlex đã được xác minh.

Mỗi paper_id × author_order có một authorship_id ổn định. Một lượt đứng tên có nhiều affiliation tạo nhiều dòng cùng authorship_id, khác institution_id. Khóa logic CSV là (authorship_id,institution_id); ô institution_id trống được xem là một giá trị thiếu duy nhất cho lượt đó, không phải primary key SQL có NULL. Khi có affiliation xác minh, thay dòng thiếu bằng các dòng có chứng cứ. Đếm DISTINCT authorship_id để thống kê lượt đứng tên.

Các dòng cùng authorship_id phải có cùng global author_id và identity_status. Chưa resolve thì author_id trống; không dùng authorship_id hoặc chuỗi tên làm ID người. `identity_status` gồm unresolved, resolved, needs_review; `affiliation_status` gồm not_collected, verified, missing_in_source, needs_review. Nếu đã resolved/verified thì ID tương ứng và source chứng minh không được trống.

ID Author dùng `author:openalex:A...` hoặc `author:orcid:...` khi chỉ xác minh được ORCID. Institution dùng `institution:openalex:I...` hoặc `institution:ror:...`. Country dùng `country:VN` theo mã nguồn. Không gộp cơ sở/phân viện với cơ quan mẹ nếu chưa có đối chứng.

## 5 Alias và quyết định merge split

`alias_map.csv` là trạng thái ánh xạ đang hiệu lực: alias_id, entity_type, source, external_id, canonical_id, decision_id. Một alias (entity_type,source,external_id) chỉ trỏ một canonical ID trong một snapshot; một canonical ID có thể có nhiều alias. alias_id là hash của ba thành phần alias, không phụ thuộc canonical_id để lịch sử gán lại truy được.

`merge_log.jsonl` là nhật ký chỉ thêm dòng, gồm decision_id, action, entity_type, input_ids, output_ids, affected_paper_ids, affected_authorship_ids, changes, reason, evidence_ids, proposed_by, reviewed_by, review_mode, decided_at, snapshot_before, reverts_decision_id.

| Action | Ý nghĩa |
|---|---|
| link / unlink | Gắn hoặc bỏ gắn quan sát/alias với một canonical entity |
| merge | Nhiều ID đầu vào, một ID giữ lại |
| split | Một ID ghép sai được phân lại về nhiều ID đúng |
| retract | Thu hồi một quyết định trước, trỏ reverts_decision_id và ghi thay đổi đảo tương ứng |

`changes` là danh sách `{table, record_key, field, before, after}`. Khi split Author, nó phải cho biết từng authorship_id nào chuyển về Author nào; chỉ ghi danh sách hai tên hoặc ID đầu ra không đủ để khôi phục đúng. Trước khi áp dụng, kiểm tra giá trị hiện tại khớp before; nếu không, dừng để xử lý xung đột. Với thay đổi tạo/xóa dòng, record_key vẫn phải xác định được dòng, before hoặc after có thể null theo rule migration của bảng.

Merge/split yêu cầu review_mode=manual và reviewed_by là A hoặc B; ưu tiên người còn lại đọc chéo. Link chính xác có thể review_mode=rule khi rule đã chốt và có chứng cứ, reviewed_by ghi tên rule, không ghi giả là A/B. Không phê duyệt tự động chỉ vì tên giống hoặc fuzzy title cao.

Không sửa mất dòng quyết định cũ. Snapshot manifest liệt kê applied_decision_ids để biết quyết định nào được áp dụng. Không nhét snapshot_after vào chính decision đang dùng tính hash snapshot, tránh phụ thuộc vòng. Affected paper/authorship IDs cộng với changes và snapshot trước cho phép tìm phần dữ liệu bị tác động; bước dựng lại graph sử dụng trạng thái quyết định mới để tính lại quan hệ, không đảo cạnh bằng phỏng đoán.

Sáu cột ID cũ, ID giữ lại, lý do, evidence, người duyệt, thời điểm chỉ là một view rút gọn cho merge. Chúng không thay thế nhật ký đầy đủ trên.

## 6 Phiên bản văn bản và bằng chứng NLP

`source_records.content_sha256` hash bytes phản hồi nguồn trước khi nén cache của nhóm. `text_versions.normalized_text_sha256` hash UTF-8 của toàn bộ một trường title hoặc abstract đã chuẩn hóa. Không hash riêng câu trích dẫn, không dùng lại tên content_sha256 để chỉ văn bản NLP.

`text_versions.jsonl` giữ text_version_id, paper_id, source_record_id, field_path, parser_version, normalization_version, normalized_text, normalized_text_sha256, captured_at. `captured_at` là thời điểm chụp bản nguồn được kế thừa; thời điểm chạy pipeline ở snapshot manifest. Title và abstract có phiên bản riêng, không nối chúng rồi dùng offset mơ hồ.

Chuẩn hóa nfc-ws-1: Unicode NFC, sau đó split/join mọi khoảng trắng bằng một dấu cách U+0020. Giữ hoa thường, dấu câu và ký tự có nghĩa. text_version_id là SHA-256 với phân cách U+0000 của source_record_id, field_path, parser_version, normalization_version, normalized_text_sha256; prefix `text:v2:`. Code chuẩn nằm trong contract_v2.text.

`evidence.jsonl` giữ 13 trường v1 và thêm evidence_kind, text_version_id, normalized_text_sha256, normalization_version. Tất cả key tồn tại; các giá trị văn bản/hash/offset có thể null theo loại.

| evidence_kind | Điều kiện |
|---|---|
| metadata | Có source_record_id, source_url, field_path thật. text_version_id, hash NLP, normalization_version và hai offset là null. evidence_text có thể null. |
| nlp | Có đầy đủ nguồn, field_path, text_version_id, hash, normalization_version, rule_id/version và evidence_text. 0 ≤ start_char < end_char ≤ len(normalized_text); lát cắt đúng bằng evidence_text. |
| derived | Có rule_id/version và supporting_evidence_ids không rỗng, truy tới evidence nguồn thật. Các nguồn/offset trực tiếp không dùng để giả tạo một câu nguồn; để null, giữ paper_id khi suy từ một Paper. |

Offset tính bằng Unicode code point, không phải byte UTF-8 hay UTF-16 code unit của JavaScript. `[start_char,end_char)` có end loại trừ. Validator phải đối chiếu toàn bộ bộ khóa nguồn, field path, phiên bản và hash, rồi so lát cắt. Văn bản/normalizer/parser thay đổi tạo text_version_id mới; phải chạy lại hoặc kiểm chứng lại binding và offset trước khi dùng bằng chứng. Rule đổi phải chạy lại rule. Evidence cũ được lưu trong snapshot cũ, không coi còn hợp lệ cho snapshot mới.

`contract_v2.text.evidence_id` thêm phiên bản 2.0.0, kind, text_version_id, hash và normalization_version vào công thức ID. Không dùng helper v1 để tạo bằng chứng v2. Paper/source/edge ID được giữ quy tắc cũ; chỉ binding bằng chứng NLP đổi phiên bản.

## 7 Graph và quy tắc đếm

8 nhãn Author, Paper, Institution, VenueEdition, Task, Method, Dataset, Country. Node có 7 cột v1 cộng project_id và properties_json. properties_json chỉ là object vận chuyển trong CSV: loader parse và bung thành các property scalar/list đã cho phép theo nhãn; không gán object lồng nhau làm property Neo4j. Danh mục thuộc tính của từng nhãn nằm trong JSON contract.

Edge có 11 cột v1 cộng project_id. Giữ khóa (src,type,dst); cạnh vô hướng sort hai ID trước khi tạo khóa, không self-loop. Edge ID tiếp tục `edge:` + SHA-256 ba giá trị phân cách U+0000. Cùng cặp/type hợp nguồn bằng chứng, không nhân cạnh.

| Quan hệ | Đầu nguồn và đích | Căn cứ |
|---|---|---|
| AUTHORED | Author → Paper | Authorship của bản đại diện và global Author đã resolve |
| AFFILIATED_WITH | Author → Institution | Đúng người và cơ quan trên bài/năm, giữ paper_ids/evidence |
| PUBLISHED_IN | Paper → VenueEdition | Kỳ hội nghị/track xác minh |
| CITES | Paper → Paper | Danh sách references, hướng từ bài trích tới bài được trích |
| BASED_IN | Institution → Country | Quốc gia của tổ chức theo nguồn |
| COAUTHORED_WITH | Author ↔ Author | Hai Author khác nhau trên cùng Paper core đại diện |
| COLLABORATED_WITH | Institution ↔ Institution | Hai tác giả khác nhau thuộc hai cơ quan khác nhau trên cùng Paper core |
| STUDIES_TASK | Paper → Task | Bài hiện tại nghiên cứu nhiệm vụ, có title/câu bằng chứng |
| USES_METHOD | Paper → Method | Bài hiện tại dùng/xây phương pháp; loại nhắc baseline đơn thuần |
| EVALUATED_ON | Paper → Dataset | Có bằng chứng đánh giá; nhắc tên hoặc chỉ pretrain chưa đủ |

Hai cạnh cộng tác có weight bằng số Paper core đại diện duy nhất hỗ trợ. Không tăng weight theo số evidence hoặc số affiliation. Các cạnh còn lại weight=1. Ví dụ một cạnh có 3 Paper hỗ trợ; sửa một Paper làm mất căn cứ thì tính lại weight=2 và evidence còn lại, không xóa toàn bộ quan hệ nếu hai Paper kia vẫn hỗ trợ.

Chỉ node/cạnh validation_status=accepted được nhập bản graph nộp. needs_review/rejected không được dùng để đạt quota. Giữ các hồ sơ review/evidence cần thiết ngoài graph. Phân biệt lượt authorship, Author duy nhất và Paper reference. Không tạo relation type thứ 11 cho phân tích trích dẫn nhóm.

## 8 Chiến lược cập nhật Neo4j được chọn

Với một graph khoảng 700 bài, chọn **tái tạo toàn bộ phạm vi dự án từ snapshot sạch**. Không yêu cầu nhóm viết cơ chế incremental retract phức tạp ở giai đoạn này. Cách này không xóa toàn bộ DBMS hoặc dữ liệu dự án khác.

1. A/B tạo đầy đủ bảng sạch, text versions, decisions, nodes, edges và evidence. Kiểm tra schema, khóa ngoại, hash và nguồn; chỉ đánh graph_ready=true khi có bản graph thực và count tương ứng. Pilot metadata-only có graph_ready=false phải bị loader từ chối.
2. Khóa một writer cho dự án mxh_cv_700, lưu snapshot đang dùng và danh sách ID/thuộc tính kỳ vọng. Node có uniqueness theo (project_id,id) ở từng nhãn; labels/type dùng whitelist đã chốt.
3. Trong **một write transaction**, gỡ các cạnh/nút cũ thuộc đúng project_id rồi nhập lại nodes trước, edges sau từ bảng accepted. Không dùng lệnh xóa không giới hạn dự án. Nếu phát hiện liên kết vượt sang dự án khác thì dừng để xử lý, không DETACH DELETE mù quáng.
4. Kiểm tra nội dung đã nhập ngay trong transaction; lỗi thì rollback, không commit một nửa. Có thể chia UNWIND thành các lượt chạy trong cùng transaction, không biến mỗi lượt thành một commit riêng rồi coi là atomic.
5. Commit thành công mới cập nhật trạng thái lần nhập thành công và xuất số liệu/bảng/hình. snapshot_id là property loader lấy từ manifest, không phải cột trong nodes/edges và không là một phần ID node; tránh tự tham chiếu khi tính hash snapshot.

Cần benchmark giới hạn transaction/RAM trên máy B bằng pilot trước khi nhập lớn. Nếu không đáp ứng, phải điều chỉnh loader sang staging có kiểm soát và kiểm tra lại cách chuyển snapshot; không tự chia commit làm mất cam kết trên. Đây là yêu cầu cho B3, chưa phải loader Neo4j đã được triển khai hoặc chạy trong gói này.

Cùng snapshot, yêu cầu cùng node IDs/labels/thuộc tính, cạnh src/type/dst, weight, paper_ids và evidence_ids. So sánh count là cần nhưng chưa đủ: một cạnh sai có thể thay một cạnh đúng trong khi tổng vẫn không đổi. Thời gian chạy và log vận hành không được làm đổi hash nội dung graph. Cần thử ít nhất ba ca: nhập lặp; sửa affiliation làm mất cạnh cũ; lỗi giữa lần nhập phải rollback.

## 9 Trạng thái và phiên bản

| Phạm vi | Trường | Giá trị |
|---|---|---|
| Paper kiểm tra CVF | registry.status | registered / cvf_verified / needs_review / excluded |
| Ghép OpenAlex Work | papers.openalex_status | not_collected / matched / not_found / needs_review |
| Danh tính người | authorships.identity_status | unresolved / resolved / needs_review |
| Affiliation theo bài | authorships.affiliation_status | not_collected / verified / missing_in_source / needs_review |
| References | papers.references_status | not_collected / verified / missing_in_source / needs_review |
| Chọn nguồn theo trường | field_provenance.validation_status | auto_verified / verified / needs_review |
| Node và cạnh | validation_status | accepted / needs_review / rejected |
| Hàng đợi review | review_status | open / resolved / rejected |

accepted hoặc auto_verified là kết quả kiểm tra quy tắc, không tự là phép đo precision >90%. Một Paper cvf_verified có thể có mọi Author unresolved mà không mâu thuẫn. Không đổi status toàn Paper chỉ vì một cạnh Dataset bị loại.

Tăng minor chỉ khi bổ sung tương thích và đã thử reader/validator cũ. Gói v1 có header cố định và JSON Schema additionalProperties=false, nên không mặc định thêm trường optional là tương thích. Đổi tên/kiểu/key/ý nghĩa, thay quy tắc null, thay ID hoặc thêm trường bắt buộc làm bản cũ không hợp lệ phải tăng major và kèm migration. Patch dành cho sửa lỗi tương thích. A/B ghi phiên bản và migration trong commit/PR; không tự sửa một phía.

Vì thêm điều kiện bắt buộc cho evidence, đổi Paper export chuẩn và bổ sung provenance rõ nguồn, bản này dùng **2.0.0**. Raw snapshot v1 không bị viết lại. Code collector v1 vẫn là chương trình v1; cần adapter hoặc exporter v2, không chỉ đổi chuỗi version trong file rồi coi đã chuyển xong.

## 10 Bàn giao và trách nhiệm

A phụ trách collector/chuẩn hóa, field provenance, text_versions, migration và Task/Dataset. B dùng cùng text_version/evidence schema cho Method, triển khai loader cập nhật graph và các phép đếm. Cả hai dùng chung alias/decision/review files, review phép ghép mơ hồ và đối chiếu snapshot trước khi viết báo cáo.

Gói này có migration không phá dữ liệu cho A1 v1: 60 Paper, 322 lượt authorship, 62 bản nguồn; tạo 120 phiên bản title/abstract và 459 bản provenance của các trường hiện có. Không tạo DOI, affiliation, merge, NLP evidence hay cạnh Neo4j giả. URL arXiv kế thừa từ CVF chỉ chứng minh có liên kết, chưa xác minh nội dung hay phiên bản preprint. Các bảng graph/merge/alias có thể rỗng trong metadata pilot; graph_ready=false làm rõ việc chưa dựng graph.

Tài liệu và JSON contract chốt giao diện cho các bước sau. Gói không thay thế các bước ghép OpenAlex, nhận dạng thực thể, kiểm tra độc lập hoặc triển khai B3.

## Nguồn kỹ thuật đối chiếu

- Neo4j Cypher Manual MERGE: https://neo4j.com/docs/cypher-manual/current/clauses/merge/
- Neo4j Cypher Manual DELETE: https://neo4j.com/docs/cypher-manual/current/clauses/delete/
- Neo4j Python Driver Transactions: https://neo4j.com/docs/python-manual/current/transactions/
- Semantic Versioning 2.0.0: https://semver.org/

Thứ tự ưu tiên nguồn, schema và lựa chọn rebuild là quyết định thiết kế của nhóm cho bài tập này; tài liệu Neo4j/SemVer chỉ xác nhận ngữ nghĩa các thao tác và cách đánh số phiên bản.
