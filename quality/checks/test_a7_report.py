"""Reporting invariants: denominators, identity union, evidence and update safety."""
import copy
import json
import unittest
from unittest.mock import patch

from src.collect.common import REPO_ROOT
from src.reporting.a7 import ratio, corpus_metrics, combined_metrics, render_report, examples, audit_metrics, report_blocks
from src.audit.pipeline import EDGE_FILE, NODE_FILE
from src.nlp.validation import read_manifest
from test_a2_support import temporary_workspace


def corpus(owner="A"):
    """Two byline occurrences, three affiliation rows, one unresolved author."""
    paper = dict(paper_id="p:" + owner, owner=owner, conference="CVPR" if owner == "A" else "ICCV",
        conference_year=2024 if owner == "A" else 2023, scope="core", track="main", doi=None,
        abstract="An abstract", openalex_id=None, arxiv_url=None, cvf_url="https://cvf/" + owner,
        authors=[{"authorship_id": owner + ":1"}, {"authorship_id": owner + ":2"}])
    data = {"papers.jsonl": [paper], "paper_registry.csv": [dict(paper_id=paper["paper_id"], status="cvf_verified")],
        "authorships.csv": [dict(authorship_id=owner + ":1", author_id="author:shared", institution_id=i,
            affiliation_status="verified") for i in ("institution:shared", "institution:" + owner)] +
            [dict(authorship_id=owner + ":2", author_id=None, institution_id=None, affiliation_status="missing")],
        "nodes.csv": [dict(id="author:shared", label="Author", properties_json={})] +
            [dict(id=i, label="Institution", properties_json={}) for i in ("institution:shared", "institution:" + owner)],
        "needs_review.csv": [{"review_status": "open"}], "merge_log.jsonl": [{"action": "link"}]}
    scope = dict(owner=owner, conference=paper["conference"], year=paper["conference_year"], target=1)
    return data, scope


def merged(a, b):
    result = {key: a[key] + b[key] for key in ("papers.jsonl", "authorships.csv")}
    result["nodes.csv"] = list({n["id"]: n for n in a["nodes.csv"] + b["nodes.csv"]}.values())
    return result


class A7StatisticsTests(unittest.TestCase):
    def test_authorship_denominator_ignores_multi_affiliation_rows(self):
        d, s = corpus()
        m = corpus_metrics(d, s)
        self.assertEqual((m["distinct_authorships"], m["authorship_rows"]), (2, 3))
        self.assertEqual(m["coverage"]["affiliation"]["denominator"], 2)
        self.assertEqual(m["coverage"]["affiliation"]["percent"], 50)
        self.assertEqual(m["multi_institution_authorships"], 1)

    def test_missing_is_complement_with_explicit_denominator(self):
        v = ratio(328, 350)
        self.assertEqual((v["missing"], v["percent"], v["missing_percent"]), (22, 93.71, 6.29))
        self.assertIsNone(ratio(0, 0)["percent"])
        with self.assertRaises(ValueError):
            ratio(351, 350)

    def test_core_papers_and_registry_cannot_be_double_counted(self):
        d, s = corpus()
        d["papers.jsonl"] *= 2
        with self.assertRaisesRegex(ValueError, "duplicated"):
            corpus_metrics(d, s)

    def test_workshop_is_not_core(self):
        d, s = corpus()
        d["papers.jsonl"][0]["track"] = "workshop"
        with self.assertRaisesRegex(ValueError, "core/main"):
            corpus_metrics(d, s)

    def test_absent_abstract_and_links_are_missing_not_zero_population(self):
        d, s = corpus()
        d["papers.jsonl"][0]["abstract"] = None
        m = corpus_metrics(d, s)
        self.assertEqual((m["coverage"]["abstract"]["numerator"], m["coverage"]["abstract"]["denominator"]), (0, 1))
        self.assertEqual(m["coverage"]["abstract"]["missing_percent"], 100)

    def test_shared_people_and_institutions_use_union_not_sum(self):
        a, _ = corpus("A")
        b, _ = corpus("B")
        m = combined_metrics([a, b], merged(a, b))
        self.assertEqual((m["core_papers"], m["distinct_authors"], m["distinct_institutions"]), (2, 1, 3))
        self.assertEqual(m["shared_canonical_ids"], {"Author": 1, "Institution": 1})

    def test_conflicting_cross_corpus_doi_blocks_total(self):
        a, _ = corpus("A")
        b, _ = corpus("B")
        for d in (a, b):
            d["papers.jsonl"][0]["doi"] = "10.1234/same"
        with self.assertRaisesRegex(ValueError, "identifier collision"):
            combined_metrics([a, b], merged(a, b))

    def test_new_metadata_leaves_old_graph_pending_instead_of_false_total(self):
        a, _ = corpus("A")
        b, _ = corpus("B")
        g = copy.deepcopy(merged(a, b))
        b["papers.jsonl"][0]["abstract"] = "Updated by B"
        self.assertEqual(combined_metrics([a, b], g)["status"], "PENDING_B")

    def test_shared_id_with_conflicting_orcid_is_not_silently_merged(self):
        a, _ = corpus("A")
        b, _ = corpus("B")
        a["nodes.csv"][0]["properties_json"]["orcid"] = "0000-0001-0000-0001"
        b["nodes.csv"][0]["properties_json"]["orcid"] = "0000-0002-0000-0002"
        self.assertEqual(combined_metrics([a, b], merged(a, b))["status"], "PENDING_B")


class A7ReportingTests(unittest.TestCase):
    def test_missing_b_is_explicit_pending_and_has_no_invented_counts(self):
        a, s = corpus()
        a = corpus_metrics(a, s)
        a.update(manifest="a.json", snapshot_id="snapshot:a", cleaning={"duplicate_papers_removed": 0, "papers_with_identifier_conflicts": 0})
        m = dict(corpora={"A": a, "B": dict(status="PENDING_B", owner="B", conference="ICCV", year=2023)},
            combined=dict(status="PENDING_B", reason="B is missing"), graph=dict(status="PENDING_B"),
            nlp=dict(status="PENDING_B"), audit=dict(status="PENDING_B"), examples=[], pending_b=[])
        blocks = report_blocks(m)
        self.assertIn("PENDING_B", blocks["coverage"])
        self.assertIn("PENDING_B", blocks["corpora"])
        self.assertIn("Chưa công bố tổng", blocks["combined"])

    def test_real_examples_reference_exact_source_slices(self):
        _, graph = read_manifest(REPO_ROOT, "data/processed/mxh_cv_700/graph_b5/snapshot_manifest.json")
        _, nlp = read_manifest(REPO_ROOT, "data/processed/mxh_cv_700/b5/snapshot_manifest.json")
        selected = examples(graph, nlp)
        evs = {e["evidence_id"]: e for e in nlp["evidence.jsonl"]}
        self.assertEqual(len(selected), 4)
        self.assertEqual({r["decision"] for r in selected}, {"accepted", "rejected_by_rule"})
        for row in selected:
            self.assertIn(row["excerpt"], evs[row["evidence_id"]]["evidence_text"])
            self.assertLessEqual(len(row["excerpt"].split()), 18)

    def test_report_updates_only_machine_blocks(self):
        text = "Academic prose edited by B\n<!-- A7:n:BEGIN -->\nold\n<!-- A7:n:END -->\nEnd"
        with patch("src.reporting.a7.report_blocks", return_value={"n": "new 42/50"}):
            result = render_report(text, {})
            self.assertTrue(result.startswith("Academic prose edited by B\n"))
            self.assertTrue(result.endswith("\nEnd"))
            self.assertIn("new 42/50", result)

    def test_missing_or_duplicated_markers_fail_without_overwriting_prose(self):
        marker = "<!-- A7:n:BEGIN --><!-- A7:n:END -->"
        with patch("src.reporting.a7.report_blocks", return_value={"n": "new"}):
            for text in ("none", marker * 2):
                with self.assertRaisesRegex(ValueError, "marker"):
                    render_report(text, {})

    def test_changed_audit_receipt_is_stale_not_passed(self):
        with temporary_workspace() as root:
            (root / "outputs/a6").mkdir(parents=True)
            (root / "audit.json").write_text(json.dumps({"output_dir": "outputs/a6"}), encoding="utf-8")
            (root / "outputs/a6/a6_run_manifest.json").write_text(json.dumps({"code_version": "old"}), encoding="utf-8")
            self.assertEqual(audit_metrics(root, "audit.json")["status"], "stale")

    def test_pending_human_reviews_remain_null_and_read_only(self):
        files = [REPO_ROOT / "outputs/a6" / n for n in (EDGE_FILE, NODE_FILE, "a6_human_summary.json")]
        before = [p.read_bytes() for p in files]
        m = audit_metrics(REPO_ROOT, "config/a6_audit.json")
        self.assertEqual(m["status"], "available")
        # Do not assume humans remain pending when they grade the real forms later.
        h = m["human"]
        if h["primary"]["graded"] == 0:
            self.assertIsNone(h["primary"]["conservative_precision"])
        self.assertEqual(before, [p.read_bytes() for p in files])


if __name__ == "__main__":
    unittest.main()
