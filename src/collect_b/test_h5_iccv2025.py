import csv
import gzip
import json
import unittest
from collections import Counter
from pathlib import Path

from src.collect.cache import api_key
from src.collect.common import REPO_ROOT as ROOT
from src.collect.contract import load_records
from .h5_coverage_iccv2025 import H5, OUT, report, review_counts

LOCK = json.loads((ROOT / "config/b_iccv2025_350_selection.json").read_text("utf-8"))
REGISTRY_SHA = "aefc467f55bcd66665c5458a4db5052b3ab71e22022ca17634418f266442e51b"
SCANNED = ("data/raw/iccv2025", "data/processed/iccv2025", "outputs/b_iccv2025")


def tables():
    cfg = json.loads((ROOT / H5).read_text("utf-8"))
    manifest = json.loads((ROOT / cfg["processed_dir"] / "snapshot_manifest.json").read_text("utf-8"))
    return {Path(f["path"]).name: ROOT / f["path"] for f in manifest["files"]}


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


class ReviewCounts(unittest.TestCase):
    def test_counts_rows_and_distinct_papers(self):
        rows = [{"paper_id": "a", "entity_type": "Paper"}, {"paper_id": "a", "entity_type": "Author"},
                {"paper_id": None, "entity_type": "Author"}]
        self.assertEqual(review_counts(rows), {"rows": 3, "papers": 1, "by_entity": {"Author": 2, "Paper": 1}})


class GeneratedFiles(unittest.TestCase):
    def test_lock_unchanged(self):
        self.assertEqual(LOCK["registry_sha256"], REGISTRY_SHA)

    def test_papers_match_lock(self):
        expected = [(p["selection_rank"], p["paper_id"], p["cvf_url"]) for p in LOCK["papers"]]
        registry = load_records(tables()["paper_registry.csv"])
        self.assertEqual(sorted((r["selection_rank"], r["paper_id"], r["cvf_url"]) for r in registry), expected)
        papers = load_records(tables()["papers.jsonl"])
        self.assertEqual(sorted(p["paper_id"] for p in papers), sorted(p[1] for p in expected))
        authorship_papers = {r["paper_id"] for r in load_records(tables()["authorships.csv"])}
        self.assertEqual(authorship_papers, {p[1] for p in expected})

    def test_coverage_file_matches_tables(self):
        self.assertEqual(json.loads((ROOT / OUT).read_text("utf-8")), report(ROOT))

    def test_coverage_file_matches_independent_recount(self):
        saved = json.loads((ROOT / OUT).read_text("utf-8"))
        files = tables()
        lines = files["papers.jsonl"].read_text("utf-8").split("\n")
        papers = [json.loads(line) for line in lines if line]
        byline = csv_rows(files["authorships.csv"])
        linked = [r for r in byline if r["affiliation_status"] == "verified" and r["institution_id"]]
        total = len({r["authorship_id"] for r in byline})
        expected = {
            "verified_locked_papers": (sum(r["status"] == "cvf_verified" for r in csv_rows(files["paper_registry.csv"])), 350),
            "abstract": (sum(bool((p["abstract"] or "").strip()) for p in papers), 350),
            "papers_with_verified_affiliation": (len({r["paper_id"] for r in linked}), 350),
            "authorships_with_verified_affiliation": (len({r["authorship_id"] for r in linked}), total),
        }
        for key, (numerator, denominator) in expected.items():
            self.assertEqual(saved[key], {"numerator": numerator, "denominator": denominator,
                                          "percent": round(100 * numerator / denominator, 2)}, key)
        self.assertEqual(saved["openalex_status_counts"], Counter(p["openalex_status"] for p in papers))
        review = csv_rows(files["needs_review.csv"])
        self.assertEqual(saved["needs_review"], {
            "rows": len(review), "papers": len({r["paper_id"] for r in review if r["paper_id"]}),
            "by_entity": Counter(r["entity_type"] for r in review)})
        self.assertEqual({r["paper_id"] for r in review if r["entity_type"] == "Paper"},
                         {p["paper_id"] for p in papers if p["openalex_status"] == "needs_review"})

    def test_no_api_key_in_outputs(self):
        key = api_key(ROOT)
        if not key:
            self.skipTest("no key configured")
        hits = []
        for folder in SCANNED:
            for path in (ROOT / folder).rglob("*"):
                if path.is_file():
                    body = path.read_bytes()
                    if path.suffix == ".gz":
                        body = gzip.decompress(body)
                    if key.encode() in body:
                        hits.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
