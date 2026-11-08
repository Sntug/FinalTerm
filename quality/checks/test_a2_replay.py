"""Rebuild A twice in isolation; all production imports come from src/."""
import ast
import json
import shutil
from test_a2_support import temporary_workspace
import unittest
from pathlib import Path
from unittest.mock import patch

from src.collect.bootstrap import bootstrap
from src.collect.common import DEFAULT_CONFIG, REPO_ROOT, load_config, load_selection, within
from src.collect.contract import load_records
from src.collect.pilot import run
from src.collect.verify import verify
from src.clean.text import sha256


class ReplayTests(unittest.TestCase):
    def prepare(self, root):
        (root / "config").mkdir()
        for name in ("a_cvpr2024_pilot.json", "a_cvpr2024_selection.json"):
            shutil.copyfile(REPO_ROOT / "config" / name, root / "config" / name)
        registry = root / "data/processed/cvpr2024/paper_registry.csv"
        registry.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / "data/processed/cvpr2024/paper_registry.csv", registry)
        config_path = root / DEFAULT_CONFIG
        config = json.loads(config_path.read_text())
        config["openalex_enabled"] = False
        config_path.write_text(json.dumps(config), encoding="utf-8")
        bootstrap(root, REPO_ROOT / "handoff/mxh_a1_pilot")

    def table(self, root, name):
        manifest = json.loads((root / "data/processed/cvpr2024/pilot/snapshot_manifest.json").read_text())
        return root / next(f["path"] for f in manifest["files"] if Path(f["path"]).name == name)

    def hashes(self, root):
        return {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in root.rglob("*") if p.is_file()}

    def test_offline_replay_is_identical_and_matches_delivered_A_metadata(self):
        with temporary_workspace() as directory, patch("socket.socket.connect", side_effect=AssertionError("No network")), patch("src.collect.cache.urlopen", side_effect=AssertionError("No network")):
            root = Path(directory)
            self.prepare(root)
            result = run(root)
            self.assertEqual(result["papers"], 30)
            self.assertEqual(result["raw_sources_checked"], 31)
            self.assertEqual(result["text_versions_checked"], 60)
            self.assertEqual(result["network_requests"], {"CVF": 0, "OpenAlex": 0})
            self.assertFalse(result["graph_ready"])
            before = self.hashes(root)
            bootstrap(root, REPO_ROOT / "handoff/mxh_a1_pilot")
            self.assertEqual(run(root), result)
            self.assertEqual(before, self.hashes(root))
            for name in ("papers.jsonl", "paper_registry.csv", "authorships.csv", "text_versions.jsonl"):
                delivered = load_records(REPO_ROOT / "handoff/mxh_contract_v2/pilot_v2/data/processed" / name)
                expected = [r for r in delivered if r.get("owner") == "A" or r.get("paper_id", "").startswith("cvf:CVPR2024:")]
                self.assertEqual(load_records(self.table(root, name)), expected, name)
            self.assertFalse((root / "data/raw/iccv2023").exists())
            self.assertFalse((root / "data/paper_registry.csv").exists())

    def test_different_existing_output_is_preserved_and_rejected(self):
        with temporary_workspace() as directory:
            root = Path(directory)
            self.prepare(root)
            run(root)
            path = self.table(root, "papers.jsonl")
            path.write_bytes(b"existing user change\n")
            before = self.hashes(root)
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                run(root)
            self.assertEqual(before, self.hashes(root))
            with self.assertRaises(ValueError):
                verify(root, "data/processed/cvpr2024/pilot/snapshot_manifest.json")

    def test_incomplete_output_can_resume_from_existing_cache(self):
        with temporary_workspace() as directory, patch("src.collect.cache.urlopen", side_effect=AssertionError("No network")):
            root = Path(directory)
            self.prepare(root)
            result = run(root)
            target = self.table(root, "text_versions.jsonl")
            expected = target.read_bytes()
            target.unlink()
            self.assertEqual(run(root), result)
            self.assertEqual(target.read_bytes(), expected)

    def test_config_rejects_wrong_corpus_paths_and_invalid_count(self):
        with temporary_workspace() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            original = json.loads((REPO_ROOT / DEFAULT_CONFIG).read_text(encoding="utf-8"))
            for field, value in (("raw_dir", "data/raw/iccv2023"), ("processed_dir", "data/processed"), ("target_count", 0)):
                (root / DEFAULT_CONFIG).write_text(json.dumps({**original, field: value}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(root)
            with self.assertRaises(ValueError):
                within(root, "../outside.json")

    def test_production_modules_never_import_handoff(self):
        for folder in (REPO_ROOT / "src/collect", REPO_ROOT / "src/clean"):
            for path in folder.glob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        self.assertFalse((node.module or "").startswith(("handoff", "contract_v2")), path)
                    elif isinstance(node, ast.Import):
                        self.assertFalse(any(a.name.startswith(("handoff", "contract_v2")) for a in node.names), path)


if __name__ == "__main__":
    unittest.main()
