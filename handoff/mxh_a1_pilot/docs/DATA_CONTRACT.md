# Hợp đồng dữ liệu phiên bản 1

Phiên bản kỹ thuật: **1.0.0**. Phạm vi A1: 30 CVPR 2024 của A và 30 ICCV 2023 của B, main conference, scope core. Bản này cung cấp schema để hai người dùng chung và review trong Git; chưa có xác nhận của B trong phiên làm việc này. Các bảng graph bên dưới là hợp đồng cho bước sau, chưa được sinh ở A1.

## Registry đã thống nhất về kỹ thuật

Giữ nguyên 7 cột đầu của file B; thêm 8 cột phía sau. `schemas/data_contract.json` là bản đọc bằng máy. `schemas/paper.schema.json` là JSON Schema Draft 2020-12 cho mỗi Paper thô.

| Trường theo thứ tự | Kiểu | Bắt buộc tại A1 | Ý nghĩa |
|---|---|---|---|
| paper_id | string | Có | `cvf:CVPR2024:SLUG` hoặc `cvf:ICCV2023:SLUG`, bỏ `_paper.html` khỏi basename |
| doi | string hoặc null | Không | DOI trần, lower-case; không tự đoán |
| cvf_url | URL | Có | URL HTTPS chính thức, main conference |
| conference | enum | Có | CVPR / ICCV |
| conference_year | integer | Có | Năm kỳ hội nghị, không thay bằng ngày preprint |
| owner | enum | Có | A / B; trách nhiệm tập bài |
| status | enum | Có | registered / cvf_verified / needs_review / excluded |
| schema_version | string | Có | 1.0.0 |
| track | enum | Có | main |
| scope | enum | Có | core; reference dành cho graph sau |
| venue_id | string | Có | `venue:CVPR:2024:main` hoặc `venue:ICCV:2023:main` |
| title | string | Có | Title CVF đã NFC và chuẩn hóa khoảng trắng |
| selection_rank | integer | Có | Thứ tự trong manifest mỗi owner, bắt đầu 1 |
| source_record_id | string | Có | Khóa ngoại tới bản ghi trang bài CVF |
| verified_at | timestamp | Có | Thời điểm tải nguồn dùng kiểm tra, UTC |

`cvf_verified` yêu cầu URL nằm trong full listing main conference, HTTP 200, title giữa meta và nội dung nhất quán, có danh sách tác giả, metadata hội nghị/năm khớp. Không có nghĩa là đã ghép OpenAlex hay kiểm chứng danh tính người. Abstract/DOI/affiliation thiếu không tự loại một bài có title, authors, venue và URL ổn định.

## Metadata Paper và bản nguồn

Mỗi dòng `pilot_papers.jsonl` là một Paper với các trường registry liên quan, `title_raw/title`, `abstract_raw/abstract`, `authors`, DOI, URL PDF/arXiv, ngày và độ chính xác ngày, BibTeX gốc, trạng thái thu thập và source FK. `authors` là danh sách có thứ tự gồm `name`, `name_raw`, `author_order`; không phải danh sách global Author ID.

`publication_date` giữ `YYYY`, `YYYY-MM` hoặc `YYYY-MM-DD`; `date_precision` lần lượt là year/month/day. Ví dụ BibTeX chỉ có June 2024 thì ghi `2024-06`, không ghi `2024-06-01`. `citation_count=null` khi chưa thu, 0 chỉ khi nguồn xác nhận. `referenced_works=null` nghĩa là chưa biết; `[]` chỉ khi nguồn được kiểm tra và xác nhận không có references.

`source_records.jsonl` có `source_record_id`, `paper_id` (null cho listing), `source`, `source_kind`, `source_id`, `source_version`, `url`, `fetched_at`, `http_status`, `content_sha256`, `raw_path`, `content_type`, `etag`, `last_modified`, `schema_version`. A1 chỉ có source=CVF; arXiv/OpenAlex URL ghi nhận chưa trở thành bản nguồn đã tải. Hash tính trên HTML bytes trước nén gzip. ID nguồn là SHA-256 của URL và hash nội dung có phân cách U+0000; cache lưu raw bằng hash nội dung.

CVF/arXiv/OpenAlex của cùng công trình dùng chung Paper. Giữ paper_id CVF đã chấp nhận; DOI và các ID khác bổ sung vào alias map/merge log ở A3. Title giống nhau chỉ là ứng viên ghép, chưa đủ để xác nhận cùng bài. Full author list của bản hội nghị là danh sách đại diện; không lấy hợp các phiên bản để tăng đồng tác giả.

## Authorship và affiliation theo từng bài

`authorships.csv` giữ `authorship_id`, `paper_id`, `author_id`, `author_name`, `author_name_raw`, `author_order`, `identity_status`, `affiliation_raw`, `institution_id`, `source_record_id`, `owner`.

Ở A1, mỗi Paper × author_order có một dòng; `authorship_id` là hash của hai trường đó, `author_id` và `institution_id` trống, `identity_status=unresolved`. ID này định danh một lượt đứng tên trong bài, không phải người. Không tạo một Author toàn graph bằng tên hay dùng ID lượt đứng tên làm global Author ID.

Ở bước làm giàu, một tác giả có nhiều affiliation tạo nhiều dòng cho cùng `authorship_id`, mỗi dòng một `institution_id` có căn cứ và raw affiliation tương ứng. Khóa logic chống trùng của CSV là `(authorship_id, institution_id)`; ô `institution_id` trống được xem là một giá trị thiếu duy nhất trong khóa này. Khi đã có affiliation xác minh, thay dòng thiếu của cùng lượt đứng tên bằng các dòng xác minh; không giữ thêm dòng thiếu để tăng số bản ghi. Số lượt đứng tên phải đếm DISTINCT authorship_id, không đếm số dòng affiliation. Đây là khóa logic trong CSV, không phải primary key SQL có NULL.

Author identity ưu tiên OpenAlex/ORCID có đối chứng. Institution ưu tiên OpenAlex Institution ID hoặc ROR; không gộp cơ quan con với cơ quan mẹ chỉ vì gần tên. Affiliation phải gắn đúng bài, không lấy nơi làm việc hiện tại gán ngược. Chưa resolve thì giữ trong bảng quan sát/review, chưa tính là Author hay Institution đã xác minh của graph.

## Hợp đồng graph cho bước sau

8 nhãn: Author, Paper, Institution, VenueEdition, Task, Method, Dataset, Country. Node tối thiểu: `id,label,name,owner,source_origin,source_record_ids,validation_status`. `source_origin` và `source_record_ids` trong CSV là JSON array string. Các thuộc tính chuyên biệt lưu trong schema của nhãn ở bước triển khai graph; tránh nhét JSON object lồng nhau làm property Neo4j.

Edge tối thiểu: `edge_id,src,dst,type,weight,derivation,validation_status,evidence_ids,paper_ids,owner,source_origin`. Khóa cạnh `(src,type,dst)`; ID là SHA-256 của ba giá trị có phân cách U+0000, thêm prefix `edge:`. Với cạnh vô hướng, sort hai ID bằng thứ tự từ điển trước khi tạo khóa và chỉ lưu một hướng. Không tạo self-loop cho cộng tác.

| Type | Nguồn → đích | Cách tạo và bằng chứng |
|---|---|---|
| AUTHORED | Author → Paper | Authorship đã xác minh của bản đại diện |
| AFFILIATED_WITH | Author → Institution | Đúng người, cơ quan trên bài/năm, lưu paper_ids trong evidence |
| PUBLISHED_IN | Paper → VenueEdition | Danh sách main conference đã xác minh |
| CITES | Paper → Paper | References của nguồn tới bài đích; không từ citation_count |
| BASED_IN | Institution → Country | Quốc gia của cơ quan từ nguồn; không phải quốc tịch tác giả |
| COAUTHORED_WITH | Author ↔ Author | Hai người cùng Paper core đại diện |
| COLLABORATED_WITH | Institution ↔ Institution | Hai tác giả khác nhau gắn hai cơ quan trên cùng Paper core |
| STUDIES_TASK | Paper → Task | Bài hiện tại nghiên cứu nhiệm vụ; title/câu bằng chứng |
| USES_METHOD | Paper → Method | Bài hiện tại dùng/xây phương pháp; loại baseline/related work đơn thuần |
| EVALUATED_ON | Paper → Dataset | Có bằng chứng đánh giá; nhắc tên hoặc chỉ pretrain chưa đủ |

Hai quan hệ cộng tác có weight bằng số Paper core đại diện duy nhất hỗ trợ; các loại còn lại weight=1. Nhiều nguồn chỉ hợp evidence, không nhân cạnh. `AFFILIATED_WITH` cùng cặp được hợp paper_ids/năm ở evidence; không dùng một thuộc tính year đơn trị làm mất lịch sử. `owner=A+B` khi có đóng góp từ cả hai tập. Không tạo loại quan hệ thứ 11 cho phân tích trích dẫn nhóm.

## Evidence

`evidence.jsonl`: `evidence_id,paper_id,source_record_id,source_url,field_path,evidence_text,start_char,end_char,rule_id,rule_version,captured_at,supporting_evidence_ids,owner`.

Evidence metadata dùng đường dẫn tới trường nguồn, ví dụ `authors[0]` của quan sát CVF gắn snapshot. Evidence NLP giữ câu, field_path, vị trí `[start_char,end_char)` theo Unicode code point của title/abstract đã chuẩn hóa gắn source_record_id, rule/version và thời gian. Không tính byte offset UTF-8. Evidence suy dẫn trỏ tới các evidence đầu vào và Paper; hợp tác cơ quan phải truy được hai tác giả khác nhau.

Hàm `src.common.evidence_id` khóa quy tắc v1: SHA-256 với phân cách U+0000 của paper_id, source_record_id, field_path, rule_id, rule_version, evidence_text (giữ nguyên), start_char, end_char và JSON compact của supporting_evidence_ids đã sort/khử trùng; thêm prefix `evidence:`. Null text/offset dùng chuỗi rỗng trong khóa. Hai offset phải cùng có hoặc cùng null. Các bước sau dùng lại hàm này, không tự viết hash khác. A1 chưa sinh evidence graph; helper chỉ thống nhất định danh.

Định dạng ID node khác: `author:openalex:A123` (ORCID làm alias, hoặc `author:orcid:...` khi chỉ xác minh được ORCID), `institution:openalex:I123` hoặc `institution:ror:...`, `country:VN` theo mã quốc gia nguồn, `task:object-detection`, `method:vision-transformer`, `dataset:coco-2017` theo từ điển đã review. Các số và tên ví dụ chỉ minh họa định dạng. Nếu sau này hai canonical ID được xác nhận cùng thực thể, giữ alias và ghi merge_log, không đổi khóa âm thầm.

## Định dạng và thay đổi phiên bản

CSV UTF-8 có BOM, dấu phẩy, LF, quoting chuẩn; list là JSON array string. JSON/JSONL UTF-8; thiếu là null. Không dùng chuỗi `nan`, `None`, `Unknown` thay dữ liệu. Timestamp thu thập UTC RFC3339, hiển thị giờ Việt Nam khi cần đọc lịch làm việc.

Thêm trường không phá tương thích: tăng minor. Sửa parser hoặc tài liệu mà không đổi hợp đồng: tăng patch/parser_version phù hợp. Đổi tên cột, kiểu, key hoặc quy tắc null: tăng major và kèm migration. Giữ version trong config, contract và dữ liệu cùng nhau. Commit/PR ghi rõ thay đổi schema và để người còn lại review trước khi mở lô 350.
