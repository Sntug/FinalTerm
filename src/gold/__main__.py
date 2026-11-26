"""Build or verify the H4 gold split using only the five H3 selection locks."""
import argparse
import json

from src.clean.text import canonical_json, sha256
from src.collect.common import REPO_ROOT, publish, record_bytes

LOCKS = {
    "CVPR2024": "a_cvpr2024_350_selection.json",
    "CVPR2025": "a_cvpr2025_350_selection.json",
    "CVPR2026": "a_cvpr2026_350_selection.json",
    "ICCV2023": "b_iccv2023_trend_350_selection.json",
    "ICCV2025": "b_iccv2025_350_selection.json",
}
DEV = 5
TEST = 15
FIELDS = ["venue_edition", "paper_id", "split", "selection_rank", "source_snapshot_id"]
OUTPUT = REPO_ROOT / "data/gold/gold_set.csv"


def select_edition(edition, lock, policy):
    papers = lock["papers"]
    if edition != f'{lock["conference"]}{lock["conference_year"]}' or lock["seed"] != policy["seed"]:
        raise ValueError(f"{edition}: selection edition or seed mismatch")
    if len(papers) != lock["target_count"] or len(papers) != policy["target_count"] or len(papers) < DEV + TEST:
        raise ValueError(f"{edition}: incomplete selection")
    snapshot_id = "selection:" + sha256(canonical_json(papers).encode("utf-8"))
    if snapshot_id != lock["source_snapshot_id"]:
        raise ValueError(f"{edition}: selection snapshot hash mismatch")

    ranks = {}
    for rank, paper in enumerate(papers, 1):
        pid = paper["paper_id"]
        if paper["selection_rank"] != rank or not pid.startswith(f"cvf:{edition}:") or pid in ranks:
            raise ValueError(f"{edition}: invalid ID or selection rank at row {rank}")
        ranks[pid] = rank

    def gold_order(pid):
        key = f'H4\n{policy["seed"]}\n{pid}'.encode("utf-8")
        return sha256(key), pid

    rows = []
    for i, pid in enumerate(sorted(ranks, key=gold_order)[:DEV + TEST]):
        rows.append(dict(venue_edition=edition, paper_id=pid, split="dev" if i < DEV else "test",
                         selection_rank=ranks[pid], source_snapshot_id=snapshot_id))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare the existing CSV with an offline replay")
    args = parser.parse_args()
    config = REPO_ROOT / "config"
    policy = json.loads((config / "a_trend_project.json").read_text("utf-8"))
    rows = []
    for edition, filename in LOCKS.items():
        lock = json.loads((config / filename).read_text("utf-8"))
        rows.extend(select_edition(edition, lock, policy))

    content = record_bytes(OUTPUT.name, FIELDS, rows)
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_bytes() != content:
            parser.exit(1, "H4 verification failed: gold_set.csv is missing or differs from replay.\n")
    else:
        publish({OUTPUT: content})
    print(f"{OUTPUT.name}: {len(rows)} papers, {DEV} dev + {TEST} test per edition, sha256={sha256(content)}")


if __name__ == "__main__":
    main()
