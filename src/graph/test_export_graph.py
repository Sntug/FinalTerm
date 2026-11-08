import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.graph.export_graph import export

PID = "mxh_cv_700"
CFG = {"project_id": PID, "output_dir": "out", "code_version": "t", "inputs": [{"name": "X", "snapshots_dir": "snaps", "a3_dir": "a3"}]}
MAN = {"snapshot_id": "snapshot:v2:x", "created_at": "2026-01-01T00:00:00Z", "parser_versions": [], "rule_versions": {}, "dictionary_versions": {}, "applied_decision_ids": []}
P1, P2 = "cvf:ICCV2023:P1", "cvf:ICCV2023:P2"


def w(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows([header] + rows)


def fixture(root, author_ok=True):
    s = root / "snaps/s1"
    papers = [dict(paper_id=i, owner="B", scope="core", track="main", conference="ICCV", conference_year=2023, venue_id="venue:ICCV:2023:main",
                   title=i, openalex_id="https://openalex.org/W" + i[-1], referenced_works=["https://openalex.org/W2"] if i == P1 else None,
                   representative_source_record_id="source:cvf:" + i[-1], citation_count_source_record_id=None) for i in (P1, P2)]
    s.mkdir(parents=True)
    (s / "papers.jsonl").write_text("".join(json.dumps(p) + "\n" for p in papers), encoding="utf-8")
    (s / "snapshot_manifest.json").write_text(json.dumps(MAN))
    w(s / "paper_registry.csv", ["paper_id", "status"], [[P1, "cvf_verified"], [P2, "cvf_verified"]])
    a3 = root / "a3"
    (a3 / "snapshot_manifest.json").parent.mkdir(parents=True)
    (a3 / "snapshot_manifest.json").write_text(json.dumps(MAN))
    (a3 / "evidence.jsonl").write_text(json.dumps(dict(paper_id=P1, source_record_id="source:cvf:1", evidence_id="evidence:1")) + "\n")
    node = lambda i, l, props: [i, l, i, "B", '["OpenAlex"]', '["source:openalex:1"]', "accepted", PID, json.dumps(props)]
    w(a3 / "nodes.csv", "id label name owner source_origin source_record_ids validation_status project_id properties_json".split(),
      [node("author:1", "Author", {"aliases": ["a"]}), node("institution:1", "Institution", {"country_code": "US"})])
    row = lambda aid, inst: ["au:" + aid, P1, aid, "n", "n", "1", "resolved", "", inst, "s", "B", "source:cvf:1", "source:cvf:1", "verified" if inst else "not_collected", "[]"]
    h = "authorship_id paper_id author_id author_name author_name_raw author_order identity_status affiliation_raw institution_id source_record_id owner identity_source_record_id affiliation_source_record_id affiliation_status decision_ids".split()
    w(a3 / "authorships.csv", h, [row("author:1", "institution:1"), row("author:1", "institution:1"), row("author:1" if author_ok else "author:missing", "")])
    return CFG


class ExportTest(unittest.TestCase):
    def test_dedupe_and_edges(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            m, _ = export(fixture(root), root)
            edges = list(csv.DictReader((root / "out/edges.csv").open(encoding="utf-8-sig")))
            types = [e["type"] for e in edges]
            self.assertEqual(types.count("AUTHORED"), 1)  # duplicate rows -> one edge
            self.assertEqual(types.count("AFFILIATED_WITH"), 1)
            self.assertEqual(types.count("CITES"), 1)  # P1 -> P2 (both core)
            self.assertEqual(m["counts_by_label"], {"Author": 1, "Country": 1, "Institution": 1, "Paper": 2, "VenueEdition": 1})
            self.assertEqual(json.loads(next(e for e in edges if e["type"] == "PUBLISHED_IN" and e["src"] == P1)["evidence_ids"]), ["evidence:1"])
            self.assertEqual(m, export(CFG, root)[0])  # deterministic

    def test_dangling_endpoint_asserts(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            with self.assertRaises(AssertionError):
                export(fixture(root, author_ok=False), root)


if __name__ == "__main__":
    unittest.main()
