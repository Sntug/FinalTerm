import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.graph.export_graph import sha256, write_records
from src.graph.load_neo4j import credentials, load

try:
    from neo4j import GraphDatabase
    CONN = credentials()
    with GraphDatabase.driver(CONN[0], auth=CONN[1:]) as d:
        d.verify_connectivity()
    UP = True
except Exception:  # driver missing, no .env, or server down
    UP, CONN = False, None

PID = "mxh_cv_700_test"


def node(i, label, props=None):
    return dict(id=i, label=label, name=i, owner="B", source_origin=["OpenAlex"], source_record_ids=["s"], validation_status="accepted",
                project_id=PID, properties_json=props or {})


def edge(s, t, d):
    return dict(edge_id="edge:" + s + t + d, src=s, dst=d, type=t, weight=1, derivation="metadata", validation_status="accepted",
                evidence_ids=[], paper_ids=["p1"], owner="B", source_origin=["OpenAlex"], project_id=PID)


NODES = [node("a1", "Author"), node("p1", "Paper", {"doi": "10.1/x", "citation_count": 3}), node("i1", "Institution", {"country_code": "US"}),
         node("i2", "Institution", {"country_code": "VN"}), node("c1", "Country", {"country_code": "US"}), node("c2", "Country", {"country_code": "VN"})]
V1 = [edge("a1", "AUTHORED", "p1"), edge("a1", "AFFILIATED_WITH", "i1"), edge("i1", "BASED_IN", "c1"), edge("i2", "BASED_IN", "c2")]
V2 = [edge("a1", "AUTHORED", "p1"), edge("a1", "AFFILIATED_WITH", "i2"), edge("i1", "BASED_IN", "c1"), edge("i2", "BASED_IN", "c2")]


def snapshot(root, name, nodes, edges, ready=True):
    d = Path(root) / name
    d.mkdir()
    write_records(d / "nodes.csv", nodes)
    write_records(d / "edges.csv", edges)
    count = lambda rows, k: {x: sum(1 for r in rows if r[k] == x) for x in sorted({r[k] for r in rows})}
    (d / "snapshot_manifest.json").write_text(json.dumps(dict(
        project_id=PID, snapshot_id="snapshot:v2:" + name, graph_ready=ready, node_count=len(nodes), edge_count=len(edges),
        counts_by_label=count(nodes, "label"), counts_by_type=count(edges, "type"),
        files=[dict(path=f, sha256=sha256((d / f).read_bytes()), record_count=0, role="graph") for f in ("nodes.csv", "edges.csv")])))
    return d


def db_edges(session):
    return {(r["s"], r["t"], r["d"]) for r in session.run("MATCH (a {project_id:$p})-[r]->(b) RETURN a.id AS s, type(r) AS t, b.id AS d", p=PID)}


@unittest.skipUnless(UP, "Neo4j unreachable")
class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.v1, self.v2 = snapshot(self.tmp.name, "v1", NODES, V1), snapshot(self.tmp.name, "v2", NODES, V2)
        self.driver = GraphDatabase.driver(CONN[0], auth=CONN[1:])

    def tearDown(self):
        with self.driver.session() as s:
            s.run("MATCH (n {project_id:$p}) DETACH DELETE n", p=PID).consume()
        self.driver.close()
        self.tmp.cleanup()

    def test_repeat_import_same_hash(self):
        a, b = load(self.v1, PID, connection=CONN), load(self.v1, PID, connection=CONN)
        self.assertEqual(a["content_sha256"], b["content_sha256"])
        self.assertEqual((a["node_count"], a["edge_count"]), (6, 4))
        self.assertEqual((a["counts_by_label"], a["counts_by_type"]), (b["counts_by_label"], b["counts_by_type"]))

    def test_affiliation_fix_replaces_edge(self):
        h1 = load(self.v1, PID, connection=CONN)["content_sha256"]
        h2 = load(self.v2, PID, connection=CONN)["content_sha256"]
        self.assertNotEqual(h1, h2)
        with self.driver.session() as s:
            e = db_edges(s)
        self.assertNotIn(("a1", "AFFILIATED_WITH", "i1"), e)
        self.assertIn(("a1", "AFFILIATED_WITH", "i2"), e)

    def test_mid_import_failure_rolls_back(self):
        good = load(self.v1, PID, connection=CONN)
        with self.assertRaises(Exception):
            load(self.v2, PID, fail_after_nodes=True, connection=CONN)
        with self.driver.session() as s:
            self.assertEqual(db_edges(s), {(e["src"], e["type"], e["dst"]) for e in V1})
            self.assertEqual(s.run("MATCH (n {project_id:$p}) RETURN count(n) AS c", p=PID).single()["c"], good["node_count"])
        self.assertEqual(load(self.v1, PID, connection=CONN)["content_sha256"], good["content_sha256"])


class RejectTest(unittest.TestCase):
    def test_graph_ready_false_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError, "graph_ready"):
                load(snapshot(t, "x", NODES, V1, ready=False), PID, connection=("bolt://127.0.0.1:1", "u", "p"))

    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            d = snapshot(t, "x", NODES, V1)
            (d / "edges.csv").write_bytes((d / "edges.csv").read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "sha256"):
                load(d, PID, connection=("bolt://127.0.0.1:1", "u", "p"))


if __name__ == "__main__":
    unittest.main()
