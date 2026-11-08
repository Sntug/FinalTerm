# B3 — Exporter và loader Neo4j (project `mxh_cv_700`)

## Chạy
```sh
# 1. Xuất snapshot gộp CVPR 2024 (A) + ICCV 2023 (B) -> data/processed/mxh_cv_700/graph/
/opt/homebrew/bin/python3.12 -B -X utf8 -m src.graph.export_graph
# 2. Nạp vào Neo4j (cần driver `neo4j`: hiện chỉ có trong .venv, Python 3.9)
.venv/bin/python -B -X utf8 -m src.graph.load_neo4j --snapshot data/processed/mxh_cv_700/graph
# 3. Test (test Neo4j tự skip nếu không có driver/server)
.venv/bin/python -B -X utf8 -W ignore -m unittest src.graph.test_export_graph src.graph.test_load_neo4j -v
```
Mật khẩu đọc từ `.env` (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`); mặc định `bolt://127.0.0.1:17687`.

## Tệp
- `config/b_graph_700.json`: đường dẫn input (snapshot A2/full và A3 của hai nhóm).
- `export_graph.py`: chỉ giữ node/cạnh `accepted`; gộp Author/Institution trùng id (union alias/nguồn, owner `A|B`, xung đột scalar giữ giá trị của A); tạo Paper (registry `cvf_verified`), VenueEdition, Country và 5 loại cạnh AUTHORED, AFFILIATED_WITH, PUBLISHED_IN, BASED_IN, CITES. Đầu ra giống hệt byte khi chạy lại (`created_at` = timestamp lớn nhất của manifest input).
- `load_neo4j.py`: từ chối nếu `graph_ready` != true, sai project_id, sai nhãn/loại, sai sha256; tạo ràng buộc `(project_id,id)` ngoài transaction; trong MỘT write transaction: kiểm tra liên kết chéo project, xóa phạm vi project, nạp node rồi cạnh, kiểm tra count + content hash, lỗi thì rollback. `last_import.json` (`outputs/b_iccv2023/graph/`) chỉ ghi sau commit.
- `test_export_graph.py`, `test_load_neo4j.py`: kiểm thử dedupe, endpoint assert, nhập lặp, sửa affiliation, rollback giữa chừng, từ chối manifest xấu (project test `mxh_cv_700_test`, tự dọn).

## Quy ước
- `BASED_IN.paper_ids` = các bài có affiliation verified dùng institution đó; `[]` nếu không có.
- `evidence_ids` = evidence có (paper_id, source_record_id) khớp nguồn identity/affiliation của authorship, hoặc nguồn đại diện (và nguồn OpenAlex cho CITES); có thể rỗng.

## Giới hạn đã biết
- CITES chỉ giữa 700 bài core (không có node reference-scope).
- Authorship chưa resolve / thiếu author_id không tạo Author hay cạnh; affiliation không `verified` không tạo AFFILIATED_WITH.
- 29 bài CVPR có referenced_works rỗng/null (dự kiến 22) nên không có cạnh CITES đi ra.
- Neo4j pilot cũ (`b_pilot.py`: 30 Paper + 1 VenueEdition, thuộc tính `pilot`, ràng buộc `b_pilot_paper_id` / `b_pilot_venue_id` trên `id`) xung đột id với graph mới; phải xóa pilot cũ trước khi nạp lần đầu (xem báo cáo).
