"""Rebuild one project's graph in Neo4j from a graph_ready snapshot: delete+load+verify in ONE write transaction."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "handoff/mxh_contract_v2"))
from contract_v2.migrate import read_csv  # noqa: E402
from contract_v2.model import LABELS, NODE_PROPERTIES, RELATIONS  # noqa: E402
from contract_v2.text import canonical_json, sha256  # noqa: E402

TYPES = {t: (s, d) for t, s, d, _ in RELATIONS}
LAST_IMPORT = ROOT / "outputs/b_iccv2023/graph/last_import.json"
BATCH = 1000


def credentials():
    env = dict(os.environ)
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip("'\""))
    return env.get("NEO4J_URI", "bolt://127.0.0.1:17687"), env.get("NEO4J_USER", "neo4j"), env["NEO4J_PASSWORD"]


def read_snapshot(snap, project_id):
    """Validate manifest + file hashes + whitelists; return (manifest, node records, rel records)."""
    snap = Path(snap)
    m = json.loads((snap / "snapshot_manifest.json").read_text(encoding="utf-8"))
    if m.get("graph_ready") is not True:
        raise ValueError("Refusing snapshot: graph_ready is not true")
    if m.get("project_id") != project_id:
        raise ValueError(f"project_id mismatch: manifest {m.get('project_id')!r} vs {project_id!r}")
    for f in m["files"]:
        if sha256((snap / Path(f["path"]).name).read_bytes()) != f["sha256"]:
            raise ValueError("sha256 mismatch: " + f["path"])
    nodes, rels = [], []
    for r in read_csv(snap / "nodes.csv"):
        if r["label"] not in LABELS or r["project_id"] != project_id or r["validation_status"] != "accepted":
            raise ValueError(f"Bad node row: {r['id']} {r['label']}")
        extra = json.loads(r["properties_json"] or "{}")
        if set(extra) - set(NODE_PROPERTIES[r["label"]]) or any(isinstance(v, dict) for v in extra.values()):
            raise ValueError(f"Non-whitelisted property on {r['id']}")
        props = dict(id=r["id"], name=r["name"], owner=r["owner"], source_origin=json.loads(r["source_origin"]),
                     source_record_ids=json.loads(r["source_record_ids"]), validation_status="accepted", project_id=project_id,
                     snapshot_id=m["snapshot_id"])
        props.update({k: v for k, v in extra.items() if v is not None})
        nodes.append((r["label"], props))
    for r in read_csv(snap / "edges.csv"):
        if r["type"] not in TYPES or r["project_id"] != project_id or r["validation_status"] != "accepted":
            raise ValueError(f"Bad edge row: {r['edge_id']} {r['type']}")
        rels.append((r["src"], r["type"], r["dst"], dict(
            edge_id=r["edge_id"], weight=int(r["weight"]), derivation=r["derivation"], evidence_ids=json.loads(r["evidence_ids"]),
            paper_ids=json.loads(r["paper_ids"]), owner=r["owner"], source_origin=json.loads(r["source_origin"]), project_id=project_id)))
    by_label, by_type = dict(Counter(l for l, _ in nodes)), dict(Counter(t for _, t, _, _ in rels))
    if (len(nodes), len(rels), by_label, by_type) != (m["node_count"], m["edge_count"], m["counts_by_label"], m["counts_by_type"]):
        raise ValueError("CSV counts differ from manifest")
    return m, nodes, rels


def content_hash(nodes, rels):
    """nodes: (label, props); rels: (src, type, dst, props). snapshot_id is a load tag, not graph content."""
    n = sorted(([l, {k: v for k, v in p.items() if k != "snapshot_id"}] for l, p in nodes), key=canonical_json)
    r = sorted(([s, t, d, p] for s, t, d, p in rels), key=canonical_json)
    return sha256(canonical_json({"nodes": n, "rels": r}).encode())


def _import(tx, project_id, nodes, rels, manifest, fail_after_nodes):
    pid, scope = {"p": project_id}, list(LABELS)
    # 1. abort on links that cross the project boundary (never DETACH DELETE blindly)
    cross = tx.run("MATCH (n)-[r]-(m) WHERE n.project_id=$p AND any(l IN labels(n) WHERE l IN $labels) AND coalesce(m.project_id,'')<>$p "
                   "RETURN count(r) AS c", p=project_id, labels=scope).single()["c"]
    if cross:
        raise RuntimeError(f"{cross} relationships link project nodes to other projects; aborting")
    # 2. delete only this project's whitelisted rels, then nodes (plain DELETE fails if anything else is attached)
    tx.run("MATCH (a)-[r]->(b) WHERE a.project_id=$p AND b.project_id=$p AND type(r) IN $types DELETE r", p=project_id, types=list(TYPES)).consume()
    tx.run("MATCH (n) WHERE n.project_id=$p AND any(l IN labels(n) WHERE l IN $labels) DELETE n", p=project_id, labels=scope).consume()
    # 3. nodes by label, then rels by type (labels/types come from the whitelist, so f-strings are safe)
    for label in LABELS:
        rows = [{"props": p} for l, p in nodes if l == label]
        for i in range(0, len(rows), BATCH):
            tx.run(f"UNWIND $rows AS row CREATE (n:{label}) SET n = row.props", rows=rows[i:i + BATCH]).consume()
    if fail_after_nodes:
        raise RuntimeError("injected failure after nodes")
    for typ, (sl, dl) in TYPES.items():
        rows = [{"src": s, "dst": d, "props": p} for s, t, d, p in rels if t == typ]
        for i in range(0, len(rows), BATCH):
            tx.run(f"UNWIND $rows AS row MATCH (a:{sl} {{project_id:$p, id:row.src}}) MATCH (b:{dl} {{project_id:$p, id:row.dst}}) "
                   f"CREATE (a)-[r:{typ}]->(b) SET r = row.props", rows=rows[i:i + BATCH], **pid).consume()
    # 4. verify inside the tx: counts per label/type == manifest, and content hash == hash of the CSVs
    db_nodes = [(next(l for l in rec["labels"] if l in LABELS), rec["props"]) for rec in tx.run(
        "MATCH (n) WHERE n.project_id=$p AND any(l IN labels(n) WHERE l IN $labels) RETURN labels(n) AS labels, properties(n) AS props",
        p=project_id, labels=scope)]
    db_rels = [(r["s"], r["t"], r["d"], r["props"]) for r in tx.run(
        "MATCH (a)-[r]->(b) WHERE a.project_id=$p AND b.project_id=$p RETURN a.id AS s, type(r) AS t, b.id AS d, properties(r) AS props", **pid)]
    counts = (len(db_nodes), len(db_rels), dict(Counter(l for l, _ in db_nodes)), dict(Counter(t for _, t, _, _ in db_rels)))
    if counts != (manifest["node_count"], manifest["edge_count"], manifest["counts_by_label"], manifest["counts_by_type"]):
        raise RuntimeError(f"Neo4j counts differ from manifest: {counts}")
    h = content_hash(db_nodes, db_rels)
    if h != content_hash(nodes, rels):
        raise RuntimeError("Neo4j content hash differs from CSV content hash")
    return h, counts


def load(snapshot, project_id="mxh_cv_700", fail_after_nodes=False, last_import=None, connection=None):
    manifest, nodes, rels = read_snapshot(snapshot, project_id)
    from neo4j import GraphDatabase
    uri, user, password = connection or credentials()
    with GraphDatabase.driver(uri, auth=(user, password)) as driver, driver.session(database="neo4j") as session:
        for label in LABELS:  # schema statements cannot share a tx with writes
            session.run(f"CREATE CONSTRAINT mxh_{label.lower()}_project_id IF NOT EXISTS FOR (n:{label}) REQUIRE (n.project_id, n.id) IS UNIQUE").consume()
        h, counts = session.execute_write(_import, project_id, nodes, rels, manifest, fail_after_nodes)
    result = dict(project_id=project_id, snapshot_id=manifest["snapshot_id"], node_count=counts[0], edge_count=counts[1],
                  counts_by_label=counts[2], counts_by_type=counts[3], content_sha256=h,
                  imported_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if last_import:  # only after commit
        Path(last_import).parent.mkdir(parents=True, exist_ok=True)
        Path(last_import).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--project-id", default="mxh_cv_700")
    a = ap.parse_args()
    res = load(a.snapshot, a.project_id, last_import=LAST_IMPORT)
    print(json.dumps(res, indent=1))
