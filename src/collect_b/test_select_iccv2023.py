import csv
import json
import unittest

from src.clean.text import canonical_json, sha256
from src.collect.common import paper_id_from_url
from src.collect.cvf import parse_listing, rank_urls
from src.collect.common import REPO_ROOT as ROOT
from .select_iccv2023 import CONFIG

SEED, TARGET = 20261103, 350
LOCK = "config/b_iccv2023_trend_350_selection.json"
CANDIDATES = "data/processed/iccv2023/trend/candidates_ranked.csv"
RAW = ROOT / "data/raw/iccv2023/catalog/ICCV2023_all_papers.html"


def load():
    lock = json.loads((ROOT / LOCK).read_text("utf-8"))
    with open(ROOT / CANDIDATES, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return lock, rows


class SelectionLock(unittest.TestCase):
    def test_committed_files_consistent(self):
        lock, rows = load()
        urls = [r["cvf_url"] for r in rows]
        self.assertEqual(len(rows), lock["candidate_count"])
        self.assertEqual(len(set(urls)), len(urls))
        self.assertEqual([int(r["ranking_position"]) for r in rows], list(range(1, len(rows) + 1)))
        for r in rows:
            self.assertEqual(r["paper_id"], paper_id_from_url(r["cvf_url"]))
        keys = [(sha256(f"{SEED}\n{u}".encode()), u) for u in urls]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(sha256(canonical_json(urls).encode()), lock["candidate_ranking_sha256"])
        self.assertEqual((lock["seed"], lock["target_count"]), (SEED, TARGET))
        self.assertEqual([p["paper_id"] for p in lock["papers"]], [r["paper_id"] for r in rows[:TARGET]])
        self.assertEqual([p["cvf_url"] for p in lock["papers"]], urls[:TARGET])
        self.assertEqual([p["selection_rank"] for p in lock["papers"]], list(range(1, TARGET + 1)))
        registry_bytes = (ROOT / lock["registry_input"]).read_bytes()
        self.assertEqual(sha256(registry_bytes), lock["registry_sha256"])
        with open(ROOT / lock["registry_input"], encoding="utf-8-sig", newline="") as f:
            reg = list(csv.DictReader(f))
        self.assertEqual([(r["paper_id"], r["cvf_url"]) for r in reg], [(r["paper_id"], r["cvf_url"]) for r in rows[:TARGET]])
        self.assertEqual(sum(a["cvf_url"] == b["cvf_url"] for a, b in zip(reg, rows)), TARGET)
        self.assertEqual(json.loads((ROOT / CONFIG).read_text("utf-8"))["selection_file"], LOCK)

    @unittest.skipUnless(RAW.exists(), "raw listing cache absent")
    def test_candidates_match_raw_listing(self):
        lock, rows = load()
        urls = parse_listing(RAW.read_bytes(), "ICCV", 2023)
        self.assertEqual([r["cvf_url"] for r in rows], rank_urls(urls, SEED))


if __name__ == "__main__":
    unittest.main()
