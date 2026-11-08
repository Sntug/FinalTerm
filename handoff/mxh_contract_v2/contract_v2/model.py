"""Authoritative field order and field types for the shared v2 contract."""
from __future__ import annotations

import json
from pathlib import Path

VERSION = "2.0.0"
REGISTRY = "paper_id doi cvf_url conference conference_year owner status schema_version track scope venue_id title selection_rank source_record_id verified_at".split()
AUTHORSHIPS = "authorship_id paper_id author_id author_name author_name_raw author_order identity_status affiliation_raw institution_id source_record_id owner identity_source_record_id affiliation_source_record_id affiliation_status decision_ids".split()
SOURCES = "schema_version source_record_id paper_id source source_kind source_id source_version url fetched_at http_status content_sha256 content_type etag last_modified raw_path".split()
PAPERS = "schema_version paper_id owner scope track conference conference_year venue_id title abstract doi cvf_url pdf_url arxiv_url publication_date date_precision authors title_text_version_id abstract_text_version_id openalex_id openalex_status citation_count citation_count_source_record_id citation_count_observed_at referenced_works references_status representative_source_record_id".split()
TEXTS = "text_version_id paper_id source_record_id field_path parser_version normalization_version normalized_text normalized_text_sha256 captured_at".split()
PROVENANCE = "paper_id field_name source_record_id field_path selection_rule validation_status reviewed_by selected_at candidate_source_record_ids".split()
NODES = "id label name owner source_origin source_record_ids validation_status project_id properties_json".split()
EDGES = "edge_id src dst type weight derivation validation_status evidence_ids paper_ids owner source_origin project_id".split()
EVIDENCE = "evidence_id evidence_kind paper_id source_record_id source_url field_path evidence_text start_char end_char rule_id rule_version captured_at supporting_evidence_ids owner text_version_id normalized_text_sha256 normalization_version".split()
ALIASES = "alias_id entity_type source external_id canonical_id decision_id".split()
MERGES = "decision_id action entity_type input_ids output_ids affected_paper_ids affected_authorship_ids changes reason evidence_ids proposed_by reviewed_by review_mode decided_at snapshot_before reverts_decision_id".split()
REVIEW = "review_id paper_id entity_type entity_id field_name reason candidate_ids evidence_ids review_status assigned_to resolution_decision_id".split()
LABELS = "Author Paper Institution VenueEdition Task Method Dataset Country".split()
NODE_PROPERTIES = {
    "Author": "openalex_id orcid aliases".split(),
    "Paper": "doi cvf_url abstract conference conference_year scope publication_date date_precision openalex_id title_text_version_id abstract_text_version_id citation_count citation_count_observed_at".split(),
    "Institution": "openalex_id ror country_code aliases".split(),
    "VenueEdition": "conference conference_year track".split(),
    "Task": "definition aliases".split(), "Method": "definition aliases".split(),
    "Dataset": "version aliases".split(), "Country": ["country_code"],
}
RELATIONS = [
    ("AUTHORED", "Author", "Paper", True),
    ("AFFILIATED_WITH", "Author", "Institution", True),
    ("PUBLISHED_IN", "Paper", "VenueEdition", True),
    ("CITES", "Paper", "Paper", True),
    ("BASED_IN", "Institution", "Country", True),
    ("COAUTHORED_WITH", "Author", "Author", False),
    ("COLLABORATED_WITH", "Institution", "Institution", False),
    ("STUDIES_TASK", "Paper", "Task", True),
    ("USES_METHOD", "Paper", "Method", True),
    ("EVALUATED_ON", "Paper", "Dataset", True),
]

FILES = {
    "paper_registry.csv": (REGISTRY, ["paper_id"], "metadata"),
    "papers.jsonl": (PAPERS, ["paper_id"], "metadata"),
    "source_records.jsonl": (SOURCES, ["source_record_id"], "metadata"),
    "authorships.csv": (AUTHORSHIPS, ["authorship_id", "institution_id"], "metadata"),
    "text_versions.jsonl": (TEXTS, ["text_version_id"], "metadata"),
    "field_provenance.csv": (PROVENANCE, ["paper_id", "field_name"], "metadata"),
    "alias_map.csv": (ALIASES, ["alias_id"], "identity"),
    "merge_log.jsonl": (MERGES, ["decision_id"], "identity"),
    "needs_review.csv": (REVIEW, ["review_id"], "review"),
    "nodes.csv": (NODES, ["project_id", "id"], "graph"),
    "edges.csv": (EDGES, ["project_id", "edge_id"], "graph"),
    "evidence.jsonl": (EVIDENCE, ["evidence_id"], "graph"),
}
ARRAYS = {"authors", "referenced_works", "decision_ids", "candidate_source_record_ids", "source_origin",
          "source_record_ids", "evidence_ids", "paper_ids", "supporting_evidence_ids", "input_ids", "output_ids",
          "affected_paper_ids", "affected_authorship_ids", "changes", "candidate_ids"}
INTS = {"conference_year", "selection_rank", "author_order", "http_status", "citation_count", "weight", "start_char", "end_char"}
NULLABLE = {
    "paper_registry.csv": {"doi"},
    "papers.jsonl": {"abstract", "doi", "pdf_url", "arxiv_url", "abstract_text_version_id", "openalex_id",
                      "citation_count", "citation_count_source_record_id", "citation_count_observed_at", "referenced_works"},
    "source_records.jsonl": {"paper_id", "source_version", "etag", "last_modified"},
    "authorships.csv": {"author_id", "affiliation_raw", "institution_id", "identity_source_record_id", "affiliation_source_record_id"},
    "field_provenance.csv": {"reviewed_by"},
    "evidence.jsonl": {"paper_id", "source_record_id", "source_url", "field_path", "evidence_text", "start_char", "end_char",
                       "text_version_id", "normalized_text_sha256", "normalization_version"},
    "merge_log.jsonl": {"snapshot_before", "reverts_decision_id"},
    "needs_review.csv": {"paper_id", "entity_id", "field_name", "assigned_to", "resolution_decision_id"},
}
ENUMS = {
    ("paper_registry.csv", "status"): ["registered", "cvf_verified", "needs_review", "excluded"],
    ("papers.jsonl", "openalex_status"): ["not_collected", "matched", "not_found", "needs_review"],
    ("papers.jsonl", "references_status"): ["not_collected", "verified", "missing_in_source", "needs_review"],
    ("authorships.csv", "identity_status"): ["unresolved", "resolved", "needs_review"],
    ("authorships.csv", "affiliation_status"): ["not_collected", "verified", "missing_in_source", "needs_review"],
    ("field_provenance.csv", "validation_status"): ["auto_verified", "verified", "needs_review"],
    ("nodes.csv", "validation_status"): ["accepted", "needs_review", "rejected"],
    ("edges.csv", "validation_status"): ["accepted", "needs_review", "rejected"],
    ("edges.csv", "type"): [r[0] for r in RELATIONS],
    ("nodes.csv", "label"): LABELS,
    ("edges.csv", "derivation"): ["metadata", "derived", "nlp"],
    ("evidence.jsonl", "evidence_kind"): ["metadata", "derived", "nlp"],
    ("merge_log.jsonl", "action"): ["link", "unlink", "merge", "split", "retract"],
    ("merge_log.jsonl", "review_mode"): ["manual", "rule"],
    ("needs_review.csv", "review_status"): ["open", "resolved", "rejected"],
}


def schema_for(filename: str) -> dict:
    properties = {}
    for name in FILES[filename][0]:
        kind = "object" if name == "properties_json" else "array" if name in ARRAYS else "integer" if name in INTS else "string"
        prop = {"type": [kind, "null"] if name in NULLABLE.get(filename, set()) else kind}
        if kind == "array":
            prop["items"] = {"type": "object"} if name in {"authors", "changes"} else {"type": "string"}
        if kind == "integer":
            prop["minimum"] = 1 if name in {"author_order", "selection_rank", "weight"} else 0
        if name == "schema_version": prop["const"] = VERSION
        if (filename, name) in ENUMS: prop["enum"] = ENUMS[(filename, name)]
        properties[name] = prop
    if "authors" in properties:
        properties["authors"]["minItems"] = 1
        properties["authors"]["items"] = {
            "type": "object", "additionalProperties": False,
            "required": ["authorship_id", "name", "name_raw", "author_order"],
            "properties": {"authorship_id": {"type": "string"}, "name": {"type": "string"},
                           "name_raw": {"type": "string"}, "author_order": {"type": "integer", "minimum": 1}},
        }
    if "changes" in properties:
        properties["changes"]["items"] = {
            "type": "object", "additionalProperties": False,
            "required": ["table", "record_key", "field", "before", "after"],
            "properties": {"table": {"type": "string"}, "record_key": {"type": "object"},
                           "field": {"type": "string"}, "before": {}, "after": {}},
        }
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": filename + " v2 decoded record", "type": "object", "additionalProperties": False,
            "required": FILES[filename][0], "properties": properties}


def contract() -> dict:
    return {
        "schema_version": VERSION, "project_id": "mxh_cv_700", "replaces": "1.0.0",
        "csv_policy": "UTF-8 BOM, comma, LF; nullable scalar blank; arrays encoded as compact JSON; header order fixed.",
        "record_policy": "All listed keys/columns required; nullable means value can be null, not that the column/key may be omitted.",
        "files": {name: {"fields": fields, "logical_unique_key": key, "stage": stage,
                         "nullable_fields": sorted(NULLABLE.get(name, set())),
                         "record_schema": name.replace(".", "_") + ".schema.json"}
                  for name, (fields, key, stage) in FILES.items()},
        "relations": [{"type": t, "src_label": s, "dst_label": d, "directed": directed} for t,s,d,directed in RELATIONS],
        "node_labels": LABELS,
        "node_properties": NODE_PROPERTIES,
        "node_property_policy": "properties_json is a CSV transport object, unpacked to whitelisted native scalar/list Neo4j properties; do not store a nested JSON object as a property. Null removes/omits a property; nested objects forbidden.",
        "normalization": {"version": "nfc-ws-1", "steps": ["Unicode NFC", "split and join whitespace with one U+0020"],
                          "hash": "SHA-256 of complete normalized field encoded UTF-8, not of a sentence excerpt."},
        "evidence_offsets": "Zero-based Unicode code points; [start_char,end_char), end exclusive; exact slice equals evidence_text.",
        "hash_names": {"content_sha256": "Original uncompressed source response bytes.",
                       "normalized_text_sha256": "Full normalized title or full normalized abstract.",
                       "graph_content_sha256": "Canonical active-node and active-edge records, not just counts."},
        "graph_update": "Rebuild full project scope from complete validated snapshot; delete+load in one write transaction; rollback on failure. No MERGE-only accumulation.",
        "graph_snapshot_tag": "snapshot_id is supplied by the manifest to the loader, not a CSV column or part of node/edge ID. This avoids self-referential snapshot hashing.",
        "status_namespaces": {name: {field: values for (table,field),values in ENUMS.items() if table==name}
                              for name in FILES if any(table==name for table,_ in ENUMS)},
        "version_policy": "Major for any breaking schema/ID/null/semantic change. Minor only after old readers/validators accept the optional addition. Patch for compatible fixes.",
        "snapshot_manifest": {
            "required": ["project_id", "snapshot_id", "schema_version", "source_snapshot_id", "created_at", "code_version", "normalization_version",
                         "parser_versions", "rule_versions", "dictionary_versions", "applied_decision_ids", "graph_ready", "node_count", "edge_count", "files"],
            "file_record": ["path", "sha256", "record_count", "role"],
            "graph_ready_false": "Metadata-only export; graph loader must refuse replacing the project from it.",
            "digest_rule": "snapshot:v2: + SHA256 of canonical JSON {project_id,schema_version,code_version,normalization_version,parser_versions,rule_versions,dictionary_versions,applied_decision_ids,graph_ready,node_count,edge_count,files}; excludes created_at, source_snapshot_id and snapshot_id.",
        },
    }


def emit(root: Path) -> None:
    schemas = root / "schemas"; schemas.mkdir(parents=True, exist_ok=True)
    (schemas / "data_contract.json").write_text(json.dumps(contract(), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for name in FILES:
        (schemas / (name.replace(".", "_") + ".schema.json")).write_text(json.dumps(schema_for(name), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    emit(Path.cwd())
