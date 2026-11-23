import csv
import json
import unittest

from src.clean.text import canonical_json, sha256
from src.collect.cvf import rank_urls
from .select_iccv2025 import CANDIDATES, LOCK, ROOT, SEED, TARGET, classify, listing, paper_id

RAW = ROOT / "data/raw/iccv2025"


def load():
    lock = json.loads((ROOT / LOCK).read_text("utf-8"))
    with open(ROOT / CANDIDATES, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return lock, rows


class SelectionLock(unittest.TestCase):
    def test_committed_files_consistent(self):
        lock, rows = load()
        urls = [r["cvf_url"] for r in rows]
        self.assertEqual(len(rows), lock["candidate_count"])
        self.assertEqual(len(set(urls)), 2701)
        self.assertEqual([int(r["ranking_position"]) for r in rows], list(range(1, len(rows) + 1)))
        for r in rows:
            self.assertEqual(r["rank_key"], sha256(f"{SEED}\n{r['cvf_url']}".encode()))
            self.assertEqual(r["paper_id"], paper_id(r["cvf_url"]))
        keys = [(r["rank_key"], r["cvf_url"]) for r in rows]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(sha256(canonical_json(urls).encode()), lock["candidate_ranking_sha256"])
        self.assertEqual([p["paper_id"] for p in lock["papers"]], [r["paper_id"] for r in rows[:TARGET]])
        self.assertEqual([p["cvf_url"] for p in lock["papers"]], urls[:TARGET])
        self.assertEqual([p["selection_rank"] for p in lock["papers"]], list(range(1, TARGET + 1)))
        registry_bytes = (ROOT / lock["registry_input"]).read_bytes()
        self.assertEqual(sha256(registry_bytes), lock["registry_sha256"])
        with open(ROOT / lock["registry_input"], encoding="utf-8-sig", newline="") as f:
            reg = list(csv.DictReader(f))
        self.assertEqual([(r["paper_id"], r["cvf_url"]) for r in reg], [(r["paper_id"], r["cvf_url"]) for r in rows[:TARGET]])

    @unittest.skipUnless(RAW.exists(), "raw listing cache absent")
    def test_candidates_match_raw_listing(self):
        lock, rows = load()
        body, meta, requests = listing(ROOT, offline=True)
        _, urls, _ = classify(body)
        self.assertEqual(requests, 0)
        self.assertEqual(meta["content_sha256"], lock["listing_content_sha256"])
        self.assertEqual([r["cvf_url"] for r in rows], rank_urls(sorted(urls), SEED))


if __name__ == "__main__":
    unittest.main()
