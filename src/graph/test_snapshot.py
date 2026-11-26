import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.graph import snapshot as sn
from contract_v2.text import evidence_id, identifier, sha256, text_record
from src.collect.common import json_bytes, record_bytes
from src.collect.contract import contract, load_records
from src.collect.pilot import snapshot_payload
from src.graph.load_neo4j import credentials

try:
    from neo4j import GraphDatabase
    CONN = credentials()
    with GraphDatabase.driver(CONN[0], auth=CONN[1:]) as d:
        d.verify_connectivity()
except Exception:
    CONN = None

AT = "2026-01-01T00:00:00Z"
PID = "mxh_cv_trend_test"
TITLE = "Object Detection with Transformers"
ABSTRACT = "We address object detection. We use a Transformer. We evaluate our method on the COCO dataset."


def row(table, **values):
    return {field: values.get(field) for field in contract()["files"][table]["fields"]}


def write_manifest(root, directory, tables, **extra):
    spec, files = contract(), []
    for name, rows in sorted(tables.items()):
        body = record_bytes(name, spec["files"][name]["fields"], rows)
        (root / directory).mkdir(parents=True, exist_ok=True)
        (root / directory / name).write_bytes(body)
        files.append(dict(path=f"{directory}/{name}", sha256=sha256(body), record_count=len(rows), role=spec["files"][name]["stage"]))
    manifest = dict(project_id="mxh_cv_700", schema_version="2.0.0", code_version="t", normalization_version="nfc-ws-1", parser_versions=["p"],
                    rule_versions={}, dictionary_versions={}, applied_decision_ids=[], graph_ready=False, node_count=None, edge_count=None,
                    files=files, source_snapshot_id="snapshot:v2:s", created_at=AT)
    manifest.update(extra)
    manifest["snapshot_id"] = "snapshot:v2:" + sha256(sn.canonical_json(snapshot_payload(manifest)).encode())
    (root / directory / "snapshot_manifest.json").write_bytes(json_bytes(manifest))
    return manifest


def edition(root, year, slugs, author="author:openalex:A1"):
    tables = {name: [] for name in contract()["files"]}
    for slug in slugs:
        pid, venue = f"cvf:CVPR{year}:{slug}", f"venue:CVPR:{year}:main"
        url = f"https://openaccess.thecvf.com/content/CVPR{year}/html/{slug}_paper.html"
        body = slug.encode()
        raw, digest = f"data/raw/{slug}-{year}.gz", sha256(body)
        (root / raw).parent.mkdir(parents=True, exist_ok=True)
        (root / raw).write_bytes(gzip.compress(body))
        sid = identifier("source:cvf", url, digest)
        tables["source_records.jsonl"].append(row("source_records.jsonl", schema_version="2.0.0", source_record_id=sid, paper_id=pid, source="CVF",
            source_kind="paper", source_id=slug, url=url, fetched_at=AT, http_status=200, content_sha256=digest, content_type="text/html", raw_path=raw))
        texts = {f: text_record(pid, sid, f"html:{f}", value, "p", AT) for f, value in (("title", TITLE), ("abstract", ABSTRACT))}
        tables["text_versions.jsonl"] += texts.values()
        tables["field_provenance.csv"] += [row("field_provenance.csv", paper_id=pid, field_name=f, source_record_id=sid, field_path=f"html:{f}",
            selection_rule="r", validation_status="auto_verified", selected_at=AT, candidate_source_record_ids=[sid]) for f in texts]
        tables["papers.jsonl"].append(row("papers.jsonl", schema_version="2.0.0", paper_id=pid, owner="A", scope="core", track="main", conference="CVPR",
            conference_year=year, venue_id=venue, title=TITLE, abstract=ABSTRACT, cvf_url=url, date_precision="year", publication_date=str(year),
            authors=[dict(authorship_id="au:" + pid, name="N", name_raw="N", author_order=1)], title_text_version_id=texts["title"]["text_version_id"],
            abstract_text_version_id=texts["abstract"]["text_version_id"], openalex_status="not_collected", references_status="not_collected",
            representative_source_record_id=sid))
        tables["paper_registry.csv"].append(row("paper_registry.csv", paper_id=pid, cvf_url=url, conference="CVPR", conference_year=year, owner="A",
            status="cvf_verified", schema_version="2.0.0", track="main", scope="core", venue_id=venue, title=TITLE, selection_rank=1, source_record_id=sid, verified_at=AT))
        tables["authorships.csv"].append(row("authorships.csv", authorship_id="au:" + pid, paper_id=pid, author_id=author, author_name="N", author_name_raw="N",
            author_order=1, identity_status="resolved", source_record_id=sid, owner="A", identity_source_record_id=sid, affiliation_status="not_collected", decision_ids=[]))
        ev = row("evidence.jsonl", evidence_kind="metadata", paper_id=pid, source_record_id=sid, source_url=url, field_path="html:authors", evidence_text="N",
                 rule_id="m", rule_version="1", captured_at=AT, supporting_evidence_ids=[], owner="A")
        ev["evidence_id"] = evidence_id(ev)
        tables["evidence.jsonl"].append(ev)
    sids = [s["source_record_id"] for s in tables["source_records.jsonl"]]
    tables["nodes.csv"] = [row("nodes.csv", id=author, label="Author", name="N", owner="A", source_origin=["CVF"], source_record_ids=sorted(sids),
                               validation_status="accepted", project_id="mxh_cv_700", properties_json={})]
    write_manifest(root, f"h5/{year}", tables)
    snap = root / f"snaps/{year}/s1"
    snap.mkdir(parents=True)
    for name in ("papers.jsonl", "paper_registry.csv", "snapshot_manifest.json"):
        (snap / name).write_bytes((root / f"h5/{year}" / name).read_bytes())
    return dict(name=f"CVPR{year}", venue_id=f"venue:CVPR:{year}:main", snapshots_dir=f"snaps/{year}", h5_dir=f"h5/{year}")


def corpus(root, first=("One",)):
    (root / "gold.csv").write_text("venue_edition,paper_id,split\nCVPR2025,cvf:CVPR2025:Gold,test\n", encoding="utf-8")
    cfg = dict(project_id=PID, code_version="t", target_count=2, gold_set="gold.csv", nlp_manifest="h7/snapshot_manifest.json", output_dir="out",
               dryrun_dir="dry", fixture_dir="fix", check_report="check.json",
               editions=[edition(root, 2024, list(first)), edition(root, 2025, ["Two", "Gold"])])
    sn.make_fixture(root, cfg)
    return cfg


def resign(root, directory, edit):
    path = root / directory / "snapshot_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    edit(manifest)
    for entry in manifest["files"]:
        entry["sha256"] = sha256((root / entry["path"]).read_bytes())
    manifest["snapshot_id"] = "snapshot:v2:" + sha256(sn.canonical_json(snapshot_payload(manifest)).encode())
    path.write_bytes(json_bytes(manifest))


def real_h7(root):
    (root / "h7").mkdir()
    for path in (root / "fix").iterdir():
        (root / "h7" / path.name).write_bytes(path.read_bytes())

    def edit(manifest):
        manifest.pop("fixture")
        for entry in manifest["files"]:
            entry["path"] = "h7/" + Path(entry["path"]).name

    resign(root, "h7", edit)


def fake_checks(manifest, recount=True):
    return "hash", dict(double_load=dict(passed=True), recount=dict(passed=recount))


class LockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = corpus(self.root, first=("One", "Three"))
        real_h7(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_snapshot(self, mode, recount=True):
        with mock.patch("neo4j.GraphDatabase.driver"), mock.patch.object(
                sn, "database_checks", side_effect=lambda snap, manifest, conn: fake_checks(manifest, recount)) as checks:
            self.checks = checks
            return sn.run(self.root, self.cfg, mode, connection=("u", "n", "p"))

    def test_failed_lock_publishes_nothing(self):
        report = self.run_snapshot("lock", recount=False)
        self.assertFalse(report["locked"])
        self.assertEqual(report["snapshot_dir"], "dry")
        self.assertFalse((self.root / "out").exists())

    def test_locked_snapshot_is_never_overwritten(self):
        report = self.run_snapshot("lock")
        self.assertEqual((report["locked"], report["snapshot_dir"], report["blockers"]), (True, "out", []))
        published = {p.name: p.read_bytes() for p in (self.root / "out").iterdir()}
        self.assertTrue(sn.verify_graph_contract(self.root, json.loads(published["snapshot_manifest.json"]))["passed"])
        self.assertTrue(self.run_snapshot("lock")["locked"])
        (self.root / "check.json").unlink()
        with self.assertRaisesRegex(ValueError, "đã khóa"):
            self.run_snapshot("dryrun")
        self.cfg["code_version"] = "t2"
        with self.assertRaisesRegex(ValueError, "không ghi đè"):
            self.run_snapshot("lock")
        self.checks.assert_not_called()
        self.assertEqual(published, {p.name: p.read_bytes() for p in (self.root / "out").iterdir()})


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = corpus(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def assemble(self):
        return sn.assemble(self.root, self.cfg, self.cfg["editions"], "fix/snapshot_manifest.json", self.cfg["dryrun_dir"])

    def test_build_is_deterministic_and_passes_contract(self):
        manifest, contents = self.assemble()
        self.assertEqual((manifest, contents), self.assemble())
        sn.write(self.root, self.cfg["dryrun_dir"], manifest, contents)
        self.assertTrue(sn.verify_graph_contract(self.root, manifest)["passed"])
        self.assertEqual(manifest["project_id"], PID)
        self.assertEqual(manifest["counts_by_label"]["Paper"], 3)
        self.assertEqual((manifest["counts_by_label"]["Author"], manifest["counts_by_type"]["AUTHORED"]), (1, 3))
        self.assertEqual(manifest["counts_by_type"]["STUDIES_TASK"], 2)
        edges = load_records(self.root / "dry/edges.csv")
        self.assertEqual({e["project_id"] for e in edges}, {PID})
        self.assertEqual(manifest["total_weight"], sum(e["weight"] for e in edges))
        self.assertEqual([e["nlp_edges"] > 0 for e in manifest["editions"]], [True, True])

    def test_fixture_skips_gold_papers(self):
        edges = load_records(self.root / "fix/edges.csv")
        self.assertTrue(edges)
        self.assertNotIn("cvf:CVPR2025:Gold", {e["src"] for e in edges})

    def test_h7_not_ready_is_rejected(self):
        resign(self.root, "fix", lambda m: m.update(graph_ready=False))
        with self.assertRaisesRegex(ValueError, "graph_ready"):
            self.assemble()

    def test_h7_changed_file_is_rejected(self):
        path = self.root / "fix/edges.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.assemble()

    def rewrite(self, name, change):
        path = self.root / "fix" / name
        rows = load_records(path)
        change(rows)
        path.write_bytes(record_bytes(name, contract()["files"][name]["fields"], rows))
        resign(self.root, "fix", lambda m: [f.update(record_count=len(rows)) for f in m["files"] if f["path"].endswith(name)])

    def test_h7_wrong_offset_is_rejected(self):
        def shift(rows):
            rows[0]["start_char"] += 1
            rows[0]["evidence_id"] = evidence_id(rows[0])

        self.rewrite("evidence.jsonl", shift)
        with self.assertRaisesRegex(ValueError, "slice|offsets"):
            self.assemble()

    def test_h7_edge_without_node_is_rejected(self):
        self.rewrite("nodes.csv", lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError, "endpoint"):
            self.assemble()

    def test_h7_missing_file_is_rejected(self):
        (self.root / "fix/evidence.jsonl").unlink()
        with self.assertRaisesRegex(ValueError, "missing.*evidence"):
            self.assemble()

    def test_h7_dictionary_version_without_sha256_is_rejected(self):
        resign(self.root, "fix", lambda m: m.update(dictionary_versions={"a4-cv": "v3"}))
        with self.assertRaisesRegex(ValueError, "sha256"):
            self.assemble()

    def test_different_load_hashes_fail_the_double_load(self):
        manifest, contents = self.assemble()
        sn.write(self.root, self.cfg["dryrun_dir"], manifest, contents)
        with mock.patch.object(sn, "load", side_effect=[dict(content_sha256="a"), dict(content_sha256="b")]), \
                mock.patch.object(sn, "recount", return_value={**{k: manifest[k] for k in sn.COUNT_KEYS}, "total_weight": 0}):
            _, result = sn.database_checks(self.root / self.cfg["dryrun_dir"], manifest, ("u", "n", "p"))
        self.assertEqual((result["double_load"]["passed"], result["recount"]["passed"]), (False, False))

    def test_config_matches_project_config(self):
        cfg, project = (json.loads((sn.ROOT / p).read_text(encoding="utf-8")) for p in (sn.CONFIG, "config/a_trend_project.json"))
        self.assertEqual((cfg["project_id"], cfg["target_count"]), (project["project_id"], project["target_count"]))
        self.assertEqual(sorted(e["venue_id"] for e in cfg["editions"]), sorted(project["venue_ids"]))

    def test_lock_blockers(self):
        ok = dict(contract=dict(passed=True), double_load=dict(passed=True), recount=dict(passed=True))
        editions = [dict(name="CVPR2024", papers_registered=350, nlp_edges=1)]
        self.assertEqual(sn.lock_blockers([], False, editions, 350, ok), [])
        blockers = sn.lock_blockers(["ICCV2025"], True, [dict(name="CVPR2024", papers_registered=3, nlp_edges=0)], 350,
                                    {**ok, "recount": dict(passed=False)})
        self.assertEqual(len(blockers), 5)

    def test_lock_refuses_without_real_h7(self):
        with self.assertRaisesRegex(ValueError, "H7"):
            sn.run(self.root, self.cfg, "lock")
        self.assertFalse((self.root / "out").exists())

    def test_database_error_is_reported_not_raised(self):
        manifest, contents = self.assemble()
        sn.write(self.root, self.cfg["dryrun_dir"], manifest, contents)
        with mock.patch.object(sn, "load", side_effect=RuntimeError("out of memory")), \
                mock.patch.object(sn, "recount", return_value={k: manifest[k] for k in sn.COUNT_KEYS}):
            _, result = sn.database_checks(self.root / self.cfg["dryrun_dir"], manifest, ("u", "n", "p"))
        self.assertFalse(result["double_load"]["passed"])
        self.assertIn("out of memory", result["double_load"]["error"])
        self.assertFalse(result["recount"]["passed"])

    @unittest.skipUnless(CONN, "Neo4j unreachable")
    def test_three_conditions_on_neo4j(self):
        try:
            report = sn.run(self.root, self.cfg, "dryrun", connection=CONN)
            self.assertEqual({k: v["passed"] for k, v in report["conditions"].items()}, dict(contract=True, double_load=True, recount=True))
            self.assertFalse(report["locked"])
            self.assertEqual(report["mode"], "dryrun")
            expected = report["conditions"]["recount"]["manifest"]
            self.assertEqual(sn.recount(CONN, PID), expected)
            with GraphDatabase.driver(CONN[0], auth=CONN[1:]) as driver, driver.session() as session:
                session.run("MATCH ({project_id:$p})-[r:AUTHORED]->() WITH r LIMIT 1 SET r.weight = 2", p=PID).consume()
            self.assertEqual(sn.recount(CONN, PID)["total_weight"], expected["total_weight"] + 1)
        finally:
            with GraphDatabase.driver(CONN[0], auth=CONN[1:]) as driver, driver.session() as session:
                session.run("MATCH (n {project_id:$p}) DETACH DELETE n", p=PID).consume()


if __name__ == "__main__":
    unittest.main()
