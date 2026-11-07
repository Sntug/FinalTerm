# Danh mục trường v2

Mỗi key/cột đều bắt buộc có mặt; cột Nullable chỉ cho phép giá trị null. Array/object trong CSV được mã hóa bằng JSON. Kiểm tra điều kiện theo loại bằng chứng và khóa ngoại theo DATA_CONTRACT.md.

## paper_registry.csv

Khóa logic: `paper_id`. Giai đoạn: metadata.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| paper_id | string | Không |  |
| doi | string | Có |  |
| cvf_url | string | Không |  |
| conference | string | Không |  |
| conference_year | integer | Không |  |
| owner | string | Không |  |
| status | string | Không | registered, cvf_verified, needs_review, excluded |
| schema_version | string | Không | 2.0.0 |
| track | string | Không |  |
| scope | string | Không |  |
| venue_id | string | Không |  |
| title | string | Không |  |
| selection_rank | integer | Không |  |
| source_record_id | string | Không |  |
| verified_at | string | Không |  |

## papers.jsonl

Khóa logic: `paper_id`. Giai đoạn: metadata.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| schema_version | string | Không | 2.0.0 |
| paper_id | string | Không |  |
| owner | string | Không |  |
| scope | string | Không |  |
| track | string | Không |  |
| conference | string | Không |  |
| conference_year | integer | Không |  |
| venue_id | string | Không |  |
| title | string | Không |  |
| abstract | string | Có |  |
| doi | string | Có |  |
| cvf_url | string | Không |  |
| pdf_url | string | Có |  |
| arxiv_url | string | Có |  |
| publication_date | string | Không |  |
| date_precision | string | Không |  |
| authors | array | Không |  |
| title_text_version_id | string | Không |  |
| abstract_text_version_id | string | Có |  |
| openalex_id | string | Có |  |
| openalex_status | string | Không | not_collected, matched, not_found, needs_review |
| citation_count | integer | Có |  |
| citation_count_source_record_id | string | Có |  |
| citation_count_observed_at | string | Có |  |
| referenced_works | array | Có |  |
| references_status | string | Không | not_collected, verified, missing_in_source, needs_review |
| representative_source_record_id | string | Không |  |

## source_records.jsonl

Khóa logic: `source_record_id`. Giai đoạn: metadata.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| schema_version | string | Không | 2.0.0 |
| source_record_id | string | Không |  |
| paper_id | string | Có |  |
| source | string | Không |  |
| source_kind | string | Không |  |
| source_id | string | Không |  |
| source_version | string | Có |  |
| url | string | Không |  |
| fetched_at | string | Không |  |
| http_status | integer | Không |  |
| content_sha256 | string | Không |  |
| content_type | string | Không |  |
| etag | string | Có |  |
| last_modified | string | Có |  |
| raw_path | string | Không |  |

## authorships.csv

Khóa logic: `authorship_id, institution_id`. Giai đoạn: metadata.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| authorship_id | string | Không |  |
| paper_id | string | Không |  |
| author_id | string | Có |  |
| author_name | string | Không |  |
| author_name_raw | string | Không |  |
| author_order | integer | Không |  |
| identity_status | string | Không | unresolved, resolved, needs_review |
| affiliation_raw | string | Có |  |
| institution_id | string | Có |  |
| source_record_id | string | Không |  |
| owner | string | Không |  |
| identity_source_record_id | string | Có |  |
| affiliation_source_record_id | string | Có |  |
| affiliation_status | string | Không | not_collected, verified, missing_in_source, needs_review |
| decision_ids | array | Không |  |

## text_versions.jsonl

Khóa logic: `text_version_id`. Giai đoạn: metadata.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| text_version_id | string | Không |  |
| paper_id | string | Không |  |
| source_record_id | string | Không |  |
| field_path | string | Không |  |
| parser_version | string | Không |  |
| normalization_version | string | Không |  |
| normalized_text | string | Không |  |
| normalized_text_sha256 | string | Không |  |
| captured_at | string | Không |  |

## field_provenance.csv

Khóa logic: `paper_id, field_name`. Giai đoạn: metadata.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| paper_id | string | Không |  |
| field_name | string | Không |  |
| source_record_id | string | Không |  |
| field_path | string | Không |  |
| selection_rule | string | Không |  |
| validation_status | string | Không | auto_verified, verified, needs_review |
| reviewed_by | string | Có |  |
| selected_at | string | Không |  |
| candidate_source_record_ids | array | Không |  |

## alias_map.csv

Khóa logic: `alias_id`. Giai đoạn: identity.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| alias_id | string | Không |  |
| entity_type | string | Không |  |
| source | string | Không |  |
| external_id | string | Không |  |
| canonical_id | string | Không |  |
| decision_id | string | Không |  |

## merge_log.jsonl

Khóa logic: `decision_id`. Giai đoạn: identity.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| decision_id | string | Không |  |
| action | string | Không | link, unlink, merge, split, retract |
| entity_type | string | Không |  |
| input_ids | array | Không |  |
| output_ids | array | Không |  |
| affected_paper_ids | array | Không |  |
| affected_authorship_ids | array | Không |  |
| changes | array | Không |  |
| reason | string | Không |  |
| evidence_ids | array | Không |  |
| proposed_by | string | Không |  |
| reviewed_by | string | Không |  |
| review_mode | string | Không | manual, rule |
| decided_at | string | Không |  |
| snapshot_before | string | Có |  |
| reverts_decision_id | string | Có |  |

## needs_review.csv

Khóa logic: `review_id`. Giai đoạn: review.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| review_id | string | Không |  |
| paper_id | string | Có |  |
| entity_type | string | Không |  |
| entity_id | string | Có |  |
| field_name | string | Có |  |
| reason | string | Không |  |
| candidate_ids | array | Không |  |
| evidence_ids | array | Không |  |
| review_status | string | Không | open, resolved, rejected |
| assigned_to | string | Có |  |
| resolution_decision_id | string | Có |  |

## nodes.csv

Khóa logic: `project_id, id`. Giai đoạn: graph.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| id | string | Không |  |
| label | string | Không | Author, Paper, Institution, VenueEdition, Task, Method, Dataset, Country |
| name | string | Không |  |
| owner | string | Không |  |
| source_origin | array | Không |  |
| source_record_ids | array | Không |  |
| validation_status | string | Không | accepted, needs_review, rejected |
| project_id | string | Không |  |
| properties_json | object | Không |  |

## edges.csv

Khóa logic: `project_id, edge_id`. Giai đoạn: graph.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| edge_id | string | Không |  |
| src | string | Không |  |
| dst | string | Không |  |
| type | string | Không | AUTHORED, AFFILIATED_WITH, PUBLISHED_IN, CITES, BASED_IN, COAUTHORED_WITH, COLLABORATED_WITH, STUDIES_TASK, USES_METHOD, EVALUATED_ON |
| weight | integer | Không |  |
| derivation | string | Không | metadata, derived, nlp |
| validation_status | string | Không | accepted, needs_review, rejected |
| evidence_ids | array | Không |  |
| paper_ids | array | Không |  |
| owner | string | Không |  |
| source_origin | array | Không |  |
| project_id | string | Không |  |

## evidence.jsonl

Khóa logic: `evidence_id`. Giai đoạn: graph.

| Trường | Kiểu JSON sau giải mã CSV | Nullable | Giá trị cố định hoặc enum |
|---|---|---|---|
| evidence_id | string | Không |  |
| evidence_kind | string | Không | metadata, derived, nlp |
| paper_id | string | Có |  |
| source_record_id | string | Có |  |
| source_url | string | Có |  |
| field_path | string | Có |  |
| evidence_text | string | Có |  |
| start_char | integer | Có |  |
| end_char | integer | Có |  |
| rule_id | string | Không |  |
| rule_version | string | Không |  |
| captured_at | string | Không |  |
| supporting_evidence_ids | array | Không |  |
| owner | string | Không |  |
| text_version_id | string | Có |  |
| normalized_text_sha256 | string | Có |  |
| normalization_version | string | Có |  |
