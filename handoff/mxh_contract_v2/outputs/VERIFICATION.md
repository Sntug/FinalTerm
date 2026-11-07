# Xác minh gói hợp đồng v2

Đã chạy trên CPython 3.12.14, Linux. Migration và verifier dùng thư viện chuẩn. Validator jsonschema 4.26.0 được dùng riêng để đối chứng JSON Schema Draft 2020-12, không là dependency của chương trình bàn giao.

| Kiểm tra | Kết quả |
|---|---|
| Chuyển A1 v1 sang export metadata v2 | 60 Paper, 322 lượt authorship, 62 source records |
| Paper/source IDs trước và sau | Giữ nguyên |
| Text versions | 120, gồm title và abstract của 60 bài |
| Field provenance | 459 bản ghi của các trường CVF đã có |
| Kiểm tra dữ liệu, khóa ngoại và hash | 12 bảng, 1.083 record; 62 raw source hashes và 120 text versions hợp lệ |
| Validator JSON Schema độc lập | 12 schema hợp lệ, 1.083 record không có lỗi schema |
| Test tự động | 15 test thành công |
| Chạy migration lại sang thư mục mới | Cùng snapshot ID, dữ liệu nguồn không ghi đè |
| Merge, NLP edges, Neo4j | Chưa thực hiện; không có dữ liệu giả để lấp chỗ trống |

Metadata snapshot có graph_ready=false. Việc kiểm tra file không chứng minh chất lượng quan hệ hay khả năng rollback Neo4j; các ca nhập lại, sửa affiliation và lỗi giữa transaction vẫn phải được B triển khai/kiểm thử trên loader thực.

Các test có kiểm tra hash toàn văn bản thay vì câu, Unicode NFC, offset nửa mở, hash/version sai, ID evidence đổi theo text version, giữ 15 cột registry/10 relation types và từ chối ghi đè output migration.
