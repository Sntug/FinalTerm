"""A6 structural fault detection, reproducible sampling and honest human metrics."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from src.audit.checks import Findings, graph_checks, corpus_checks, identity_risks, expected_metadata
from src.audit.pipeline import run, summarize
from src.audit.sampling import samples, csv_bytes, decode_csv, EDGE_FIELDS, NODE_FIELDS, human_summary, form_fingerprint, pending
from src.clean.text import text_record, evidence_id, identifier, canonical_json
from src.collect.common import REPO_ROOT, json_bytes
from src.graph.export_graph import build
from test_a2_support import temporary_workspace
from test_a4_nlp import write_snapshot
from test_a5_metadata import fixture, STAMP


def graph_fixture(root):
    cfg, _, data, bodies = fixture(root)
    write_snapshot(root, "data/processed/papers/s1", data)
    nodes, edges, *_ = build(dict(project_id="mxh_cv_700", inputs=[dict(name="X", snapshots_dir="data/processed/papers", a3_dir=cfg["input_manifest"].rsplit("/", 1)[0])]), root)
    data["nodes.csv"], data["edges.csv"] = nodes, edges
    manifest = dict(project_id="mxh_cv_700", snapshot_id="snapshot:test", node_count=len(nodes), edge_count=len(edges), rule_versions={})
    return data, manifest, bodies


def add_nlp(data, manifest, text="We evaluate on COCO.", typ="EVALUATED_ON"):
    p = data["papers.jsonl"][0]
    t = text_record(p["paper_id"], p["representative_source_record_id"], "html:div#abstract.text", text, "fixture", STAMP)
    data["text_versions.jsonl"].append(t)
    p["abstract"], p["abstract_text_version_id"] = t["normalized_text"], t["text_version_id"]
    label = {"EVALUATED_ON":"Dataset", "STUDIES_TASK":"Task", "USES_METHOD":"Method"}[typ]
    dst = label.lower() + ":fixture"
    data["nodes.csv"].append(dict(id=dst, label=label, name="fixture", owner="A", source_origin=["CVF"], source_record_ids=[t["source_record_id"]], validation_status="accepted", project_id="mxh_cv_700", properties_json={}))
    rule = {"EVALUATED_ON":"a4-dataset-evaluate", "STUDIES_TASK":"a4-task-current", "USES_METHOD":"b5-method-use"}[typ]
    ev = dict(evidence_kind="nlp", paper_id=p["paper_id"], source_record_id=t["source_record_id"], source_url=p["cvf_url"],
        field_path=t["field_path"], evidence_text=text, start_char=0, end_char=len(text), rule_id=rule, rule_version="1.0.0", captured_at=STAMP,
        supporting_evidence_ids=[], owner="A", text_version_id=t["text_version_id"], normalized_text_sha256=t["normalized_text_sha256"], normalization_version=t["normalization_version"])
    ev["evidence_id"] = evidence_id(ev)
    data["evidence.jsonl"].append(ev)
    edge = dict(edge_id=identifier("edge", p["paper_id"], typ, dst), src=p["paper_id"], type=typ, dst=dst, weight=1,
                derivation="nlp", validation_status="accepted", evidence_ids=[ev["evidence_id"]], paper_ids=[p["paper_id"]], owner="A", source_origin=["CVF"], project_id="mxh_cv_700")
    data["edges.csv"].append(edge)
    manifest.update(node_count=len(data["nodes.csv"]), edge_count=len(data["edges.csv"]), rule_versions={rule:"1.0.0"})
    return edge, ev, t


class ChecksTest(unittest.TestCase):
    def test_valid_metadata_has_no_confirmed_error(self):
        with temporary_workspace() as root:
            data, manifest, _ = graph_fixture(root)
            f = Findings()
            graph_checks(data, manifest, f)
            self.assertFalse([r for r in f.rows.values() if r["finding_kind"] == "error"])

    def test_dangling_duplicate_direction_and_self_loop(self):
        for change, expected in (("missing", "missing_endpoint"), ("duplicate", "duplicate_edge"), ("reverse", "edge_direction_or_labels"), ("loop", "self_loop_or_order")):
            with self.subTest(change=change), temporary_workspace() as root:
                data, manifest, _ = graph_fixture(root)
                edge = next(e for e in data["edges.csv"] if e["type"] == "AUTHORED")
                if change == "missing":
                    edge["dst"] = "missing:paper"
                elif change == "duplicate":
                    data["edges.csv"].append(deepcopy(edge))
                elif change == "reverse":
                    edge["src"], edge["dst"] = edge["dst"], edge["src"]
                else:
                    edge["dst"] = edge["src"]
                f = Findings()
                graph_checks(data, manifest, f)
                self.assertIn(expected, {r["check_id"] for r in f.rows.values()})

    def test_collaboration_distinct_papers_not_evidence_count(self):
        with temporary_workspace() as root:
            data, manifest, _ = graph_fixture(root)
            e = next(e for e in data["edges.csv"] if e["type"] == "COAUTHORED_WITH")
            e["paper_ids"] *= 2
            e["weight"] = 2
            f = Findings()
            graph_checks(data, manifest, f)
            self.assertIn("derived_weight", {r["check_id"] for r in f.rows.values()})

    def test_one_author_two_institutions_does_not_support_collaboration(self):
        with temporary_workspace() as root:
            data, manifest, _ = graph_fixture(root)
            first = data["authorships.csv"][0]
            second = {**first, "institution_id": data["authorships.csv"][1]["institution_id"]}
            data["authorships.csv"] = [first, second]
            self.assertFalse(any(k[1] == "COLLABORATED_WITH" for k in expected_metadata(data)))
            f = Findings()
            graph_checks(data, manifest, f)
            self.assertTrue(any(r["check_id"] == "independent_relation_support" for r in f.rows.values()))

    def test_citation_count_cannot_create_reference_edge(self):
        with temporary_workspace() as root:
            data, manifest, _ = graph_fixture(root)
            p = data["papers.jsonl"][0]
            q = {**p, "paper_id": p["paper_id"] + "_second", "openalex_id":"https://openalex.org/W999"}
            data["papers.jsonl"].append(q)
            data["paper_registry.csv"].append({**data["paper_registry.csv"][0], "paper_id": q["paper_id"]})
            pn = next(n for n in data["nodes.csv"] if n["label"] == "Paper")
            data["nodes.csv"].append({**pn, "id": q["paper_id"]})
            p["citation_count"], p["referenced_works"] = 100000, []
            e = dict(edge_id=identifier("edge", p["paper_id"], "CITES", q["paper_id"]), src=p["paper_id"], type="CITES", dst=q["paper_id"], weight=1,
                derivation="metadata", validation_status="accepted", evidence_ids=[data["evidence.jsonl"][0]["evidence_id"]], paper_ids=[p["paper_id"]], owner="A", source_origin=["CVF"], project_id="mxh_cv_700")
            data["edges.csv"].append(e)
            f = Findings()
            graph_checks(data, manifest, f)
            self.assertTrue(any(r["check_id"] == "independent_relation_support" and r["category"] == "citation" for r in f.rows.values()))
            p["referenced_works"], p["references_status"] = [q["openalex_id"]], "verified"
            self.assertEqual(expected_metadata(data)[(p["paper_id"], "CITES", q["paper_id"])], {p["paper_id"]})

    def test_unicode_offset_and_rule_version_failures(self):
        for change in ("offset", "version", "paper"):
            with self.subTest(change=change), temporary_workspace() as root:
                data, manifest, _ = graph_fixture(root)
                edge, ev, text = add_nlp(data, manifest, "Résumé 🚀. We evaluate on COCO.")
                if change == "offset":
                    ev["start_char"] += 1
                elif change == "version":
                    ev["rule_version"] = "stale"
                else:
                    ev["paper_id"] = "other:paper"
                f = Findings()
                graph_checks(data, manifest, f)
                self.assertIn("nlp_binding_or_offset", {r["check_id"] for r in f.rows.values()})

    def test_baseline_related_work_and_dataset_pretraining_are_risks_not_votes(self):
        for sentence in ("Previous work evaluates on COCO.", "We compare a baseline on COCO.", "We pretrain on COCO."):
            with self.subTest(sentence=sentence), temporary_workspace() as root:
                data, manifest, _ = graph_fixture(root)
                add_nlp(data, manifest, sentence)
                f = Findings()
                graph_checks(data, manifest, f)
                risk = next(r for r in f.rows.values() if r["check_id"] == "nlp_context_risk")
                self.assertEqual((risk["finding_kind"], risk["owner"]), ("review_risk", "A"))
                self.assertIn(sentence, risk["evidence_text"])

    def test_pretrained_method_is_not_a_dataset_training_false_positive(self):
        with temporary_workspace() as root:
            data, manifest, _ = graph_fixture(root)
            add_nlp(data, manifest, "We use a pretrained diffusion model.", "USES_METHOD")
            f = Findings()
            graph_checks(data, manifest, f)
            self.assertFalse(any(r["check_id"] == "nlp_context_risk" for r in f.rows.values()))

    def test_wrong_paper_affiliation_source_and_missing_review_log(self):
        with temporary_workspace() as root:
            cfg, _, data, bodies = fixture(root)
            row = data["authorships.csv"][0]
            row["affiliation_source_record_id"] = "nonexistent:source"
            row["identity_status"] = "needs_review"
            data["needs_review.csv"] = []
            f = Findings()
            corpus_checks(data, dict(owner="A", target=1, conference="CVPR", year=2024), f, bodies)
            self.assertTrue({"affiliation_paper_source", "unlogged_ambiguous_authorship"} <= {r["check_id"] for r in f.rows.values()})

    def test_duplicate_doi_arxiv_and_homonyms_remain_review_candidates(self):
        with temporary_workspace() as root:
            data, _, _ = graph_fixture(root)
            other = deepcopy(data)
            other["papers.jsonl"][0]["paper_id"] += "_other"
            data["papers.jsonl"][0]["arxiv_url"] = "https://arxiv.org/abs/2401.12345v1"
            other["papers.jsonl"][0]["arxiv_url"] = "https://arxiv.org/abs/2401.12345v2"
            author = next(n for n in data["nodes.csv"] if n["label"] == "Author")
            author["properties_json"]["orcid"] = "0000-0002-1825-0097"
            next(n for n in other["nodes.csv"] if n["id"] == author["id"])["properties_json"]["orcid"] = "0000-0002-1694-233X"
            data["nodes.csv"].append({**author, "id":"author:openalex:A999"})
            f = Findings()
            original = deepcopy(data)
            risks = identity_risks([data, other], data, f)
            self.assertTrue(any(r["check_id"] == "shared_identifier" for r in f.rows.values()))
            self.assertTrue(any(r["check_id"] == "canonical_property_conflict" for r in f.rows.values()))
            self.assertIn("author:openalex:A999", risks)
            self.assertEqual(original, data)
            self.assertTrue(all(r["finding_kind"] == "review_risk" for r in f.rows.values()))


class SamplingTest(unittest.TestCase):
    def fixture(self, root):
        data, manifest, _ = graph_fixture(root)
        cfg = dict(seed=20261103, edges_per_type=10, cross_reviews_per_person=2, node_count=3)
        f = Findings()
        risks = identity_risks([data], data, f)
        return data, manifest, cfg, f, risks

    def test_seed_reproducible_input_order_independent_and_sparse_types(self):
        with temporary_workspace() as root:
            data, manifest, cfg, f, risks = self.fixture(root)
            first = samples(data, manifest, list(f.rows.values()), risks, cfg)
            data["nodes.csv"].reverse()
            data["edges.csv"].reverse()
            second = samples(data, manifest, list(f.rows.values()), risks, cfg)
            self.assertEqual(first, second)
            self.assertEqual(first[2]["strata"]["AUTHORED"]["sampled"], 2)
            self.assertEqual(first[2]["strata"]["CITES"]["sampled"], 0)
            self.assertEqual(len({e["edge_id"] for e in first[0] if e["review_phase"] == "primary"}), first[2]["unique_edges"])

    def test_primary_balanced_cross_uses_other_person_and_all_pending(self):
        with temporary_workspace() as root:
            data, manifest, cfg, f, risks = self.fixture(root)
            edges, nodes, stats = samples(data, manifest, list(f.rows.values()), risks, cfg)
            primary = {e["edge_id"]:e for e in edges if e["review_phase"] == "primary"}
            self.assertLessEqual(abs(stats["primary_by_reviewer"]["A"] - stats["primary_by_reviewer"]["B"]), 1)
            for e in edges:
                if e["review_phase"] == "cross":
                    self.assertNotEqual(e["assigned_reviewer"], primary[e["edge_id"]]["assigned_reviewer"])
            self.assertTrue(all(e["review_status"] == "pending_review" and not e["reviewer_name"] and not e["reviewed_at"] for e in edges + nodes))
            human = human_summary(decode_csv(csv_bytes(EDGE_FIELDS, edges)), decode_csv(csv_bytes(NODE_FIELDS, nodes)))
            self.assertIsNone(human["primary"]["conservative_precision"])
            self.assertFalse(human["human_audit_complete"])

    def test_conservative_denominator_excludes_pending_includes_unverifiable(self):
        rows = []
        for i, status in enumerate(("correct", "incorrect", "unverifiable", "pending_review")):
            rows.append(dict(sample_id=str(i), edge_id=str(i), assigned_reviewer="A", review_phase="primary", **pending()))
            rows[-1].update(review_status=status, reviewer_name="Fixture reviewer", reviewed_at="2026-11-10T10:00:00+07:00", error_group="other", review_notes="Synthetic test judgment")
        summary = human_summary(rows, [])
        self.assertEqual(summary["primary"]["graded"], 3)
        self.assertAlmostEqual(summary["primary"]["conservative_precision"], 1/3)

    def test_graded_rows_require_real_fields_and_known_status(self):
        row = dict(sample_id="one", assigned_reviewer="A", edge_id="e", review_phase="primary", **pending())
        for change in ({"review_status":"all_good"}, {"review_status":"correct"}, {"review_status":"unverifiable", "reviewer_name":"Test", "reviewed_at":"2026-11-10T00:00:00Z"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                human_summary([{**row, **change}], [])

    def test_only_human_columns_can_change_fingerprint(self):
        with temporary_workspace() as root:
            data, manifest, cfg, f, risks = self.fixture(root)
            edges, _, _ = samples(data, manifest, list(f.rows.values()), risks, cfg)
            rows = decode_csv(csv_bytes(EDGE_FIELDS, edges))
            original = form_fingerprint(rows)
            rows[0]["review_notes"] = "Human note"
            self.assertEqual(original, form_fingerprint(rows))
            rows[0]["edge_id"] = "wrong"
            self.assertNotEqual(original, form_fingerprint(rows))

    def test_cross_disagreement_is_reported_and_blocks_clear_human_findings(self):
        def row(sid, person, phase, status):
            return dict(sample_id=sid, edge_id="same-edge", assigned_reviewer=person, review_phase=phase,
                        review_status=status, error_group="other", review_notes="Synthetic human judgment", reviewer_name="Test reviewer " + person,
                        reviewed_at="2026-11-10T12:00:00+07:00")
        result = human_summary([row("p", "A", "primary", "correct"), row("c", "B", "cross", "unverifiable")], [])
        self.assertEqual(result["cross_disagreements"], ["same-edge"])
        self.assertFalse(result["human_findings_clear"])


class FailureTest(unittest.TestCase):
    def test_missing_inputs_block_audit_and_never_pass_or_create_fake_samples(self):
        with temporary_workspace() as root:
            cfg = json.loads((REPO_ROOT / "config/a6_audit.json").read_text())
            (root / "config").mkdir()
            (root / "config/a6.json").write_bytes(json_bytes(cfg))
            result = run(root, "config/a6.json")
            self.assertFalse(result["automatic_checks_passed"])
            self.assertFalse(result["checks_execution_complete"])
            self.assertFalse(result["ready_for_a7"])
            folder = root / cfg["output_dir"]
            self.assertEqual(decode_csv((folder / "a6_edge_audit_sample.csv").read_bytes()), [])
            self.assertEqual(run(root, "config/a6.json"), result)
            summary = summarize(root, "config/a6.json")
            self.assertFalse(summary["ready_for_a7"])
            self.assertEqual(run(root, "config/a6.json"), result)
            fake = {key: "" for key in EDGE_FIELDS}
            fake.update(sample_id="unauthorized", edge_id="fake", assigned_reviewer="A", review_phase="primary", **pending())
            (folder / "a6_edge_audit_sample.csv").write_bytes(csv_bytes(EDGE_FIELDS, [fake]))
            with self.assertRaisesRegex(ValueError, "Immutable audit fields"):
                summarize(root, "config/a6.json")


if __name__ == "__main__":
    unittest.main()
