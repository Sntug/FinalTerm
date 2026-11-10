# A6 — Review dữ liệu và kiểm tra chất lượng

Graph snapshot: `snapshot:v2:7494c3c9c055befc8a7b59e529674a25d5ff5ad99bb824315f4d2c98d71afb61`; seed `20261103`.

## Kiểm tra tự động

Required checks passed: True; execution complete: True.

- A: 350/350 Paper core hợp lệ; 1968 lượt authorship; 340 thiếu Author ID; 466 thiếu Institution ID.
- B: 350/350 Paper core hợp lệ; 1853 lượt authorship; 199 thiếu Author ID; 295 thiếu Institution ID.
- Graph: 4182 node, 16979 cạnh; 320 cạnh NLP, 335 evidence NLP được kiểm tra binding/offset.
- Finding kinds: `{"known_review":2594,"review_risk":177}`; confirmed automatic errors: 0.
- Known reviews và review risks chưa phải lỗi ngữ nghĩa đã được xác nhận. Không tự sửa B4/B5 hoặc dữ liệu nguồn; xem a6_review_issues.csv để lọc owner/severity/check_id.
- Phân loại issue: `{"citation_evidence_specificity":97,"existing_review":2594,"homonym":75,"nlp_context_risk":2,"shared_identifier":3}`.

| Kiểm tra | Trạng thái |
|---|---|
| load_corpus_A | passed |
| corpus_checks_A | passed |
| contract_corpus_A | passed |
| clean_replay_A | passed |
| metadata_replay_A | passed |
| load_corpus_B | passed |
| corpus_checks_B | passed |
| contract_corpus_B | passed |
| clean_replay_B | passed |
| load_graph | passed |
| contract_graph | passed |
| nlp_replay | passed |
| independent_graph_checks | passed |
| neo4j_counts | not_run |

neo4j_counts: Neo4j Python driver is not installed; CSV/contract checks still run offline.

## Mẫu và chấm độc lập

Primary/cross/node rows: 100/20/50.
Primary A/B: `{"A":50,"B":50}`. Chi tiết phân tầng:

| Quan hệ | Cạnh trong graph | Mẫu primary |
|---|---:|---:|
| AUTHORED | 3282 | 10 |
| AFFILIATED_WITH | 3237 | 10 |
| PUBLISHED_IN | 700 | 10 |
| CITES | 97 | 10 |
| BASED_IN | 432 | 10 |
| COAUTHORED_WITH | 7771 | 10 |
| COLLABORATED_WITH | 1140 | 10 |
| STUDIES_TASK | 97 | 10 |
| USES_METHOD | 195 | 10 |
| EVALUATED_ON | 28 | 10 |

Đã chấm primary: 0; còn pending: 100. Conservative precision: chưa có kết quả chấm.
Cross disagreements: 0; node pending: 50.
Unverifiable được tính là chưa đúng; pending_review không nằm trong mẫu số đã chấm. Cross rows không nhân đôi mẫu số precision primary. Không suy độ chính xác toàn graph >90% từ mẫu thử.

## Bàn giao

Mở a6_edge_audit_sample.csv và a6_node_audit_sample.csv bằng Excel/CSV editor. Lọc assigned_reviewer A/B, review_phase primary/cross; chỉ sửa review_status, error_group, review_notes, reviewer_name và reviewed_at (ISO 8601 có timezone).
review_status: correct / incorrect / unverifiable / pending_review. error_group: identity / affiliation / nlp_relation / citation / missing_evidence / time_or_version / other. Incorrect/unverifiable cần lý do; mọi dòng đã chấm cần tên người và thời điểm thật. Không sửa ID, assignment, evidence hoặc thêm/xóa dòng.
evidence_json trên phiếu cạnh chứa tối đa 3 bản ghi nguyên văn để phù hợp CSV/Excel; evidence_ids vẫn giữ toàn bộ. Đọc evidence.jsonl được manifest graph tham chiếu để kiểm tra tất cả nguồn, đặc biệt cạnh có nhiều Paper hỗ trợ.
Chạy `python -m src.audit summarize --config config/a6_audit.json` để tổng hợp sau khi A/B chấm. Lệnh này chỉ cập nhật báo cáo dẫn xuất, giữ nguyên phiếu chấm. Rerun `run` từ chối ghi đè phiếu đã sửa; snapshot/rule/config mới phải dùng output_dir mới.

A6 tự động hoàn tất: True; human audit hoàn tất: False.
A7 chỉ sẵn sàng sau khi các kiểm tra bắt buộc qua, A/B chấm và đọc chéo đủ, xử lý các kết quả incorrect/unverifiable/bất đồng và xác minh lại lỗi đã sửa. Hiện chưa tuyên bố đạt precision hoặc nghiệm thu toàn graph.
