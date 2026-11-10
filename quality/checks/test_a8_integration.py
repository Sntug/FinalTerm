"""A8 safety/status tests; Neo4j fakes here never establish a real connection."""
import copy
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from src.collect.common import REPO_ROOT, json_bytes
from src.integration.a8 import Checks, configured, dependency, form_state, compare_baseline, human_status, recorded_import, exit_status
from src.integration import neo4j as neo
from test_a2_support import temporary_workspace


MANIFEST = {"snapshot_id": "snapshot:v2:example"}
NODES = [("Paper", dict(id="p1", snapshot_id=MANIFEST["snapshot_id"], scope="core", conference="CVPR", conference_year=2024)),
         ("Task", dict(id="task:one", snapshot_id=MANIFEST["snapshot_id"]))]
RELS = [("p1", "STUDIES_TASK", "task:one", dict(edge_id="edge:one", weight=1))]


class A8ConfigTests(unittest.TestCase):
    def fixture(self, root):
        (root / "config").mkdir()
        for name in ("a8_integration.json", "a8_nlp_700.json", "a8_graph_700.json", "a8_audit.json", "a7_report.json"):
            (root / "config" / name).write_bytes((REPO_ROOT / "config" / name).read_bytes())

    def change(self, root, file, callback):
        path = root / "config" / file
        data = json.loads(path.read_text(encoding="utf-8"))
        callback(data)
        path.write_bytes(json_bytes(data))

    def test_current_configs_bind_the_same_snapshots(self):
        configured(REPO_ROOT, "config/a8_integration.json")

    def test_historical_graph_output_is_rejected(self):
        with temporary_workspace() as root:
            self.fixture(root)
            self.change(root, "a8_graph_700.json", lambda c: c.update(output_dir="data/processed/mxh_cv_700/graph_b5"))
            with self.assertRaisesRegex(ValueError, "separate a8"):
                configured(root, "config/a8_integration.json")

    def test_escaping_output_is_rejected(self):
        with temporary_workspace() as root:
            self.fixture(root)
            self.change(root, "a8_integration.json", lambda c: c.update(output_dir="../outside"))
            with self.assertRaises(ValueError):
                configured(root, "config/a8_integration.json")

    def test_old_human_audit_cannot_be_overwritten(self):
        with temporary_workspace() as root:
            self.fixture(root)
            self.change(root, "a8_audit.json", lambda c: c.update(output_dir="outputs/a6"))
            with self.assertRaisesRegex(ValueError, "separate directory"):
                configured(root, "config/a8_integration.json")

    def test_nlp_and_graph_must_share_corpus_bindings(self):
        with temporary_workspace() as root:
            self.fixture(root)
            self.change(root, "a8_nlp_700.json", lambda c: c.update(input_manifests=["wrong.json"]))
            with self.assertRaisesRegex(ValueError, "input snapshots differ"):
                configured(root, "config/a8_integration.json")

    def test_report_cannot_mix_graph_snapshots(self):
        with temporary_workspace() as root:
            self.fixture(root)
            self.change(root, "a7_report.json", lambda c: c.update(nlp_config="config/b5_nlp_700.json"))
            with self.assertRaisesRegex(ValueError, "different graph"):
                configured(root, "config/a8_integration.json")


class A8StatusTests(unittest.TestCase):
    def test_cli_distinguishes_success_failure_and_unexecuted_checks(self):
        self.assertEqual(exit_status({"status": "PASS"}), 0)
        self.assertEqual(exit_status({"status": "FAIL"}), 1)
        self.assertEqual(exit_status({"status": "BLOCKED_ENV"}), 2)
        self.assertEqual(exit_status({"status": "NOT_RUN"}), 2)
        self.assertEqual(exit_status({"offline_checks_passed": False}), 1)
    def test_no_result_cannot_be_counted_as_pass(self):
        checks = Checks()
        checks.run("nothing", lambda: None)
        self.assertEqual(checks.rows[0]["status"], "FAIL")

    def test_known_human_error_is_fail_even_while_other_samples_are_pending(self):
        h = {k: {"incorrect": 0, "unverifiable": 0} for k in ("primary", "cross", "nodes")}
        h.update(human_findings_clear=False, human_audit_complete=False, cross_disagreements=[])
        self.assertEqual(human_status(h), "PENDING_B")
        h["primary"]["incorrect"] = 1
        self.assertEqual(human_status(h), "FAIL")

    def test_failed_live_test_receipt_is_not_hidden_as_environment_pending(self):
        with temporary_workspace() as root:
            (root / "test_import.json").write_bytes(json_bytes({"status": "FAIL", "reason": "wrong count"}))
            self.assertEqual(recorded_import(root, root, Path("unused"), "p")["status"], "FAIL")

    def test_actual_failure_is_not_pending_b(self):
        checks = Checks()
        def fail():
            raise ValueError("wrong hash")
        self.assertIsNone(checks.run("bad", fail, owner="B"))
        self.assertEqual(checks.rows[0]["status"], "FAIL")

    def test_environment_failure_is_blocked(self):
        checks = Checks()
        def fail():
            raise ImportError("missing optional dependency")
        checks.run("env", fail)
        self.assertEqual(checks.rows[0]["status"], "BLOCKED_ENV")

    def test_false_pass_flag_is_failure(self):
        checks = Checks()
        checks.run("check", lambda: dict(passed=False))
        self.assertEqual(checks.rows[0]["status"], "FAIL")

    def test_existing_unverified_b_file_does_not_become_pass(self):
        item = dict(task="B6", paths=["b6.json"], missing="missing")
        with temporary_workspace() as root:
            self.assertEqual(dependency(root, item)["status"], "PENDING_B")
            (root / "b6.json").write_text("{}", encoding="utf-8")
            self.assertEqual(dependency(root, item)["status"], "NOT_RUN")

    def test_export_receipt_does_not_copy_large_manifest(self):
        checks = Checks()
        checks.run("export", lambda: ({"snapshot_id": "s", "applied_decision_ids": ["large"] * 1000}, {"name_prop_conflicts": []}))
        self.assertNotIn("applied_decision_ids", checks.rows[0]["details"])

    def test_audit_with_human_edits_uses_summarize_only(self):
        with temporary_workspace() as root:
            (root / "audit.json").write_bytes(json_bytes({"output_dir": "outputs/a8/audit"}))
            out = root / "outputs/a8/audit"
            out.mkdir(parents=True)
            (out / "a6_run_manifest.json").write_text("{}", encoding="utf-8")
            form = out / "a6_edge_audit_sample.csv"
            form.write_bytes(b"human edits must remain")
            with patch("src.audit.pipeline.run") as run, patch("src.audit.pipeline.summarize") as summarize, patch(
                    "src.reporting.a7.audit_metrics", return_value={"status": "available", "automatic_checks_passed": True}):
                form_state(root, "audit.json")
                run.assert_not_called()
                summarize.assert_called_once()
            self.assertEqual(form.read_bytes(), b"human edits must remain")

    def test_evidence_delta_does_not_masquerade_as_new_semantic_edge(self):
        old = {"nodes.csv": [{"id": "a"}], "edges.csv": [{"edge_id": "e", "weight": 1, "evidence_ids": ["x"]}],
               "evidence.jsonl": [{"evidence_id": "x"}], "source_records.jsonl": [], "needs_review.csv": []}
        new = copy.deepcopy(old)
        new["edges.csv"][0]["evidence_ids"].append("y")
        new["evidence.jsonl"].append({"evidence_id": "y"})
        result = compare_baseline(old, new)
        self.assertEqual((result["semantic_edge_records_changed"], result["edge_evidence_changed"], result["evidence_added"]), (0, 1, 1))


class A8Neo4jTests(unittest.TestCase):
    def test_read_comparison_checks_content_and_snapshot_not_just_counts(self):
        result = neo.compare_records(MANIFEST, NODES, RELS, NODES, RELS)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["papers_by_conference"], {"CVPR2024": 1})
        wrong = copy.deepcopy(RELS)
        wrong[0][3]["weight"] = 2
        with self.assertRaisesRegex(ValueError, "content hash"):
            neo.compare_records(MANIFEST, NODES, RELS, NODES, wrong)

    def test_same_counts_with_wrong_snapshot_tags_fail(self):
        wrong = copy.deepcopy(NODES)
        wrong[0][1]["snapshot_id"] = "older"
        with self.assertRaisesRegex(ValueError, "snapshot tags"):
            neo.compare_records(MANIFEST, NODES, RELS, wrong, RELS)

    def test_duplicate_relationships_fail(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            neo.compare_records(MANIFEST, NODES, RELS, NODES, RELS * 2)

    def test_missing_driver_never_connects_or_loads(self):
        with patch.object(neo, "read_snapshot", return_value=(MANIFEST, NODES, RELS)), patch.object(
                neo.importlib.util, "find_spec", return_value=None), patch.object(neo, "load") as load:
            self.assertEqual(neo.inspect(Path("snapshot"))["status"], "BLOCKED_ENV")
            load.assert_not_called()

    def test_test_import_rejects_normal_ports_remote_and_embedded_credentials(self):
        for uri in ("bolt://localhost:7687", "bolt://127.0.0.1:17687", "bolt://remote:17688",
                    "bolt://user:secret@localhost:17688", "neo4j://localhost:17688"):
            with self.assertRaises(ValueError):
                neo.isolated_uri(uri)
        self.assertEqual(neo.isolated_uri("bolt://127.0.0.1:17688"), "bolt://127.0.0.1:17688")

    def fake_driver(self, occupied):
        database = MagicMock()
        driver = database.driver.return_value.__enter__.return_value
        session = driver.session.return_value.__enter__.return_value
        session.run.return_value.single.return_value = {"c": occupied}
        return types.SimpleNamespace(GraphDatabase=database)

    def test_test_import_refuses_occupied_instance_without_writes(self):
        env = {"A8_NEO4J_TEST_URI": "bolt://127.0.0.1:17688", "A8_NEO4J_TEST_USER": "test", "A8_NEO4J_TEST_PASSWORD": "fixture"}
        with patch.dict(os.environ, env), patch.dict(sys.modules, {"neo4j": self.fake_driver(1)}), patch.object(
                neo.importlib.util, "find_spec", return_value=object()), patch.object(neo, "read_snapshot", return_value=(MANIFEST, NODES, RELS)), patch.object(neo, "load") as load:
            with self.assertRaisesRegex(ValueError, "not empty"):
                neo.test_import(Path("snapshot"))
            load.assert_not_called()

    def test_isolated_import_checks_repeat_and_rollback_using_existing_loader(self):
        env = {"A8_NEO4J_TEST_URI": "bolt://127.0.0.1:17688", "A8_NEO4J_TEST_USER": "test", "A8_NEO4J_TEST_PASSWORD": "fixture"}
        digest = neo.content_hash(NODES, RELS)
        with patch.dict(os.environ, env), patch.dict(sys.modules, {"neo4j": self.fake_driver(0)}), patch.object(
                neo.importlib.util, "find_spec", return_value=object()), patch.object(neo, "read_snapshot", return_value=(MANIFEST, NODES, RELS)), patch.object(
                neo, "load", side_effect=[{"content_sha256": digest}, {"content_sha256": digest}, RuntimeError("injected failure after nodes")]) as load, patch.object(
                neo, "db_records", return_value=(NODES, RELS)), patch.object(neo, "credentials", side_effect=AssertionError("must not read .env")):
            result = neo.test_import(Path("snapshot"))
            self.assertEqual(result["repeat_import"], "PASS")
            self.assertEqual(result["rollback_after_injected_failure"], "PASS")
            self.assertEqual(load.call_count, 3)
            self.assertTrue(load.call_args_list[2].kwargs["fail_after_nodes"])
            self.assertNotIn("last_import", load.call_args_list[0].kwargs)


if __name__ == "__main__":
    unittest.main()
