import csv
import json
import unittest
from collections import defaultdict

from .load import ROOT
from .sna import edition, load_snapshot, paper_authors

QUERY = ROOT / "queries/trend_q1b.cypher"
SNA = ROOT / "outputs/trend/sna"
COLUMNS = ["topic_type", "topic_id", "topic_name", "n_topic_papers", "n_group_text_papers", "n_group_papers",
           "n_total_papers", "core_author_id", "core_author_name", "source_papers"]
EDGE_TYPES = {"STUDIES_TASK": "Task", "USES_METHOD": "Method", "EVALUATED_ON": "Dataset"}


def read_csv(name):
    with (SNA / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class Q1bTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from neo4j import READ_ACCESS, GraphDatabase

            from src.graph.load_neo4j import credentials

            summary = json.loads((SNA / "summary.json").read_text(encoding="utf-8"))
            uri, user, password = credentials()
            cls.driver = GraphDatabase.driver(uri, auth=(user, password))
            cls.session = cls.driver.session(database="neo4j", default_access_mode=READ_ACCESS)
            cls.project = summary["snapshot"]["project_id"]
            loaded = cls.session.run("MATCH (n:Paper {project_id: $p}) RETURN collect(DISTINCT n.snapshot_id) AS s",
                                     p=cls.project).single()["s"]
        except Exception as exc:
            raise unittest.SkipTest(f"Neo4j not available: {exc}")
        if loaded != [summary["snapshot"]["snapshot_id"]]:
            raise unittest.SkipTest(f"Neo4j holds {loaded}, SNA tables use {summary['snapshot']['snapshot_id']}")
        cls.g, _ = load_snapshot(ROOT / summary["snapshot"]["path"])
        top = max(read_csv("group_ranking.csv"), key=lambda r: int(r["n_papers"]))
        cls.core = top["core_author_id"]
        cls.members = [r["author_id"] for r in read_csv("communities.csv") if r["community_id"] == top["community_id"]]

    @classmethod
    def tearDownClass(cls):
        cls.session.close()
        cls.driver.close()

    def run_query(self, **params):
        args = {"project_id": self.project, "author_ids": self.members, "core_author_id": self.core,
                "venue_edition": None, "limit": 3, **params}
        result = self.session.run(QUERY.read_text(encoding="utf-8"), **args)
        self.assertEqual(list(result.keys()), COLUMNS)
        return [r.data() for r in result]

    def expected(self, venue_edition, limit):
        papers = {p for p, d in self.g.nodes(data=True)
                  if d["label"] == "Paper" and venue_edition in (None, edition(d))}
        group = {p for p, team in paper_authors(self.g).items() if p in papers and team & set(self.members)}
        topics = defaultdict(set)
        for p, t, d in self.g.edges(data=True):
            if p in group and d["type"] in EDGE_TYPES:
                topics[EDGE_TYPES[d["type"]], t].add(p)
        want = []
        for kind in sorted(EDGE_TYPES.values()):
            ids = sorted((t for k, t in topics if k == kind), key=lambda t: (-len(topics[kind, t]), t))
            want += [(kind, t, sorted(topics[kind, t])) for t in ids[:limit]]
        return len(papers), len(group), want

    def test_counts_topics_and_source_papers_match_the_snapshot(self):
        for venue_edition in (None, "CVPR2024"):
            total, group, want = self.expected(venue_edition, 3)
            rows = self.run_query(venue_edition=venue_edition)
            self.assertTrue(want)
            self.assertEqual([(r["topic_type"], r["topic_id"], [s["paper_id"] for s in r["source_papers"]]) for r in rows], want)
            for r in rows:
                self.assertEqual((r["n_total_papers"], r["n_group_papers"], r["n_group_text_papers"]), (total, group, group))
                self.assertEqual(r["n_topic_papers"], len(r["source_papers"]))
                self.assertEqual(r["core_author_id"], self.core)
                self.assertTrue(r["core_author_name"])
                self.assertTrue(all(s["evidence_ids"] and s["title"] and s["cvf_url"] for s in r["source_papers"]))

    def test_empty_group_still_returns_one_row_with_the_denominators(self):
        rows = self.run_query(author_ids=[], core_author_id=None)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["topic_type"], rows[0]["n_group_papers"], rows[0]["n_topic_papers"], rows[0]["source_papers"]),
                         (None, 0, 0, []))
        self.assertGreater(rows[0]["n_total_papers"], 0)


if __name__ == "__main__":
    unittest.main()
