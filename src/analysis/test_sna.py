import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import networkx as nx

from . import sna as S
from .load import ROOT, build


def fixture(papers, editions=None):
    editions = editions or {}
    nodes, rels, weights = [], [], {}
    authors = sorted({a for team in papers.values() for a in team})
    for a in authors:
        nodes.append(("Author", {"id": a, "name": a.upper()}))
    for p, team in papers.items():
        conference, year = editions.get(p, ("CVPR", 2024))
        nodes.append(("Paper", {"id": p, "name": p, "conference": conference, "conference_year": year}))
        for a in team:
            rels.append((a, "AUTHORED", p, {"edge_id": f"au:{a}:{p}", "weight": 1, "paper_ids": [p], "evidence_ids": []}))
        for i, a in enumerate(sorted(team)):
            for b in sorted(team)[i + 1:]:
                weights.setdefault((a, b), []).append(p)
    for (a, b), shared in weights.items():
        rels.append((a, "COAUTHORED_WITH", b, {"edge_id": f"co:{a}:{b}", "weight": len(shared), "paper_ids": shared, "evidence_ids": []}))
    return build(nodes, rels)


class DistanceTest(unittest.TestCase):
    def test_three_numbers_on_a_fragmented_graph(self):
        c = nx.Graph([("a", "b"), ("b", "c"), ("d", "e")])
        c.add_node("f")
        d = S.distances(c)
        self.assertEqual(d["l_lcc"], round(4 / 3, 6))
        self.assertEqual(d["l_reachable"], 1.25)
        self.assertEqual(d["reachable_share"], round(4 / 15, 6))
        self.assertEqual((d["reachable_pairs"], d["total_pairs"]), (4, 15))
        self.assertEqual(d["lcc_diameter"], 2)
        self.assertEqual(d["histogram_lcc"], {"1": 2, "2": 1})
        self.assertEqual(d["histogram_reachable"], {"1": 3, "2": 1})


class CommunityTest(unittest.TestCase):
    def setUp(self):
        self.g = fixture({"p1": ["a", "b", "c", "d"], "p2": ["e", "f", "g"], "p3": ["d", "e"],
                          "p4": ["x", "y"], "p5": ["z"]})
        self.c = S.coauthor_graph(self.g)

    def test_lcc_louvain_small_components_and_isolates_are_separated(self):
        member, q = S.communities(self.c, 42, 1.0)
        self.assertEqual({member[a] for a in "abcd"}, {"L001"})
        self.assertEqual({member[a] for a in "efg"}, {"L002"})
        self.assertEqual({member[a] for a in "xy"}, {"C001"})
        self.assertNotIn("z", member)
        self.assertGreater(q, 0)

    def test_core_author_is_top_internal_pagerank_ties_by_id(self):
        member, _ = S.communities(self.c, 42, 1.0)
        core, internal = S.core_authors(self.c, member, 0.85)
        self.assertEqual(core["C001"], "x")
        self.assertEqual(core["L001"], "a")
        self.assertAlmostEqual(sum(internal[a] for a in "abcd"), 1.0, places=6)

    def test_core_author_follows_weighted_pagerank_not_id_order(self):
        c = S.coauthor_graph(fixture({"p1": ["a", "y", "z"], "p2": ["y", "z"], "p3": ["y", "z"], "p4": ["y", "z"]}))
        core, internal = S.core_authors(c, {"a": "G", "y": "G", "z": "G"}, 0.85)
        self.assertEqual(core["G"], "y")
        self.assertGreater(internal["y"], internal["a"])

    def test_coverage_counts_papers_missing_authors_or_affiliations(self):
        g = fixture({"p1": ["a", "b"], "p2": [], "p3": ["a"]}, {"p3": ("ICCV", 2023)})
        g.add_node("i", label="Institution", name="I")
        g.add_edge("a", "i", type="AFFILIATED_WITH", weight=1, paper_ids=["p1"])
        self.assertEqual(S.coverage(g), {"CVPR2024": {"papers": 2, "with_resolved_author": 1, "with_affiliation": 1},
                                         "ICCV2023": {"papers": 1, "with_resolved_author": 1, "with_affiliation": 0}})

    def test_core_numbers_and_main_core(self):
        numbers = S.core_numbers(self.c)
        self.assertEqual((numbers["a"], numbers["e"], numbers["x"], numbers["z"]), (3, 2, 1, 0))


class RankingTest(unittest.TestCase):
    def test_papers_counted_once_per_group_and_ordered_with_ties(self):
        g = fixture({"p1": ["a", "b"], "p2": ["c"], "p3": ["c"], "p4": ["d"], "p5": ["e", "f"], "p6": ["a"]},
                    {"p6": ("ICCV", 2023)})
        member = {"a": "G2", "b": "G2", "c": "G1", "d": "G4", "e": "G3", "f": "G3"}
        core = {"G1": "c", "G2": "a", "G3": "e", "G4": "d"}
        rows = S.group_ranking(g, member, core, ["CVPR2024", "ICCV2023", "ICCV2025"])
        self.assertEqual(rows, [["CVPR2024", "G1", 2, 1, "c"], ["CVPR2024", "G2", 1, 2, "a"],
                                ["CVPR2024", "G3", 1, 2, "e"], ["CVPR2024", "G4", 1, 1, "d"],
                                ["ICCV2023", "G2", 1, 1, "a"]])

    def test_edition_outside_the_configured_periods_is_an_error(self):
        g = fixture({"p1": ["a", "b"]}, {"p1": ("CVPR", 2030)})
        with self.assertRaises(ValueError):
            S.group_ranking(g, {"a": "G1"}, {"G1": "a"}, ["CVPR2024"])


class ReferenceTest(unittest.TestCase):
    def test_reference_keeps_degrees_and_connectivity(self):
        c = nx.connected_watts_strogatz_graph(60, 6, 0.1, seed=1)
        runs = S.reference_networks(c, 3, 5, 7)
        self.assertEqual(len(runs), 3)
        for graph, swaps in runs:
            self.assertEqual(sorted(d for _, d in graph.degree()), sorted(d for _, d in c.degree()))
            self.assertTrue(nx.is_connected(graph))
            self.assertGreater(swaps, 0)
        self.assertEqual([s for _, s in runs], [s for _, s in S.reference_networks(c, 3, 5, 7)])

    def test_conclusion_states_scope_and_can_be_insufficient(self):
        yes = S.conclusion(sigma=5.0, path_ratio=1.1, reachable_share=0.9, lcc_share=0.95, max_path_ratio=1.5, min_reachable_share=0.5)
        no = S.conclusion(sigma=5.0, path_ratio=2.4, reachable_share=0.03, lcc_share=0.17, max_path_ratio=1.5, min_reachable_share=0.5)
        unknown = S.conclusion(sigma=None, path_ratio=1.0, reachable_share=0.03, lcc_share=0.17, max_path_ratio=1.5, min_reachable_share=0.5)
        self.assertEqual((yes["lcc"], yes["whole_network"]), ("small_world_signs", "small_world_signs"))
        self.assertEqual((no["lcc"], no["whole_network"]), ("insufficient_evidence", "insufficient_evidence"))
        self.assertEqual(unknown["lcc"], "insufficient_evidence")


class EndToEndTest(unittest.TestCase):
    def test_output_columns_and_byte_identical_reruns(self):
        cfg = json.loads((ROOT / "config/trend_sna.json").read_text(encoding="utf-8"))
        cfg.update(reference_networks=2, swaps_per_edge=1)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
            for hashseed, out in (("1", tmp / "a"), ("2", tmp / "b")):
                subprocess.run([sys.executable, "-m", "src.analysis.sna", "--config", str(tmp / "cfg.json"), "--out", str(out)],
                               cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": hashseed}, check=True, capture_output=True)
            names = sorted(f.name for f in (tmp / "a").iterdir())
            self.assertEqual(names, ["communities.csv", "group_ranking.csv", "kcore.csv", "pagerank_author.csv",
                                     "pagerank_institution.csv", "summary.json"])
            for name in names:
                self.assertEqual((tmp / "a" / name).read_bytes(), (tmp / "b" / name).read_bytes(), name)

            def table(name):
                with (tmp / "a" / name).open(encoding="utf-8", newline="") as f:
                    return list(csv.reader(f))

            self.assertEqual(table("communities.csv")[0], ["author_id", "community_id"])
            self.assertEqual(table("group_ranking.csv")[0],
                             ["venue_edition", "community_id", "n_papers", "n_active_authors", "core_author_id"])
            summary = json.loads((tmp / "a" / "summary.json").read_text(encoding="utf-8"))
            members = {a for a, _ in table("communities.csv")[1:]}
            self.assertEqual(len(members) + summary["coauthor"]["isolated_authors"], summary["coauthor"]["nodes"])
            self.assertEqual(len(table("pagerank_author.csv")) - 1, summary["coauthor"]["nodes"])


if __name__ == "__main__":
    unittest.main()
