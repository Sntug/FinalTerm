"""Validate the pilot against snapshots and the v1 contract, entirely offline."""
from __future__ import annotations

import argparse
import gzip
import json
import re
from collections import Counter
from pathlib import Path

from src.collect.__main__ import check_b_input
from src.collect.cvf import parse_detail, parse_listing, rank_urls
from src.common import (
    AUTHORSHIP_FIELDS, METADATA_FIELDS, REGISTRY_FIELDS, SCHEMA_VERSION, digest,
    paper_id_from_url, read_csv, read_jsonl, stable_id, venue_id, write_json,
)


def validate_json(value: object, schema: dict, path: str = "$") -> list[str]:
    """Validate the types/constraints used by paper.schema.json, with no dependency.

    This is deliberately a documented subset, not a general JSON Schema engine.
    The delivered schema is also consumable by standard Draft 2020-12 validators.
    """
    errors = []
    types = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
             "string": lambda v: isinstance(v, str), "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
             "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
             "boolean": lambda v: isinstance(v, bool), "null": lambda v: v is None}
    expected = schema.get("type")
    if expected and not any(types[t](value) for t in (expected if isinstance(expected, list) else [expected])):
        return [f"{path}: expected {expected}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: outside enum")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                errors.extend(validate_json(item, props[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: unexpected property")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: too few items")
        for index, item in enumerate(value):
            errors.extend(validate_json(item, schema.get("items", {}), f"{path}[{index}]"))
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: too short")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: invalid pattern")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
    return errors


def audit(root: Path) -> dict:
    checks = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    registry_fields, registry = read_csv(root / "data/processed/paper_registry.csv")
    metadata_fields, metadata = read_csv(root / "data/processed/paper_metadata.csv")
    author_fields, authorships = read_csv(root / "data/processed/authorships.csv")
    papers = read_jsonl(root / "data/raw/pilot_papers.jsonl")
    sources = read_jsonl(root / "data/raw/source_records.jsonl")
    manifest = json.loads((root / "data/processed/selection_manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "outputs/pilot_summary.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "schemas/paper.schema.json").read_text(encoding="utf-8"))
    contract = json.loads((root / "schemas/data_contract.json").read_text(encoding="utf-8"))
    check("registry_header", registry_fields == REGISTRY_FIELDS)
    check("metadata_header", metadata_fields == METADATA_FIELDS)
    check("authorship_header", author_fields == AUTHORSHIP_FIELDS)
    check("contract_version", contract["schema_version"] == SCHEMA_VERSION)
    check("contract_registry_header", [f["name"] for f in contract["files"]["paper_registry.csv"]["fields"]] == REGISTRY_FIELDS)
    check("counts_30_plus_30", len(papers) == len(registry) == 60 and Counter(p["owner"] for p in papers) == {"A": 30, "B": 30})
    for label, values in [("paper_ids", [p["paper_id"] for p in papers]),
                          ("registry_ids", [p["paper_id"] for p in registry]),
                          ("cvf_urls", [p["cvf_url"] for p in papers]),
                          ("source_ids", [s["source_record_id"] for s in sources]),
                          ("authorship_ids", [a["authorship_id"] for a in authorships])]:
        check("unique_" + label, len(values) == len(set(values)))
    check("registry_paper_foreign_keys", {r["paper_id"] for r in registry} == {p["paper_id"] for p in papers})
    check("metadata_paper_foreign_keys", len(metadata) == 60 and {r["paper_id"] for r in metadata} == {p["paper_id"] for p in papers})
    by_source = {s["source_record_id"]: s for s in sources}
    by_registry = {r["paper_id"]: r for r in registry}
    by_metadata = {r["paper_id"]: r for r in metadata}
    b_fields, b_rows = read_csv(root / "data/input/b_iccv2023_pilot_registry.csv")
    check("B_original_structural_validation", not check_b_input(b_fields, b_rows, 30))
    check("B_original_bytes_preserved", digest((root / "data/input/b_iccv2023_pilot_registry.csv").read_bytes()) == manifest["b_input_sha256"])
    check("config_bytes_preserved", digest((root / "config/project.json").read_bytes()) == manifest["config_sha256"])
    check("B_ids_and_order_preserved", [r["paper_id"] for r in b_rows] == [r["paper_id"] for r in registry if r["owner"] == "B"])
    schema_errors = []
    for index, paper in enumerate(papers):
        schema_errors.extend(validate_json(paper, schema, f"papers[{index}]"))
    check("paper_JSON_schema_subset", not schema_errors, schema_errors)
    raw_bodies = {}
    for source in sources:
        sid = source["source_record_id"]
        body = gzip.decompress((root / source["raw_path"]).read_bytes())
        raw_bodies[sid] = body
        check("snapshot_sha256:" + sid, digest(body) == source["content_sha256"])
        check("stable_source_id:" + sid, sid == stable_id("source:cvf", source["url"], source["content_sha256"]))
    check("source_record_count", len(sources) == 62 and sum(s["source_kind"] == "listing" for s in sources) == 2)
    for corpus in manifest["corpora"]:
        owner = corpus["owner"]
        urls = parse_listing(raw_bodies[corpus["listing_source_record_id"]], corpus["conference"], corpus["conference_year"])
        selected = [p for p in papers if p["owner"] == owner]
        check(f"{owner}_official_listing_membership", all(p["cvf_url"] in urls for p in selected))
        check(f"{owner}_candidate_count", len(urls) == corpus["candidate_count"])
        check(f"{owner}_manifest_order", [p["paper_id"] for p in selected] == corpus["selected_paper_ids"])
        if owner == "A":
            check("A_seeded_selection_reproduced", [p["cvf_url"] for p in selected] == rank_urls(urls, manifest["seed"])[:30])
    paper_errors, author_errors = [], []
    for paper in papers:
        pid = paper["paper_id"]
        source = by_source.get(paper["source_record_id"])
        reg = by_registry[pid]
        if not source or source["paper_id"] != pid or source["url"] != paper["cvf_url"]:
            paper_errors.append(pid + ": invalid source foreign key")
            continue
        expected = parse_detail(raw_bodies[source["source_record_id"]], paper["cvf_url"], paper["conference"], paper["conference_year"])
        if any(paper[key] != value for key, value in expected.items()):
            paper_errors.append(pid + ": parsed data differs from raw snapshot")
        if pid != paper_id_from_url(paper["cvf_url"]) or paper["venue_id"] != venue_id(paper["conference"], paper["conference_year"]):
            paper_errors.append(pid + ": invalid paper/venue ID")
        if (paper["conference"], paper["conference_year"]) != ({"A": ("CVPR", 2024), "B": ("ICCV", 2023)}[paper["owner"]]):
            paper_errors.append(pid + ": owner/edition mismatch")
        if reg["title"] != paper["title"] or reg["doi"] != (paper["doi"] or "") or reg["status"] != "cvf_verified":
            paper_errors.append(pid + ": registry metadata mismatch")
        flat = by_metadata[pid]
        if flat["abstract"] != (paper["abstract"] or "") or int(flat["author_count"]) != len(paper["authors"]):
            paper_errors.append(pid + ": flat metadata mismatch")
        observations = [a for a in authorships if a["paper_id"] == pid]
        if len(observations) != len(paper["authors"]):
            author_errors.append(pid + ": wrong number of authorship observations")
        for author, observation in zip(paper["authors"], observations):
            order = author["author_order"]
            if (int(observation["author_order"]) != order or observation["author_name_raw"] != author["name_raw"]
                    or observation["authorship_id"] != stable_id("authorship", pid, str(order))
                    or observation["source_record_id"] != paper["source_record_id"]
                    or observation["author_id"] or observation["institution_id"]
                    or observation["identity_status"] != "unresolved"):
                author_errors.append(pid + ": invalid author observation")
    check("paper_metadata_matches_original_snapshots", not paper_errors, paper_errors)
    check("authorship_order_names_and_unresolved_identity", not author_errors, author_errors)
    check("authorship_foreign_keys", all(a["paper_id"] in by_registry and a["source_record_id"] in by_source for a in authorships))
    check("authorship_total", len(authorships) == sum(len(p["authors"]) for p in papers) == summary["counts"]["authorship_observations"])
    check("no_cross_corpus_paper_overlap", not ({p["paper_id"] for p in papers if p["owner"] == "A"} & {p["paper_id"] for p in papers if p["owner"] == "B"}))
    snapshot_id = stable_id("snapshot", manifest["b_input_sha256"], manifest["config_sha256"], *sorted(s["source_record_id"] for s in sources))
    check("snapshot_id", summary["snapshot_id"] == snapshot_id)
    from src.collect.__main__ import coverage
    check("coverage_summary_recomputed", summary["coverage"] == coverage(papers))
    outcome = {"schema_version": SCHEMA_VERSION, "snapshot_id": snapshot_id,
               "passed": all(c["passed"] for c in checks), "check_count": len(checks),
               "failure_count": sum(not c["passed"] for c in checks), "checks": checks}
    write_json(root / "outputs/quality_checks.json", outcome)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = audit(args.root.resolve())
    except (KeyError, ValueError, OSError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(f"Checks: {result['check_count']}; failures: {result['failure_count']}")
    if not result["passed"]:
        parser.exit(1, "FAILED: see outputs/quality_checks.json\n")


if __name__ == "__main__":
    main()
