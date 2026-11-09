"""A4 rules, exact evidence binding, deterministic export and B3/B4 integration."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from src.nlp.pipeline import extract, run
from src.nlp.rules import Extractor
from src.nlp.validation import read_manifest, validate_nlp, TABLES, verify_graph_contract, load_inputs
from src.nlp.verify import verify
from contract_v2.text import evidence_id, identifier, sha256, canonical_json, validate_nlp_evidence
from src.collect.common import REPO_ROOT, record_bytes, json_bytes
from src.collect.contract import contract, validate_records, load_records
from src.collect.export import export_records
from src.collect.pilot import snapshot_payload
from src.graph.export_graph import export, build
from src.graph.load_neo4j import read_snapshot
from test_a3_clean import observation, source, STAMP
from test_a2_support import temporary_workspace


def fixture(title="Object Detection with Features", abstract="We evaluate our model on COCO. We test on MS COCO.", conference="CVPR", root=None):
    year, owner = (2024, "A") if conference == "CVPR" else (2023, "B")
    obs = observation(pid=f"cvf:{conference}{year}:fixture")
    obs.update(title=title, title_raw=title, abstract=abstract, abstract_raw=abstract, conference=conference,
               conference_year=year, owner=owner, venue_id=f"venue:{conference}{year}",
               cvf_url=f"https://openaccess.thecvf.com/content/{conference}{year}/html/fixture_paper.html")
    # Explicitly synthetic raw fixture, never used as evidence for corpus papers.
    raw = (f"<title>{title}</title><abstract>{abstract}</abstract>").encode()
    src = source("", obs["paper_id"])
    src.update(url=obs["cvf_url"], content_sha256=sha256(raw), raw_path=f"data/raw/{conference}/fixture.html.gz")
    src["source_record_id"] = identifier("source:cvf", src["url"], src["content_sha256"])
    obs.update(source_record_id=src["source_record_id"])
    records = export_records([obs], [src], src)
    if root:
        path = root / src["raw_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(raw, mtime=0))
    # Resolved fixture authors/institutions make both B4 relation types observable.
    for i, a in enumerate(records["authorships.csv"], 1):
        a.update(author_id=f"author:openalex:A{i}", institution_id=f"institution:openalex:I{i}",
                 identity_status="resolved", affiliation_status="verified", identity_source_record_id=src["source_record_id"],
                 affiliation_source_record_id=src["source_record_id"])
        for label, entity_id in (("Author", a["author_id"]), ("Institution", a["institution_id"])):
            records["nodes.csv"].append(dict(id=entity_id, label=label, name=entity_id, owner=owner,
                source_origin=["CVF"], source_record_ids=[src["source_record_id"]], validation_status="accepted", project_id="mxh_cv_700", properties_json={}))
    ev = dict(evidence_kind="metadata", paper_id=obs["paper_id"], source_record_id=src["source_record_id"], source_url=src["url"],
        field_path="html:title.text", evidence_text=title, start_char=None, end_char=None, rule_id="fixture-metadata", rule_version="1",
        captured_at=STAMP, supporting_evidence_ids=[], owner=owner, text_version_id=None, normalized_text_sha256=None, normalization_version=None)
    ev["evidence_id"] = evidence_id(ev)
    records["evidence.jsonl"] = [ev]
    return records


def write_snapshot(root, directory, records):
    spec, files = contract(), []
    for name, rows in records.items():
        validate_records(name, rows)
        body = record_bytes(name, spec["files"][name]["fields"], rows)
        path = directory + "/" + name
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(body)
        files.append(dict(path=path, sha256=sha256(body), record_count=len(rows), role=spec["files"][name]["stage"]))
    m = dict(project_id="mxh_cv_700", schema_version="2.0.0", code_version="fixture", normalization_version="nfc-ws-1",
        parser_versions=["cvf-html-1.0.0"], rule_versions={}, dictionary_versions={}, applied_decision_ids=[d["decision_id"] for d in records["merge_log.jsonl"]],
        graph_ready=False, node_count=None, edge_count=None, files=files, created_at=STAMP, source_snapshot_id="snapshot:v2:fixture")
    m["snapshot_id"] = "snapshot:v2:" + sha256(canonical_json(snapshot_payload(m)).encode())
    (root / directory / "snapshot_manifest.json").write_bytes(json_bytes(m))
    return m


def setup_pipeline(root):
    records = fixture(root=root)
    write_snapshot(root, "data/processed/snaps/s1", records)
    write_snapshot(root, "data/processed/a3", records)
    cfg = dict(input_manifests=["data/processed/a3/snapshot_manifest.json"], output_dir="data/processed/a4",
               dictionary="config/dictionary.json", model="blank")
    (root / "config").mkdir()
    (root / "config/dictionary.json").write_bytes((REPO_ROOT / "config/a4_dictionary.json").read_bytes())
    (root / "config/a4.json").write_bytes(json_bytes(cfg))
    graph = dict(project_id="mxh_cv_700", code_version="test", output_dir="data/processed/graph",
                 inputs=[dict(name="test", snapshots_dir="data/processed/snaps", a3_dir="data/processed/a3")])
    return cfg, graph, records


class RulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor = Extractor(model="blank")

    def check_cases(self, name):
        cases = json.loads((REPO_ROOT / "quality/fixtures" / name).read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(text=case["text"], group=case["group"]):
                actual = sorted({c.entity_id for c in self.extractor.candidates(case["text"], case["field"]) if c.rule_id})
                self.assertEqual(actual, sorted(case["expected"]))

    def test_development_cases(self):
        self.check_cases("a4_dev.json")

    def test_held_out_cases(self):
        self.check_cases("a4_eval.json")

    def test_evaluation_texts_separate(self):
        dev, evaluation = [json.loads((REPO_ROOT / "quality/fixtures" / n).read_text()) for n in ("a4_dev.json", "a4_eval.json")]
        self.assertFalse({c["text"] for c in dev} & {c["text"] for c in evaluation})

    def test_no_global_names_acronyms_or_partial_tokens(self):
        self.assertFalse(list(self.extractor.candidates("We study SR and classification. We evaluate on COCOA.", "abstract")))

    def test_auto_without_model_uses_offline_fallback(self):
        with patch("spacy.util.is_package", return_value=False):
            self.assertEqual(Extractor(model="auto").model, "blank")


class EvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extractor = Extractor(model="blank")

    def setUp(self):
        self.original = fixture(abstract="Résumé 🚀. We evaluate our model on COCO. We test on MS COCO.")
        self.data, self.summary = extract(self.original, self.extractor)
        self.e = next(e for e in self.data["evidence.jsonl"] if e["rule_id"].startswith("a4-dataset"))
        self.t = next(t for t in self.original["text_versions.jsonl"] if t["text_version_id"] == self.e["text_version_id"])

    def test_unicode_slice_and_canonical_validator(self):
        validate_nlp_evidence(self.e, self.t)
        self.assertEqual(self.e["evidence_kind"], "nlp")
        self.assertEqual(self.e["start_char"], len("Résumé 🚀. "))
        self.assertEqual(self.t["normalized_text"][self.e["start_char"]:self.e["end_char"]], self.e["evidence_text"])

    def test_bad_offsets_rejected(self):
        for change in ({"start_char": self.e["start_char"] + 1}, {"end_char": 100000}, {"start_char": -1}, {"start_char": 1.0}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_nlp_evidence({**self.e, **change}, self.t)

    def test_wrong_text_version_paper_source_hash_rejected(self):
        for key in ("text_version_id", "paper_id", "source_record_id", "field_path", "normalization_version", "normalized_text_sha256"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_nlp_evidence({**self.e, key: "incorrect"}, self.t)
        with self.assertRaises(ValueError):
            validate_nlp_evidence(self.e, {**self.t, "normalized_text": "changed"})

    def test_required_fields_rejected_by_contract_schema(self):
        for key in ("evidence_kind", "text_version_id", "rule_id", "start_char", "end_char", "evidence_text"):
            bad = {k: v for k, v in self.e.items() if k != key}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_records("evidence.jsonl", [bad])

    def test_aliases_one_edge_multiple_evidence_and_stable_ids(self):
        edges = [e for e in self.data["edges.csv"] if e["type"] == "EVALUATED_ON"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(len(edges[0]["evidence_ids"]), 2)
        self.assertEqual(len(self.data["nodes.csv"]), 2)
        self.assertEqual(self.data, extract(self.original, self.extractor)[0])
        self.assertEqual((edges[0]["derivation"], edges[0]["weight"]), ("nlp", 1))
        self.assertEqual({n["id"] for n in self.data["nodes.csv"]}, {e["dst"] for e in self.data["edges.csv"]})

    def test_wrong_or_missing_text_and_disputed_provenance_are_reviewed(self):
        for change in ("missing", "other_paper", "hash", "provenance", "field"):
            original = deepcopy(self.original)
            text = next(t for t in original["text_versions.jsonl"] if t["text_version_id"] == self.t["text_version_id"])
            if change == "missing":
                original["text_versions.jsonl"].remove(text)
            elif change == "other_paper":
                text["paper_id"] = "cvf:OTHER"
            elif change == "hash":
                text["normalized_text"] += "garbage"
            elif change == "field":
                original["papers.jsonl"][0]["abstract_text_version_id"] = original["papers.jsonl"][0]["title_text_version_id"]
            else:
                next(p for p in original["field_provenance.csv"] if p["field_name"] == "abstract")["validation_status"] = "needs_review"
            data, stats = extract(original, self.extractor)
            with self.subTest(change=change):
                self.assertFalse(any(e["type"] == "EVALUATED_ON" for e in data["edges.csv"]))
                self.assertEqual(stats["invalid_fields"], 1)

    def test_bad_endpoints_duplicates_cross_paper_and_source_url_rejected(self):
        for change in ("node", "duplicate", "paper", "source_url", "orphan"):
            data = deepcopy(self.data)
            if change == "node":
                data["nodes.csv"].pop()
            elif change == "duplicate":
                data["edges.csv"].append(data["edges.csv"][0])
            elif change == "paper":
                data["edges.csv"][0]["src"] = "cvf:OTHER"
            elif change == "orphan":
                data["edges.csv"] = []
            else:
                data["evidence.jsonl"][0]["source_url"] = "https://wrong.example/"
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_nlp(data, self.original)

    def test_iccv_and_cvpr_share_rules_and_dictionary(self):
        data, summary = extract(fixture(conference="ICCV"), self.extractor)
        self.assertEqual({e["type"] for e in data["edges.csv"]}, {"STUDIES_TASK", "EVALUATED_ON"})
        self.assertTrue(all(e["src"].startswith("cvf:ICCV2023:") and e["owner"] == "B" for e in data["edges.csv"]))


class IntegrationTest(unittest.TestCase):
    def test_export_contract_loader_reader_and_repeat_preserve_b3_b4(self):
        with temporary_workspace() as root:
            cfg, graph, original = setup_pipeline(root)
            base_nodes, base_edges, *_ = build(graph, root)
            summary = run(root, "config/a4.json")
            self.assertFalse(summary["graph_ready"])
            self.assertTrue(verify(root, "config/a4.json")["passed"])
            self.assertEqual(summary, run(root, "config/a4.json"))
            graph["nlp_manifest"] = cfg["output_dir"] + "/snapshot_manifest.json"
            manifest, report = export(graph, root)
            self.assertTrue(report["contract_validation"]["passed"])
            self.assertTrue(manifest["graph_ready"])
            _, tables = read_manifest(root, graph["output_dir"] + "/snapshot_manifest.json", contract()["files"])
            self.assertEqual(base_edges, [e for e in tables["edges.csv"] if e["derivation"] != "nlp"])
            self.assertEqual(base_nodes, [n for n in tables["nodes.csv"] if n["label"] not in ("Task", "Dataset")])
            self.assertTrue({"COAUTHORED_WITH", "COLLABORATED_WITH", "STUDIES_TASK", "EVALUATED_ON"} <= set(manifest["counts_by_type"]))
            self.assertEqual(len(tables["evidence.jsonl"]), len(original["evidence.jsonl"]) + summary["evidence"])
            self.assertTrue(verify_graph_contract(root, manifest)["passed"])
            self.assertEqual(read_snapshot(root / graph["output_dir"], "mxh_cv_700")[0], manifest)
            before = {p.name: p.read_bytes() for p in (root / graph["output_dir"]).iterdir()}
            self.assertEqual(export(graph, root)[0], manifest)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / graph["output_dir"]).iterdir()})

    def test_bad_source_bytes_fail_without_output(self):
        with temporary_workspace() as root:
            cfg, graph, original = setup_pipeline(root)
            source = root / original["source_records.jsonl"][0]["raw_path"]
            source.write_bytes(gzip.compress(b"corrupt", mtime=0))
            with self.assertRaisesRegex(ValueError, "Raw source"):
                run(root, "config/a4.json")
            self.assertFalse((root / cfg["output_dir"]).exists())

    def test_missing_evidence_refuses_graph_publication(self):
        with temporary_workspace() as root:
            cfg, graph, original = setup_pipeline(root)
            run(root, "config/a4.json")
            graph["nlp_manifest"] = cfg["output_dir"] + "/snapshot_manifest.json"
            with patch("src.graph.export_graph.build", wraps=build) as mocked:
                nodes, edges, manifests, inputs, report = build(graph, root)
                edges[0]["evidence_ids"] = []
                mocked.side_effect = None
                mocked.return_value = nodes, edges, manifests, inputs, report
                with self.assertRaisesRegex(ValueError, "Edge evidence missing"):
                    export(graph, root)
            self.assertFalse((root / graph["output_dir"]).exists())

    def test_manifest_and_table_tampering_rejected(self):
        with temporary_workspace() as root:
            cfg, graph, _ = setup_pipeline(root)
            run(root, "config/a4.json")
            p = root / cfg["output_dir"] / "evidence.jsonl"
            p.write_bytes(p.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify(root, "config/a4.json")
            graph["nlp_manifest"] = cfg["output_dir"] + "/snapshot_manifest.json"
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                export(graph, root)
            self.assertFalse((root / graph["output_dir"]).exists())

    def test_refuses_overwrite_and_stale_source_snapshot(self):
        with temporary_workspace() as root:
            cfg, graph, original = setup_pipeline(root)
            run(root, "config/a4.json")
            (root / cfg["output_dir"] / "summary.json").write_text("different", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                run(root, "config/a4.json")
            original["paper_registry.csv"][0]["verified_at"] = "2026-11-09T00:00:00Z"
            write_snapshot(root, "data/processed/a3", original)
            graph["nlp_manifest"] = cfg["output_dir"] + "/snapshot_manifest.json"
            with self.assertRaisesRegex(ValueError, "input snapshot mismatch"):
                export(graph, root)

    def test_cross_corpus_alias_conflicts_are_reviewed_without_identity_merge(self):
        with temporary_workspace() as root:
            cfg, graph, records = setup_pipeline(root)
            aid = identifier("alias", "Author", "ORCID", "0000-0000-0000-0001")
            for i in (1, 2):
                data = deepcopy(records)
                did, author = f"decision:fixture{i}", f"author:openalex:A{i}"
                data["alias_map.csv"] = [dict(alias_id=aid, entity_type="Author", source="ORCID", external_id="0000-0000-0000-0001",
                    canonical_id=author, decision_id=did)]
                data["merge_log.jsonl"] = [dict(decision_id=did, action="link", entity_type="Author", input_ids=[aid], output_ids=[author],
                    affected_paper_ids=[data["papers.jsonl"][0]["paper_id"]], affected_authorship_ids=[],
                    changes=[dict(table="alias_map.csv", record_key={"alias_id": aid}, field="canonical_id", before=None, after=author)],
                    reason="synthetic fixture", evidence_ids=[data["evidence.jsonl"][0]["evidence_id"]], proposed_by="fixture",
                    reviewed_by="fixture", review_mode="rule", decided_at=STAMP, snapshot_before=None, reverts_decision_id=None)]
                write_snapshot(root, f"data/processed/input{i}", data)
            _, merged = load_inputs(root, [f"data/processed/input{i}/snapshot_manifest.json" for i in (1, 2)], include_identity=True)
            self.assertFalse(merged["alias_map.csv"])
            self.assertEqual(len(merged["merge_log.jsonl"]), 2)
            self.assertEqual(merged["needs_review.csv"][0]["candidate_ids"], ["author:openalex:A1", "author:openalex:A2"])
            self.assertEqual(merged["authorships.csv"], sorted(records["authorships.csv"], key=canonical_json))
            # Use the two manifests as inputs to the existing graph exporter.
            # The fixture repeats the same paper, so the base exporter deduplicates it.
            cfg["input_manifests"] = [f"data/processed/input{i}/snapshot_manifest.json" for i in (1, 2)]
            (root / "config/a4.json").write_bytes(json_bytes(cfg))
            run(root, "config/a4.json")
            graph["inputs"] = [dict(name=str(i), snapshots_dir="data/processed/snaps", a3_dir=f"data/processed/input{i}") for i in (1, 2)]
            graph["nlp_manifest"] = cfg["output_dir"] + "/snapshot_manifest.json"
            manifest, report = export(graph, root)
            self.assertFalse(set(manifest["applied_decision_ids"]) & {"decision:fixture1", "decision:fixture2"})
            self.assertEqual(report["unapplied_alias_decision_ids"], ["decision:fixture1", "decision:fixture2"])
            self.assertTrue(report["contract_validation"]["passed"])


if __name__ == "__main__":
    unittest.main()
