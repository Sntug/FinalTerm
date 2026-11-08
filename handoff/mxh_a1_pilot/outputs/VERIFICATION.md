# Kết quả xác minh gói A1

Môi trường chạy thực tế: CPython 3.12.14 trên Linux. Chi tiết ở `runtime.json`. Không cài thư viện ngoài cho collector hoặc các test bắt buộc.

| Kiểm tra đã chạy | Kết quả |
|---|---|
| Thu thập từ mạng CVF | 62 request thành công: hai full listing và 60 trang bài |
| Số Paper sau chuẩn hóa | 60, gồm A 30 CVPR 2024 và B 30 ICCV 2023 |
| Kiểm tra dữ liệu và snapshot | 157 kiểm tra, 0 thất bại; chi tiết `quality_checks.json` |
| Unit và integration tests | 28 test thành công |
| Dựng lại từ thư mục mới, chỉ có code/config/schema/input/cache | 14 tệp đầu ra được đối chiếu hash và trùng khớp từng byte |
| Chạy lại offline lần hai | Cùng 14 tệp vẫn trùng khớp; 0 network request, không tăng số bản ghi |
| JSON Schema Draft 2020-12 bằng validator độc lập jsonschema 4.26.0 | Schema hợp lệ; 60 Paper, 0 lỗi |
| File đầu vào B so với bản đính kèm | SHA-256 trùng khớp; giữ nguyên nội dung |

28 test gồm 27 unit test và một integration test. Integration test tự chạy hai lần collect offline rồi chạy quality trong thư mục mới. Validator jsonschema là công cụ đối chứng trong môi trường kiểm tra; không phải dependency của code A1. Lệnh `src.quality` dùng bộ kiểm tra loại/ràng buộc mà schema Paper thực sự sử dụng, không tự nhận là validator JSON Schema tổng quát.

Đã thử tính bất biến ID, phân biệt hướng CITES, chuẩn hóa cạnh cộng tác vô hướng, từ chối self-loop cộng tác, phân biệt người với lượt đứng tên, chuẩn hóa Unicode, thứ tự tác giả, độ chi tiết ngày, loại workshop, trùng B, lệch ID/URL, cache sai hash và dừng HTTP 403.

Chưa thử trực tiếp trên Windows, chưa gọi OpenAlex, chưa kiểm chứng danh tính tác giả, chưa chạy NLP/Neo4j và chưa đo chất lượng >90%. Số kiểm tra tự động không phải precision của graph.
