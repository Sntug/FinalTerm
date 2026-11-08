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
