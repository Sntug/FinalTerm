# Đề tài 30 · Mạng tác giả và tổ chức nghiên cứu thị giác máy tính

Một dự án chung cho A (350 bài CVPR 2024) và B (350 bài ICCV 2023), chỉ lấy bài main conference. Cả nhóm dựng một graph Neo4j gồm 8 loại nút và 10 loại quan hệ có bằng chứng. Mốc nghiệm thu là ít nhất 2.000 nút và 5.000 cạnh duy nhất.

| Đường dẫn | Dùng để làm gì |
| --- | --- |
| `src/collect/`, `src/clean/` | Collector chung, ghép bản ghi nguồn và chuẩn hóa Paper, Author, Institution. |
| `src/nlp/`, `config/` | Rule Task và Dataset (A), Method (B), từ điển dùng chung, phạm vi lấy mẫu và hợp đồng dữ liệu. |
| `src/graph/`, `queries/` | Sinh nút/cạnh, nạp Neo4j, lưu ràng buộc và truy vấn Cypher (B). |
| `src/analysis/`, `outputs/` | Phân tích NetworkX từ Neo4j, bảng chỉ số, biểu đồ và hình case study (B). |
| `data/raw/cvpr2024/`, `data/raw/iccv2023/` | Snapshot nguồn và manifest riêng cho mỗi hội nghị. Dữ liệu thô nằm ngoài Git. |
| `data/paper_registry.csv` | Vị trí registry chung do A tạo. Ghi URL/ID, hội nghị, trạng thái và owner của từng bài. |
| `data/processed/` | Dữ liệu chuẩn hóa dùng chung, gồm source records, papers/authorships, nodes/edges/evidence, alias map, merge log và needs review. Phân biệt Paper core và reference theo hợp đồng dữ liệu. |
| `quality/`, `quality/checks/` | Mẫu audit và các kiểm tra định danh, chất lượng cạnh, nhập lại Neo4j. |
| `report/` | Báo cáo nhóm, tài liệu tham khảo và bản nộp. |

## Bắt đầu pilot

1. Tạo repo GitHub chung từ thư mục này. B sao chép `.env.example` thành `.env` và điền thông tin Neo4j cục bộ khi đã có database.
2. A và B chốt schema, ID và trường của registry trong `config/data_contract.md`. A tạo registry và collector chung.
3. A đăng ký 30 bài CVPR 2024. B đăng ký 30 bài ICCV 2023 với `owner=B` và thử nạp vào Neo4j.
4. Chạy đủ 60 bài từ raw qua clean/NLP tới Neo4j. Kiểm tra ghép ID, dữ liệu thiếu và số nút/cạnh trước khi thu hàng loạt 350 bài mỗi người.

Thư mục này là bộ khung. Khi chạy pilot, cập nhật README với các lệnh chạy thực tế, cách lấy snapshot nguồn và các phiên bản đã kiểm tra trong `requirements.txt`.
