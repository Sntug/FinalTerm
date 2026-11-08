"""Rebuild the delivered pilot from raw snapshots in a fresh directory, twice."""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class OfflineReplayTest(unittest.TestCase):
    def test_fresh_rebuild_and_second_run_are_byte_identical(self):
        source = Path(__file__).resolve().parents[1]
        expected = [
            "data/raw/pilot_papers.jsonl", "data/raw/a_cvpr2024_pilot_papers.jsonl",
            "data/raw/b_iccv2023_pilot_papers.jsonl", "data/raw/source_records.jsonl",
            "data/processed/paper_registry.csv", "data/processed/a_cvpr2024_pilot_registry.csv",
            "data/processed/b_iccv2023_pilot_registry_v1.csv", "data/processed/paper_metadata.csv",
            "data/processed/authorships.csv", "data/processed/selection_manifest.json",
            "outputs/pilot_summary.json", "outputs/b_registry_review.csv",
            "outputs/field_coverage.csv", "outputs/REVIEW_A1_B.md",
        ]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in ("src", "config", "schemas", "data/input", "data/raw/http"):
                shutil.copytree(source / name, target / name, ignore=shutil.ignore_patterns("__pycache__"))
            for iteration in range(2):
                result = subprocess.run([sys.executable, "-m", "src.collect", "--offline"],
                                        cwd=target, capture_output=True, text=True, encoding="utf-8", timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("network requests this run: 0", result.stdout)
                for name in expected:
                    self.assertEqual(hashlib.sha256((source / name).read_bytes()).hexdigest(),
                                     hashlib.sha256((target / name).read_bytes()).hexdigest(),
                                     f"Rebuild {iteration+1} differs: {name}")
            result = subprocess.run([sys.executable, "-m", "src.quality"], cwd=target,
                                    capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
