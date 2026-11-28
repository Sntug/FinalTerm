import csv
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from src.collect.common import REPO_ROOT
from .h7_inputs import manifest_table, prepare


class H7GoldIsolationTests(unittest.TestCase):
    def test_raw_reads_respect_locked_split(self):
        root = REPO_ROOT
        path = "data/processed/cvpr2025/h5/snapshot_manifest.json"
        manifest = json.loads((root / path).read_text("utf-8"))
        sources = manifest_table(root, manifest, "source_records.jsonl")
        with (root / "data/gold/gold_set.csv").open(encoding="utf-8-sig", newline="") as stream:
            splits = {row["paper_id"]: row["split"] for row in csv.DictReader(stream)}

        read_bytes = Path.read_bytes
        for group, expected_count in (("dev", 5), ("candidates", 330)):
            with self.subTest(group=group):
                allowed = {root / src["raw_path"] for src in sources
                           if src["source_kind"] == "paper_detail"
                           and splits.get(src["paper_id"], "candidates") == group}

                def guarded_read(path):
                    if path.is_relative_to(root / "data/raw"):
                        self.assertIn(path, allowed)
                    if path.name in ("papers.jsonl", "text_versions.jsonl"):
                        self.fail("Bulk corpus includes held-out text")
                    return read_bytes(path)

                with patch.object(Path, "read_bytes", guarded_read):
                    rows = prepare(root, "CVPR2025", path, group)
                ids = {row["paper_id"] for row in rows}
                self.assertEqual(len(rows), expected_count)
                self.assertEqual(len(ids), expected_count)
                self.assertTrue(all(splits.get(pid, "candidates") == group for pid in ids))
