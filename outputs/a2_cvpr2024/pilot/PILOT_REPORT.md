# A2 — báo cáo pilot 30 CVPR 2024

Ngày 08/11/2026. Nhánh `feat/a2-collector-v2`. Chưa commit/push; chưa chạy 350 bài.

## Kết quả thực tế

| Chỉ số | Số lượng / mẫu số | Tỷ lệ |
| --- | --- | --- |
| Paper core hợp lệ, đúng 30 ID đã khóa | 30/30 | 100% |
| Work matched | 27/30 | 90% |
| Work not_found | 0/30 | 0% |
| Work needs_review | 3/30 | 10% |
| Work not_collected | 0/30 | 0% |
| Abstract có văn bản | 30/30 Paper | 100% |
| Affiliation có trong raw Work đã matched | 27/30 Paper | 90% |
| Affiliation đã gắn chắc vào CVF authorship | 0/159 lượt đứng tên; 0/30 Paper | 0% |
| References đã đọc từ Work matched | 27/30 Paper | 90% |
| References không rỗng | 25/30 Paper | 83,33% |

Hai Work trả `referenced_works=[]`: đây là danh sách rỗng quan sát ở nguồn, không chứng minh bài gốc không có tài liệu tham khảo. `cited_by_count` được lưu riêng với nguồn/thời điểm; không dùng nó tạo references. Danh sách tác giả CVF được giữ nguyên, không union OpenAlex. Cả 159 authorship vẫn unresolved, affiliation_status=not_collected; không tạo alias, merge/split hay người duyệt giả.

Snapshot cuối có 12 bảng, 741 records, 89 source records (31 CVF + 58 OpenAlex), 60 text versions. `graph_ready=false`, node_count/edge_count=null. Có 3 evidence metadata phục vụ review, không có node/edge graph.

## Work cần review

| Bài | Vấn đề còn lại |
| --- | --- |
| C2RV: Cross-Regional and Cross-View Learning for Sparse-View CBCT Reconstruction | Truy vấn title không có kết quả; fallback rộng có ứng viên nhưng không đạt title/byline/venue. Chưa xác định được Work. |
| Do Vision and Language Encoders Represent the World Similarly? | Work W4402716370 khớp title, venue và năm nhưng byline có thứ tự chưa khớp CVF. |
| ADFactory: An Effective Framework for Generalizing Optical Flow with NeRF | Work W4402702995 khớp title, venue và năm nhưng byline có thứ tự chưa khớp CVF. |

Chi tiết từng ứng viên và từng điều kiện: `matching.json`; hàng đợi chuẩn v2: bảng `needs_review.csv` trỏ bởi snapshot manifest. Không tự chấp nhận các trường hợp này để tăng tỷ lệ matched. Chưa có phép kiểm chứng thủ công độc lập; matched là kết quả rule có thể tái lập từ raw.

## Quy tắc Work và nguồn

Ưu tiên DOI được CVF xác nhận; nếu thiếu, tìm cụm title trong trường title, fallback search rộng để giữ ứng viên review. Chỉ nhận một ứng viên duy nhất, danh sách kết quả không bị cắt, title chuẩn hóa khớp và toàn bộ byline có thứ tự khớp, kèm DOI hoặc venue/năm hoặc liên kết CVF/PDF/arXiv của chính bài (năm lệch tối đa một khi có liên kết phiên bản). Đọc endpoint Work chi tiết và kiểm tra lại trước khi enrich. Không coi điểm relevance/title tương tự là bằng chứng đủ. Khớp Work không tự phân giải danh tính Author.

Rule `openalex-work-match=1.1.0`; code `a2-collector-1.1.0`; CVF parser và normalizer giữ nguyên. Contract v2 không thay đổi. Snapshot raw CVF giữ nguyên compressed bytes, fetched_at, content hash và source IDs của bàn giao.

Tài liệu chính thức đã đối chiếu ngày chạy: [Authentication](https://help.openalex.org/api/authentication/), [Error handling](https://help.openalex.org/api/errors/), [Search](https://help.openalex.org/api/searching/), [Work attributes](https://help.openalex.org/data/works/attributes/). Pilot dùng truy vấn cơ bản không key, giãn cách 1 giây. Nếu dùng key, đọc OPENALEX_API_KEY từ môi trường hoặc `.env`, gửi qua Authorization header; không đưa vào URL, log hoặc cache. Không làm thủ tục đăng ký tài khoản/key trong phiên này.

## Lỗi nguồn và độ bền

- Lượt đầu trong sandbox bị WinError 10061: 3 lần thử kết nối, 0 OpenAlex hoàn tất. Đã lưu checkpoint và snapshot phần CVF; `live_run.log` ghi exit 2.
- Chạy với quyền mạng đã thành công. Truy vấn rộng đầu tiên trả nhiều danh sách bị cắt; đã chuyển sang title phrase thay vì hạ tiêu chuẩn matching. Hai lượt có dữ liệu mạng lần lượt 31 và 56 request OpenAlex, tổng 87; CVF không tải lại. `live_run_network.log`, `live_run_title_query.log` và `live_summary.json` lưu bằng chứng.
- Lượt cuối không còn lỗi nguồn, 30/30 truy vấn đã xử lý, 3 Work cần review. Chưa gặp hết quota thật; ca quota/Retry-After được kiểm tra bằng mock.
- Retry tối đa 2, timeout 30 giây, backoff tăng dần và tôn trọng Retry-After (giây hoặc HTTP date). Khi cần đợi quá 30 giây hoặc hết retry, lưu gate/checkpoint rồi trả exit 2; chạy lại sau thời điểm gate. Không bỏ qua gate bằng cách đổi key/host.
- Cache hash sai dừng, không tự tải lại. Cache hợp lệ được dùng trước khi gọi mạng. Resume đọc lại raw hợp lệ và tái tính kết quả; checkpoint ghi tiến độ, không được dùng để bỏ qua kiểm tra hash. Mỗi response và mỗi checkpoint được công bố atomically.
- Snapshot là các bảng bất biến trong `data/processed/cvpr2024/pilot/snapshots/<digest>/`. Manifest hiện hành chỉ cập nhật sau khi verify; bản cũ/partial vẫn còn. Nếu một bảng bất biến đã bị sửa, chạy lại dừng thay vì ghi đè. Không chạy hai writer cùng một config đồng thời.

## Lệnh PowerShell đã kiểm tra

Chạy ở repo root `D:/UET_Projects/PTMXH/FinalTerm`, Python 3.12.10, không cần pip:

```powershell
py -3.12 -B -X utf8 -m src.collect --config config/a_cvpr2024_pilot.json
py -3.12 -B -X utf8 -m src.collect --config config/a_cvpr2024_pilot.json --offline
py -3.12 -B -X utf8 -m src.collect.verify --manifest data/processed/cvpr2024/pilot/snapshot_manifest.json
py -3.12 -B -X utf8 -m unittest discover -s quality/checks -p "test_a2_*.py" -v
```

Cả online từ cache và offline đều exit 0, không có request mới, giữ nguyên bytes manifest. `replay_check.json` và các `*_run.log` ghi kết quả. 37 test qua, gồm parser/sai hội nghị/workshop, URL/ID trùng, schema/hash/khóa ngoại, đường dẫn thoát repo, retry/quota/key, resume sau lỗi chi tiết, cấu hình ICCV trong thư mục tạm và replay không nhân bản. Kiểm tra schema dùng subset bao phủ ràng buộc trong 12 schema bàn giao; không gọi validator Draft 2020-12 bên ngoài.

`raw_path` và mọi path trong manifest đều tính từ repo root. Verifier nhận `--manifest` độc lập, không suy vị trí snapshot từ config. Đọc bảng theo manifest thay vì giả định bảng ở ngay dưới `data/processed`.

## Bàn giao và giới hạn

`config/a_cvpr2024_pilot.json` khóa target_count=30 và registry A đã bàn giao; selection_file còn kiểm tra đúng thứ tự/ID/source IDs cũ. `config/collector.example.json` là mẫu ICCV cho B tự sửa registry/path/target_count; runtime không khóa owner A hoặc số 30. Registry phải có đúng target_count dòng duy nhất; collector không tự chọn thêm khi thiếu. Seed được ghi vào selection manifest; registry cung cấp danh sách đã chọn.

Mã nguồn trong `src/collect`, helper văn bản trong `src/clean`; không import code handoff. Schema chuẩn `config/contracts/v2/data_contract.json` và 13 JSON liên quan giữ nguyên bytes. Dữ liệu ICCV chính thức và registry chung không được ghi. Export offline A trước đó nằm ngoài thư mục pilot được giữ nguyên. Raw vẫn bị Git ignore; máy khác cần được bàn giao cache/raw để chạy offline.

A2 pilot đã chạy xong; A2 đủ 350 chưa hoàn thành. Chưa thu 320 bài tiếp theo, chưa resolve 159 Author/affiliation và chưa xử lý thủ công 3 Work mơ hồ. Chưa dựng NLP/Neo4j hoặc đo precision graph.

Snapshot cuối: `snapshot:v2:737f8bc206c9a39e0b99d6ffb085036acbbfdf323556b717e5634c5cea0d64ba`.
