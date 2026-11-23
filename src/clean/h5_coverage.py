"""Verify a CVPR H5 handoff and measure coverage on its locked sample."""
import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from src.collect.common import REPO_ROOT, json_bytes, load_config, load_selection, publish, within
from src.collect.contract import load_records
from src.collect.cvf import parse_detail
from src.collect.openalex import assessment
from .verify import verify


def fraction(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                percent=round(100 * numerator / denominator, 2) if denominator else None)


def match_basis(cvf, work):
    check = assessment(cvf, work)
    if not check["accepted"]:
        raise ValueError("Cannot reproduce matched OpenAlex Work from the source records")
    # Use the DOI observed on the CVF detail page. The finished paper may already
    # have a DOI copied from OpenAlex, which would make this comparison circular.
    venue_and_year = check["venue_match"] and check["year_equal"]
    conference_doi = check["doi_equal"] and not cvf["doi"].startswith("10.48550/arxiv.")
    if venue_and_year or conference_doi:
        return "conference_venue_year_or_cvf_doi"
    return "linked_version_only"


def affiliation_by_match_basis(root, tables, papers, byline, verified):
    raw = {r["source_record_id"]: within(root, r["raw_path"]) for r in load_records(tables["source_records.jsonl"])}
    work_source = {r["paper_id"]: r["source_record_id"] for r in load_records(tables["field_provenance.csv"])
                   if r["field_name"] == "openalex_id"}
    groups = {"conference_venue_year_or_cvf_doi": set(), "linked_version_only": set()}
    types = {basis: Counter() for basis in groups}
    for p in papers:
        if p["openalex_status"] == "matched":
            cvf = parse_detail(gzip.decompress(raw[p["representative_source_record_id"]].read_bytes()),
                               p["cvf_url"], p["conference"], p["conference_year"])
            cvf.update(conference=p["conference"], conference_year=p["conference_year"])
            work = json.loads(gzip.decompress(raw[work_source[p["paper_id"]]].read_bytes()))
            basis = match_basis(cvf, work)
            groups[basis].add(p["paper_id"])
            types[basis][work.get("type") or "unknown"] += 1
    total_authorships = len({r["authorship_id"] for r in byline})
    breakdown = {}
    for basis, ids in groups.items():
        affiliations = [r for r in verified if r["paper_id"] in ids]
        breakdown[basis] = dict(matched_papers=fraction(len(ids), len(papers)),
                                openalex_work_type_counts=dict(sorted(types[basis].items())),
                                papers_with_verified_affiliation=fraction(len({r["paper_id"] for r in affiliations}), len(papers)),
                                authorships_with_verified_affiliation=fraction(len({r["authorship_id"] for r in affiliations}), total_authorships))
    return breakdown


def report(root, year=2025):
    collector = load_config(root, f"config/a_cvpr{year}_350.json")
    selection = load_selection(root, collector)
    config_path = f"config/a_cvpr{year}_h5.json"
    cfg = json.loads(within(root, config_path).read_text(encoding="utf-8"))
    verification = verify(root, config_path)
    metadata = json.loads(within(root, cfg["input_manifest"]).read_text(encoding="utf-8"))
    if metadata["source_snapshot_id"] != selection["source_snapshot_id"]:
        raise ValueError("Metadata snapshot is not bound to the selection lock")
    manifest_path = cfg["processed_dir"] + "/snapshot_manifest.json"
    manifest = json.loads(within(root, manifest_path).read_text(encoding="utf-8"))
    tables = {Path(f["path"]).name: within(root, f["path"]) for f in manifest["files"]}
    registry = sorted(load_records(tables["paper_registry.csv"]), key=lambda r: r["selection_rank"])
    expected = [(r["selection_rank"], r["paper_id"], r["cvf_url"]) for r in selection["papers"]]
    actual = [(r["selection_rank"], r["paper_id"], r["cvf_url"]) for r in registry]
    if actual != expected:
        raise ValueError("H5 registry differs from the locked sample")
    verified_count = sum(r["status"] == "cvf_verified" for r in registry)
    if verified_count != len(expected):
        raise ValueError(f"Only {verified_count}/{len(expected)} locked papers verified. Check the H5 review queue")
    papers = load_records(tables["papers.jsonl"])
    statuses = Counter(p["openalex_status"] for p in papers)
    if statuses["not_collected"]:
        raise ValueError("OpenAlex collection is incomplete")
    byline = load_records(tables["authorships.csv"])
    verified = [r for r in byline if r["affiliation_status"] == "verified" and r["institution_id"]]
    result = dict(manifest=manifest_path, selection_snapshot_id=selection["source_snapshot_id"],
                verified_locked_papers=fraction(len(registry), collector["target_count"]),
                abstract=fraction(sum(bool(p["abstract"]) for p in papers), len(papers)),
                papers_with_verified_affiliation=fraction(len({r["paper_id"] for r in verified}), len(papers)),
                authorships_with_verified_affiliation=fraction(len({r["authorship_id"] for r in verified}),
                                                              len({r["authorship_id"] for r in byline})),
                openalex_status_counts=dict(sorted(statuses.items())), verification=verification)
    if year == 2026:
        result["openalex_match_basis"] = affiliation_by_match_basis(root, tables, papers, byline, verified)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, choices=(2025, 2026), default=2025)
    args = parser.parse_args()
    result = report(REPO_ROOT, args.year)
    publish({REPO_ROOT / f"outputs/trend/quality/cvpr{args.year}_h5.json": json_bytes(result)})
    print(json.dumps(result, indent=2))
