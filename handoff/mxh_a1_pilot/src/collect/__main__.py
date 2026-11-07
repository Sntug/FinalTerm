"""Run A1 and audit the supplied B registry: python -m src.collect [--offline]."""
from __future__ import annotations

import argparse
import json
import platform
from collections import Counter
from pathlib import Path

from src.collect.cvf import HTTPCache, parse_detail, parse_listing, rank_urls, source_record
from src.common import (
    AUTHORSHIP_FIELDS, METADATA_FIELDS, ORIGINAL_FIELDS, REGISTRY_FIELDS, SCHEMA_VERSION,
    canonical_cvf_url, digest, paper_id_from_url, read_csv, stable_id, venue_id,
    write_csv, write_json, write_jsonl,
)


def check_b_input(fields: list[str], rows: list[dict], expected_count: int) -> list[dict]:
    issues = []
    missing = set(ORIGINAL_FIELDS) - set(fields)
    if missing:
        issues.append({"row": 1, "field": "header", "reason": "missing: " + ", ".join(sorted(missing))})
        return issues
    if len(rows) != expected_count:
        issues.append({"row": 0, "field": "row_count", "reason": f"expected {expected_count}, got {len(rows)}"})
    ids, urls = set(), set()
    for row_number, row in enumerate(rows, 2):
        try:
            url = canonical_cvf_url(row["cvf_url"])
            if "/content/ICCV2023/" not in url:
                raise ValueError("Wrong edition for B")
            if row["paper_id"] != paper_id_from_url(url):
                raise ValueError("paper_id does not match CVF URL")
            if row["conference"] != "ICCV" or row["conference_year"] != "2023" or row["owner"] != "B":
                raise ValueError("Expected ICCV / 2023 / B")
            if not row["status"]:
                raise ValueError("Missing status")
            if row["paper_id"] in ids or url in urls:
                raise ValueError("Duplicate paper_id or canonical URL")
            ids.add(row["paper_id"])
            urls.add(url)
        except (KeyError, ValueError) as exc:
            issues.append({"row": row_number, "field": "registry", "reason": str(exc)})
    return issues


def coverage(papers: list[dict]) -> list[dict]:
    fields = ["title", "authors", "abstract", "doi", "pdf_url", "arxiv_url", "publication_date",
              "openalex_id", "affiliations", "referenced_works", "citation_count"]
    rows = []
    for owner in ("A", "B"):
        subset = [paper for paper in papers if paper["owner"] == owner]
        for field in fields:
            present = sum(paper[field] is not None and paper[field] != "" and paper[field] != [] for paper in subset)
            missing_kind = "not_collected_in_A1" if field in {"openalex_id", "affiliations", "referenced_works", "citation_count"} else "not_present_in_CVF_html"
            rows.append({"owner": owner, "field": field, "total": len(subset), "present": present,
                         "missing": len(subset) - present, "coverage_pct": round(100 * present / len(subset), 2),
                         "missing_interpretation": missing_kind})
    return rows


def run(root: Path, config_path: Path, offline: bool = False) -> dict:
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    count = config["pilot_count_per_owner"]
    if count != 30:
        raise ValueError("A1 is a fixed 30+30 pilot. Expand the manifest explicitly in A2.")
    b_path = root / config["b_input"]
    fields, b_rows = read_csv(b_path)
    b_issues = check_b_input(fields, b_rows, count)
    if b_issues:
        write_json(root / "outputs/b_input_errors.json", b_issues)
        raise ValueError("B input failed structural checks; see outputs/b_input_errors.json")
    cache = HTTPCache(root, offline=offline, delay=config["delay_seconds"])
    registries, papers, sources, authorships, b_audit = [], [], [], [], []
    manifest = {
        "schema_version": SCHEMA_VERSION, "seed": config["seed"],
        "selection_algorithm": "sha256(seed + newline + canonical_url), ascending, then URL",
        "b_input_sha256": digest(b_path.read_bytes()), "config_sha256": digest(config_bytes),
        "corpora": [],
    }
    for corpus in config["corpora"]:
        owner, conference, year = corpus["owner"], corpus["conference"], corpus["conference_year"]
        listing_body, listing_meta = cache.get(corpus["listing_url"])
        listing_source = source_record(listing_meta, None, "listing")
        sources.append(listing_source)
        all_urls = parse_listing(listing_body, conference, year)
        if owner == "A":
            selected = rank_urls(all_urls, config["seed"])[:count]
            selection_method = "seeded_sha256_rank"
        else:
            selected = [canonical_cvf_url(row["cvf_url"]) for row in b_rows]
            selection_method = "provided_B_manifest_preserved"
        if len(selected) != count:
            raise ValueError("Insufficient selected papers")
        not_in_listing = set(selected) - set(all_urls)
        if not_in_listing:
            raise ValueError("Selected papers absent from the official main-conference listing: " + repr(sorted(not_in_listing)))
        manifest["corpora"].append({
            **corpus, "candidate_count": len(all_urls), "selected_count": len(selected),
            "selection_method": selection_method,
            "selection_seed": config["seed"] if owner == "A" else None,
            "listing_source_record_id": listing_source["source_record_id"],
            "selected_paper_ids": [paper_id_from_url(url) for url in selected],
        })
        for rank, url in enumerate(selected, 1):
            body, meta = cache.get(url)
            paper_id = paper_id_from_url(url)
            source = source_record(meta, paper_id, "paper_detail")
            parsed = parse_detail(body, url, conference, year)
            if owner == "B" and b_rows[rank - 1]["doi"] and b_rows[rank - 1]["doi"].lower() != (parsed["doi"] or "").lower():
                raise ValueError("B DOI disagrees with CVF or requires verification; do not silently overwrite")
            paper = {
                **parsed, "paper_id": paper_id, "conference": conference, "conference_year": year,
                "owner": owner, "track": "main", "scope": "core", "venue_id": venue_id(conference, year),
                "source_record_id": source["source_record_id"], "captured_at": meta["fetched_at"],
            }
            row = {
                "paper_id": paper_id, "doi": parsed["doi"], "cvf_url": url,
                "conference": conference, "conference_year": year, "owner": owner,
                "status": "cvf_verified", "schema_version": SCHEMA_VERSION,
                "track": "main", "scope": "core", "venue_id": paper["venue_id"],
                "title": parsed["title"], "selection_rank": rank,
                "source_record_id": source["source_record_id"], "verified_at": meta["fetched_at"],
            }
            papers.append(paper)
            registries.append(row)
            sources.append(source)
            for author in parsed["authors"]:
                authorships.append({
                    "authorship_id": stable_id("authorship", paper_id, str(author["author_order"])),
                    "paper_id": paper_id, "author_id": None, "author_name": author["name"],
                    "author_name_raw": author["name_raw"], "author_order": author["author_order"],
                    "identity_status": "unresolved", "affiliation_raw": None, "institution_id": None,
                    "source_record_id": source["source_record_id"], "owner": owner,
                })
            if owner == "B":
                warnings = ["original_file_is_registry_only", "selection_seed_not_supplied",
                            "author_identity_not_resolved", "affiliations_and_references_not_collected"]
                if not parsed["doi"]:
                    warnings.append("doi_not_in_CVF_html_optional")
                if not parsed["abstract"]:
                    warnings.append("abstract_missing_in_CVF_html")
                b_audit.append({
                    "input_row": rank + 1, "paper_id": paper_id, "cvf_url": url,
                    "id_matches_url": True, "in_official_main_listing": True,
                    "http_status": source["http_status"], "conference_metadata_matches": True,
                    "title": parsed["title"], "author_count": len(parsed["authors"]),
                    "abstract_present": bool(parsed["abstract"]), "doi_present": bool(parsed["doi"]),
                    "original_status": b_rows[rank - 1]["status"], "review_status": "cvf_metadata_verified",
                    "warnings_json": json.dumps(warnings, ensure_ascii=False),
                })
            print(f"{owner} {rank:02d}/{count}: {parsed['title']}", flush=True)
    registry_path = root / "data/processed/paper_registry.csv"
    write_csv(registry_path, REGISTRY_FIELDS, registries)
    for owner in ("A", "B"):
        filename = "a_cvpr2024_pilot_registry.csv" if owner == "A" else "b_iccv2023_pilot_registry_v1.csv"
        write_csv(root / "data/processed" / filename, REGISTRY_FIELDS, [row for row in registries if row["owner"] == owner])
        filename = "a_cvpr2024_pilot_papers.jsonl" if owner == "A" else "b_iccv2023_pilot_papers.jsonl"
        write_jsonl(root / "data/raw" / filename, [paper for paper in papers if paper["owner"] == owner])
    write_jsonl(root / "data/raw/pilot_papers.jsonl", papers)
    write_jsonl(root / "data/raw/source_records.jsonl", sources)
    write_csv(root / "data/processed/authorships.csv", AUTHORSHIP_FIELDS, authorships)
    flat = []
    for paper in papers:
        row = {field: paper.get(field) for field in METADATA_FIELDS}
        row["author_count"] = len(paper["authors"])
        row["authors_json"] = json.dumps([author["name"] for author in paper["authors"]], ensure_ascii=False)
        flat.append(row)
    write_csv(root / "data/processed/paper_metadata.csv", METADATA_FIELDS, flat)
    coverage_rows = coverage(papers)
    write_csv(root / "outputs/field_coverage.csv", list(coverage_rows[0]), coverage_rows)
    write_csv(root / "outputs/b_registry_review.csv", list(b_audit[0]), b_audit)
    write_json(root / "data/processed/selection_manifest.json", manifest)
    # Snapshot identity derives from the raw source IDs and immutable original input.
    snapshot_id = stable_id("snapshot", manifest["b_input_sha256"], manifest["config_sha256"],
                            *sorted(source["source_record_id"] for source in sources))
    summary = {
        "schema_version": SCHEMA_VERSION, "snapshot_id": snapshot_id,
        "counts": {"A_papers": sum(p["owner"] == "A" for p in papers),
                   "B_papers": sum(p["owner"] == "B" for p in papers),
                   "papers": len(papers), "source_records": len(sources),
                   "authorship_observations": len(authorships),
                   "A_authorship_observations": sum(a["owner"] == "A" for a in authorships),
                   "B_authorship_observations": sum(a["owner"] == "B" for a in authorships)},
        "coverage": coverage_rows,
        "publication_date_precision": dict(Counter(p["date_precision"] for p in papers)),
        "b_review": {"input_rows": len(b_rows), "structural_errors": len(b_issues),
                     "verified_against_listing_and_detail": len(b_audit),
                     "original_file_has_paper_metadata": False,
                     "B1_repo_setup_verified": False, "B1_neo4j_verified": False,
                     "B1_complete_from_supplied_evidence": False},
        "scope": {"A1_completed": True, "openalex_enrichment_executed": False,
                  "nlp_executed": False, "neo4j_import_executed": False,
                  "graph_size_measured": False, "author_identity_resolved": False},
    }
    write_json(root / "outputs/pilot_summary.json", summary)
    write_json(root / "outputs/runtime.json", {"python": platform.python_version(), "implementation": platform.python_implementation(),
                                               "platform": platform.platform(), "third_party_runtime_dependencies": [],
                                               "note": "A1 uses Python standard library. Plan target: Python 3.12+."})
    from src.quality.report import write_report
    write_report(root, summary, manifest)
    print(f"Wrote {len(papers)} papers; network requests this run: {cache.network_requests}", flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("config/project.json"))
    parser.add_argument("--offline", action="store_true", help="Require saved snapshots; never access the network")
    args = parser.parse_args()
    root = args.root.resolve()
    config = args.config if args.config.is_absolute() else root / args.config
    try:
        run(root, config, offline=args.offline)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
