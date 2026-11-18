import json
import tempfile
import unittest
from pathlib import Path

from . import analyze as A
from .__main__ import run
from .load import counts, from_csv


class AnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g, cls.manifest = from_csv()

    def test_counts_match_manifest(self):
        c = counts(self.g)
        self.assertEqual(c["nodes"], self.manifest["node_count"])
        self.assertEqual(c["edges"], self.manifest["edge_count"])
        self.assertEqual(c["by_label"], dict(sorted(self.manifest["counts_by_label"].items())))
        self.assertEqual(c["by_type"], dict(sorted(self.manifest["counts_by_type"].items())))

    def test_group_citation_sums_to_assigned_cites(self):
        pc, _ = A.paper_countries(self.g)
        m, tables, _ = A.group_citation(self.g, pc)
        total = sum(r[2] for r in tables["group_citation_country_matrix"][1])
        self.assertAlmostEqual(total, m["cites_assigned"], places=3)
        self.assertEqual(m["cites_assigned"] + m["cites_unassigned"], self.manifest["counts_by_type"]["CITES"])

    def test_country_pairs_count_distinct_papers(self):
        pc, ic = A.paper_countries(self.g)
        want = {}
        for u, v, d in self.g.edges(data=True):
            if d["type"] == "COLLABORATED_WITH" and u in ic and v in ic:
                want.setdefault(tuple(sorted((ic[u], ic[v]))), set()).update(d["paper_ids"])
        got = {(a, b): w for a, b, w in A.institutions(self.g, pc, ic)[1]["country_pair_collaboration"][1]}
        self.assertEqual(got, {k: len(v) for k, v in want.items()})

    def test_metrics_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            run("csv", a, False)
            run("csv", b, False)
            for f in sorted(Path(a).rglob("*")):
                if f.is_file():
                    self.assertEqual(f.read_bytes(), (Path(b) / f.relative_to(a)).read_bytes())
            json.loads((Path(a) / "metrics.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
