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

## Neo4j pilot cục bộ trên máy này

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
