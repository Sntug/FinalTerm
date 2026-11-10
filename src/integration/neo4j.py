"""Read-only CSV/Neo4j comparison and explicitly isolated B3 import exercises."""
from collections import Counter
import importlib.util
import os
from pathlib import Path
from urllib.parse import urlsplit

from src.graph.load_neo4j import read_snapshot, content_hash, credentials, load


def db_records(session, project_id):
    nodes = []
    for row in session.run("MATCH (n {project_id:$p}) RETURN labels(n) AS labels, properties(n) AS props", p=project_id):
        if len(row["labels"]) != 1:
            raise ValueError("Neo4j project node has missing/additional labels")
        nodes.append((row["labels"][0], row["props"]))
    rels = []
    for row in session.run(
        "MATCH (a)-[r]->(b) WHERE a.project_id=$p OR b.project_id=$p "
        "RETURN a.id AS s, type(r) AS t, b.id AS d, properties(r) AS props, a.project_id AS ap, b.project_id AS bp", p=project_id):
        if row["ap"] != project_id or row["bp"] != project_id:
            raise ValueError("Neo4j relationship crosses the project boundary")
        rels.append((row["s"], row["t"], row["d"], row["props"]))
    return nodes, rels


def compare_records(manifest, nodes, rels, actual_nodes, actual_rels):
    if len({p["id"] for _, p in actual_nodes}) != len(actual_nodes):
        raise ValueError("Duplicate Neo4j node ID")
    if len({(s, t, d) for s, t, d, _ in actual_rels}) != len(actual_rels):
        raise ValueError("Duplicate Neo4j relationship key")
    if {p.get("snapshot_id") for _, p in actual_nodes} != {manifest["snapshot_id"]}:
        raise ValueError("Neo4j node snapshot tags differ from the selected CSV snapshot")
    expected_hash, observed_hash = content_hash(nodes, rels), content_hash(actual_nodes, actual_rels)
    if expected_hash != observed_hash:
        raise ValueError("Neo4j content hash differs from CSV; counts alone are insufficient")
    paper_nodes = [p for label, p in actual_nodes if label == "Paper"]
    return dict(status="PASS", snapshot_id=manifest["snapshot_id"], content_sha256=observed_hash, nodes=len(actual_nodes), edges=len(actual_rels),
        counts_by_label=dict(sorted(Counter(label for label, _ in actual_nodes).items())),
        counts_by_type=dict(sorted(Counter(t for _, t, _, _ in actual_rels).items())),
        papers_by_scope=dict(Counter(p.get("scope") for p in paper_nodes)),
        papers_by_conference=dict(Counter(str(p.get("conference")) + str(p.get("conference_year")) for p in paper_nodes)))


def inspect(snapshot, project_id="mxh_cv_700", connection=None):
    manifest, nodes, rels = read_snapshot(Path(snapshot), project_id)
    if importlib.util.find_spec("neo4j") is None:
        return dict(status="BLOCKED_ENV", reason="Neo4j Python driver is not installed; no DB queries/writes executed")
    from neo4j import GraphDatabase
    try:
        uri, user, password = connection or credentials()
        with GraphDatabase.driver(uri, auth=(user, password), connection_timeout=3,
                                  connection_acquisition_timeout=5, max_transaction_retry_time=0) as driver:
            with driver.session(database="neo4j", default_access_mode="READ") as session:
                actual = db_records(session, project_id)
    except ValueError as exc:
        return dict(status="FAIL", reason=str(exc))
    except Exception as exc:
        # Driver exceptions may include credentials, URI parameters or server details.
        return dict(status="BLOCKED_ENV", reason="Neo4j connection/authentication/read unavailable: " + type(exc).__name__)
    try:
        return compare_records(manifest, nodes, rels, *actual)
    except (ValueError, KeyError, TypeError) as exc:
        return dict(status="FAIL", reason=str(exc) if isinstance(exc, ValueError) else "Neo4j records do not match the expected schema")


def isolated_uri(uri):
    parsed = urlsplit(uri)
    if (parsed.scheme != "bolt" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or
        parsed.port is None or parsed.port in (7687, 17687) or parsed.username or parsed.password or
        parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("Test import requires an explicit separate local bolt port; production/default targets are rejected")
    return uri


def test_import(snapshot, project_id="mxh_cv_700"):
    """Never called by the default A8 run; require an empty dedicated test instance."""
    uri, user, password = [os.environ.get(k) for k in ("A8_NEO4J_TEST_URI", "A8_NEO4J_TEST_USER", "A8_NEO4J_TEST_PASSWORD")]
    if not all((uri, user, password)):
        return dict(status="BLOCKED_ENV", reason="Set A8_NEO4J_TEST_URI/USER/PASSWORD for a separate empty test instance; .env is not used")
    isolated_uri(uri)
    if importlib.util.find_spec("neo4j") is None:
        return dict(status="BLOCKED_ENV", reason="Neo4j Python driver is not installed")
    manifest, nodes, rels = read_snapshot(Path(snapshot), project_id)
    from neo4j import GraphDatabase
    preflight_complete = False
    try:
        with GraphDatabase.driver(uri, auth=(user, password), connection_timeout=3,
                                  connection_acquisition_timeout=5, max_transaction_retry_time=0) as driver:
            with driver.session(database="neo4j", default_access_mode="READ") as session:
                if session.run("MATCH (n) RETURN count(n) AS c").single()["c"] != 0:
                    raise ValueError("Test instance is not empty; refusing import without deleting/resetting existing data")
            preflight_complete = True
            conn = (uri, user, password)
            first = load(snapshot, project_id, connection=conn)
            second = load(snapshot, project_id, connection=conn)
            if first["content_sha256"] != second["content_sha256"]:
                raise ValueError("Repeated B3 import changed the graph content hash")
            try:
                load(snapshot, project_id, fail_after_nodes=True, connection=conn)
            except RuntimeError as exc:
                if str(exc) != "injected failure after nodes":
                    raise
            else:
                raise ValueError("Injected import failure did not occur")
            with driver.session(database="neo4j", default_access_mode="READ") as session:
                result = compare_records(manifest, nodes, rels, *db_records(session, project_id))
    except ValueError:
        raise
    except Exception as exc:
        return dict(status="FAIL" if preflight_complete else "BLOCKED_ENV",
                    reason=("Isolated import failed: " if preflight_complete else "Isolated DB preflight unavailable: ") + type(exc).__name__)
    result.update(repeat_import="PASS", rollback_after_injected_failure="PASS", test_data_retained=True,
                  note="Dedicated instance started empty; B3 loader invoked only there, no production DB or B last_import.json changed")
    return result
