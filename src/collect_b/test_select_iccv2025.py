import json
import unittest

from src.clean.text import canonical_json, sha256
from src.collect.cvf import rank_urls
from .select_iccv2025 import LOCK, ROOT, SEED, TARGET, classify, listing, paper_id


class SelectionLock(unittest.TestCase):
    def test_lock_matches_cached_listing(self):
        lock = json.loads((ROOT / LOCK).read_text("utf-8"))
        body, meta, requests = listing(ROOT, offline=True)
        _, urls, _ = classify(body)
        ranked = rank_urls(sorted(urls), SEED)
        self.assertEqual(requests, 0)
        self.assertEqual(meta["content_sha256"], lock["listing_content_sha256"])
        self.assertEqual(len(ranked), lock["candidate_count"])
        self.assertEqual(sha256(canonical_json(ranked).encode()), lock["candidate_ranking_sha256"])
        self.assertEqual([p["paper_id"] for p in lock["papers"]], [paper_id(u) for u in ranked[:TARGET]])
        self.assertEqual([p["cvf_url"] for p in lock["papers"]], ranked[:TARGET])
        self.assertEqual(len({p["paper_id"] for p in lock["papers"]}), TARGET)
        registry = (ROOT / lock["registry_input"]).read_bytes()
        self.assertEqual(sha256(registry), lock["registry_sha256"])


if __name__ == "__main__":
    unittest.main()
