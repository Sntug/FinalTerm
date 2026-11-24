import json
from pathlib import Path

from src.clean.text import canonical_json, sha256
from src.collect.common import REPO_ROOT, json_bytes, load_config, load_selection, paper_id_from_url, publish, record_bytes, within
from src.collect.trend_selection import ranking

CONFIG = "config/b_iccv2023_trend_350.json"


def lock_iccv2023(root=REPO_ROOT):
    root = Path(root)
    policy = json.loads((root / "config/a_trend_project.json").read_text(encoding="utf-8"))
    cfg = load_config(root, CONFIG)
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


if __name__ == "__main__":
    lock = lock_iccv2023()
    print(f'ICCV2023: {len(lock["papers"])}/{lock["candidate_count"]}')
