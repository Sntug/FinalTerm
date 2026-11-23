"""Replay CVPR trend selections from the two pinned CVF listings."""
import csv
import json

from src.clean.text import canonical_json, sha256
from .cache import HTTPCache, source_record
from .common import (REPO_ROOT, json_bytes, load_config, load_selection, paper_id_from_url,
                     publish, record_bytes, within)
from .cvf import parse_listing, rank_urls


def ranking(root, cfg, policy):
    if (cfg["seed"], cfg["target_count"]) != (policy["seed"], policy["target_count"]):
        raise ValueError("Collector and trend sampling policies differ")
    venue = f'venue:{cfg["conference"]}:{cfg["conference_year"]}:main'
    if venue not in policy["venue_ids"]:
        raise ValueError(f"Unexpected venue {venue}")
    body, meta = HTTPCache(root, cfg["raw_dir"]).get(cfg["listing_url"])
    urls = rank_urls(parse_listing(body, cfg["conference"], cfg["conference_year"]), cfg["seed"])
    if len(urls) < cfg["target_count"] or len({paper_id_from_url(u) for u in urls}) != len(urls):
        raise ValueError("Insufficient candidates or ambiguous paper IDs")
    return urls, source_record(meta, None, "listing")


def lock_2025(root, policy):
    cfg = load_config(root, "config/a_cvpr2025_350.json")
    ranked, listing = ranking(root, cfg, policy)
    edition = {key: cfg[key] for key in ("owner", "conference", "conference_year")}
    papers, rows, candidates = [], [], []
    for rank, url in enumerate(ranked, 1):
        candidate = dict(ranking_position=rank, paper_id=paper_id_from_url(url), cvf_url=url)
        candidates.append(candidate)
        if rank <= cfg["target_count"]:
            papers.append(dict(**candidate, selection_rank=rank, source_record_id=""))
            rows.append(dict(paper_id=candidate["paper_id"], cvf_url=url, **edition, doi="", source_record_id=""))
    registry = record_bytes("input_registry.csv", list(rows[0]), rows)
    lock = dict(**edition, seed=cfg["seed"], target_count=cfg["target_count"],
                selection_algorithm=policy["selection_algorithm"], candidate_count=len(ranked),
                candidate_ranking_sha256=sha256(canonical_json(ranked).encode()),
                listing_source_record_id=listing["source_record_id"], listing_url=listing["url"],
                listing_content_sha256=listing["content_sha256"], listing_raw_path=listing["raw_path"],
                listing_fetched_at=listing["fetched_at"], registry_input=cfg["registry_input"],
                registry_sha256=sha256(registry), source_snapshot_id="selection:" + sha256(canonical_json(papers).encode()),
                papers=papers)
    publish({within(root, cfg["registry_input"]): registry,
             within(root, cfg["processed_dir"]) / "candidates_ranked.csv":
                 record_bytes("candidates_ranked.csv", list(candidates[0]), candidates),
             within(root, cfg["selection_file"]): json_bytes(lock)})
    load_selection(root, cfg)
    return lock


def compare_2024(root, policy):
    cfg = load_config(root, "config/a_cvpr2024_350.json")
    ranked, source = ranking(root, cfg, policy)
    selected = load_selection(root, cfg)
    if (source["source_record_id"] != selected["listing_source_record_id"]
            or sha256(canonical_json(ranked).encode()) != selected["candidate_ranking_sha256"]):
        raise ValueError("Historical listing or ranking differs from its lock")
    actual = [p["paper_id"] for p in selected["papers"]]
    snapshot = "data/processed/cvpr2024/a5_350/paper_registry.csv"
    with within(root, snapshot).open(encoding="utf-8-sig", newline="") as stream:
        verified = sorted(csv.DictReader(stream), key=lambda row: int(row["selection_rank"]))
    if actual != [row["paper_id"] for row in verified]:
        raise ValueError("A5 paper registry differs from the locked selection")
    expected = [paper_id_from_url(url) for url in ranked[:cfg["target_count"]]]
    actual_only = sorted(set(actual) - set(expected))
    rule_only = sorted(set(expected) - set(actual))
    row = dict(venue_edition="CVPR2024", listing_source_record_id=source["source_record_id"],
               listing_content_sha256=source["content_sha256"], candidate_count=len(ranked),
               seed=cfg["seed"], registry=cfg["registry_input"], registry_sha256=selected["registry_sha256"],
               verified_registry=snapshot, selected_count=len(actual), rule_count=len(expected),
               overlap=len(actual) - len(actual_only), matching_positions=sum(a == b for a, b in zip(actual, expected)),
               sample_follows_rule=str(not actual_only and not rule_only).lower(),
               preserved_pilot_count=len(selected["preserved_paper_ids"]), actual_only_ids=actual_only, rule_only_ids=rule_only)
    publish({root / "outputs/trend/quality/cvpr2024_selection.csv": record_bytes("selection.csv", list(row), [row])})
    return row


if __name__ == "__main__":
    policy = json.loads((REPO_ROOT / "config/a_trend_project.json").read_text(encoding="utf-8"))
    lock = lock_2025(REPO_ROOT, policy)
    print(f'CVPR2025: {len(lock["papers"])}/{lock["candidate_count"]}')
    print(json.dumps(compare_2024(REPO_ROOT, policy)))
