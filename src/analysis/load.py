import json
import sys
from collections import Counter
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.graph.load_neo4j import content_hash, credentials, read_snapshot

SNAPSHOT = ROOT / "data/processed/mxh_cv_700/a8/graph"
PROJECT = "mxh_cv_700"
NODE_KEYS = ("conference", "conference_year", "country_code", "citation_count")


def build(nodes, rels):
    g = nx.MultiDiGraph()
    for label, p in sorted(nodes, key=lambda x: x[1]["id"]):
        g.add_node(p["id"], label=label, name=p["name"], **{k: p[k] for k in NODE_KEYS if k in p})
    for s, t, d, p in sorted(rels, key=lambda x: x[3]["edge_id"]):
        g.add_edge(s, d, key=p["edge_id"], type=t, weight=p["weight"], paper_ids=list(p["paper_ids"]), evidence_ids=list(p["evidence_ids"]))
    return g


def read(snapshot=SNAPSHOT):
    return read_snapshot(snapshot, PROJECT)


def from_csv(snapshot=SNAPSHOT):
    manifest, nodes, rels = read(snapshot)
    return build(nodes, rels), manifest


def from_neo4j():
    from neo4j import GraphDatabase
    uri, user, password = credentials()
    with GraphDatabase.driver(uri, auth=(user, password)) as driver, driver.session(database="neo4j") as session:
        nodes = [(r["label"], dict(r["props"])) for r in session.run(
            "MATCH (n {project_id:$p}) RETURN labels(n)[0] AS label, properties(n) AS props", p=PROJECT)]
        rels = [(r["s"], r["t"], r["d"], dict(r["props"])) for r in session.run(
            "MATCH (a {project_id:$p})-[r]->(b {project_id:$p}) RETURN a.id AS s, type(r) AS t, b.id AS d, properties(r) AS props", p=PROJECT)]
    return nodes, rels


def counts(g):
    return {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "by_label": dict(sorted(Counter(d["label"] for _, d in g.nodes(data=True)).items())),
        "by_type": dict(sorted(Counter(d["type"] for _, _, d in g.edges(data=True)).items())),
    }


def load(source):
    manifest, csv_nodes, csv_rels = read()
    csv_graph = build(csv_nodes, csv_rels)
    csv_hash = content_hash(csv_nodes, csv_rels)
    result = {"snapshot": {"path": SNAPSHOT.relative_to(ROOT).as_posix(), "snapshot_id": manifest["snapshot_id"],
                           "source_snapshot_id": manifest["source_snapshot_id"], "content_hash": csv_hash}}
    result["manifest_match"] = counts(csv_graph) == {
        "nodes": manifest["node_count"], "edges": manifest["edge_count"],
        "by_label": dict(sorted(manifest["counts_by_label"].items())), "by_type": dict(sorted(manifest["counts_by_type"].items()))}
    assert result["manifest_match"], "CSV counts differ from manifest"
    if source == "csv":
        result["neo4j_vs_csv"] = "skipped"
        return csv_graph, result
    neo_nodes, neo_rels = from_neo4j()
    tags = sorted({p.get("snapshot_id") for _, p in neo_nodes})
    assert tags == [manifest["snapshot_id"]], f"Neo4j holds snapshot {tags}, expected {manifest['snapshot_id']}"
    assert content_hash(neo_nodes, neo_rels) == csv_hash, "Neo4j content hash differs from CSV"
    neo_graph = build(neo_nodes, neo_rels)
    result["neo4j_vs_csv"] = "identical"
    result["counts"] = counts(neo_graph)
    return neo_graph, result
