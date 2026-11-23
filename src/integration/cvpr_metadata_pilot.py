"""Measure CVF text and source-level affiliation coverage on the first 20 locked papers."""
import json
from collections import Counter

from src.clean.h5_coverage import fraction
from src.clean.text import canonical_json, sha256
from src.collect.cache import HTTPCache, OpenAlexCache, source_record
from src.collect.common import REPO_ROOT, json_bytes, load_config, load_selection, publish
from src.collect.cvf import parse_detail
from src.collect.openalex import collect_work, rule_version


def report(root, config_path):
    cfg = load_config(root, config_path)
    selection = load_selection(root, cfg)
    sample = selection["papers"][:20]
    if len(sample) != 20:
        raise ValueError("Expected at least 20 locked papers")
    cvf = HTTPCache(root, cfg["raw_dir"], offline=True)
    openalex = OpenAlexCache(root, cfg, offline=True)
    source_ids = set()
    statuses = Counter()
    abstracts = papers_with_institution = authorships = authorships_with_institution = 0
    for item in sample:
        body, meta = cvf.get(item["cvf_url"])
        source_ids.add(source_record(meta, item["paper_id"], "paper_detail")["source_record_id"])
        paper = parse_detail(body, item["cvf_url"], cfg["conference"], cfg["conference_year"])
        abstracts += bool(paper["abstract"])
        authorships += len(paper["authors"])
        paper.update(paper_id=item["paper_id"], conference=cfg["conference"], conference_year=cfg["conference_year"])
        work, sources, audit = collect_work(openalex, paper)
        statuses[audit["status"]] += 1
        source_ids.update(s["source_record_id"] for s in sources)
        if work:
            count = sum(any(i.get("id") for i in (a.get("institutions") or [])) for a in work["authorships"])
            papers_with_institution += count > 0
            authorships_with_institution += count
    return dict(conference=cfg["conference"], conference_year=cfg["conference_year"],
                selection_snapshot_id=selection["source_snapshot_id"], selection_rank_range=[1, len(sample)],
                rule_versions={"openalex-work-match": rule_version(cfg)},
                source_record_ids_sha256=sha256(canonical_json(sorted(source_ids)).encode()),
                source_count=len(source_ids), openalex_status_counts=dict(sorted(statuses.items())),
                abstract_cvf=fraction(abstracts, len(sample)),
                papers_with_institution_in_matched_work=fraction(papers_with_institution, len(sample)),
                authorships_with_institution_in_matched_work=fraction(authorships_with_institution, authorships),
                network_requests={"CVF": cvf.network_requests, "OpenAlex": openalex.network_requests})


if __name__ == "__main__":
    summary = report(REPO_ROOT, "config/a_cvpr2026_350.json")
    publish({REPO_ROOT / "outputs/trend/quality/cvpr2026_pilot.json": json_bytes(summary)})
    print(json.dumps(summary, indent=2))
