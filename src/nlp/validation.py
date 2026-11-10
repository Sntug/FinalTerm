"""Contract-backed validation and immutable snapshot input for A4."""
import gzip
import json
import os
from pathlib import Path
import shutil
import uuid
from contextlib import contextmanager

from contract_v2.text import canonical_json, evidence_id, identifier, sha256, text_record, validate_nlp_evidence
from contract_v2.verify import verify as verify_contract
from src.collect.common import within
from src.collect.contract import contract, load_records, validate_records
from src.collect.pilot import snapshot_payload

TABLES = ("nodes.csv", "edges.csv", "evidence.jsonl", "needs_review.csv")
RELATIONS = {"STUDIES_TASK": "Task", "EVALUATED_ON": "Dataset", "USES_METHOD": "Method"}


@contextmanager
def verification_workspace(root):
    # mkdir(0o700) gives inaccessible ACLs in the Windows desktop sandbox.
    parent = (root / "outputs").resolve()
    parent.mkdir(exist_ok=True)
    folder = parent / (".a4-verify-" + uuid.uuid4().hex)
    folder.mkdir(mode=0o755)
    try:
        yield folder
    finally:
        target = folder.resolve()
        if target.parent != parent or not target.name.startswith(".a4-verify-"):
            raise ValueError("Refusing cleanup outside verification workspace")
        shutil.rmtree(target)


def read_manifest(root, path, expected_tables=None):
    manifest = json.loads(within(root, str(path)).read_text(encoding="utf-8"))
    spec = contract()
    if set(spec["snapshot_manifest"]["required"]) - set(manifest):
        raise ValueError("Manifest required keys missing")
    if manifest["project_id"] != spec["project_id"] or manifest["schema_version"] != spec["schema_version"]:
        raise ValueError("Wrong contract/project")
    if manifest["snapshot_id"] != "snapshot:v2:" + sha256(canonical_json(snapshot_payload(manifest)).encode()):
        raise ValueError("Snapshot fingerprint mismatch")
    data = {}
    for entry in manifest["files"]:
        table = within(root, entry["path"])
        if table.name in data or sha256(table.read_bytes()) != entry["sha256"]:
            raise ValueError("Duplicate table or file hash mismatch: " + table.name)
        rows = load_records(table)
        if len(rows) != entry["record_count"] or entry["role"] != spec["files"][table.name]["stage"]:
            raise ValueError("Table count/role mismatch")
        data[table.name] = rows
    if expected_tables is not None and set(data) != set(expected_tables):
        raise ValueError("Missing/extra contract tables")
    return manifest, data


def combine(tables):
    """Merge exact shared records; resolve only equivalent cross-corpus alias decisions."""
    spec, result = contract(), {}
    for name in {n for data in tables for n in data}:
        found = {}
        for data in tables:
            for row in data.get(name, []):
                key = tuple(row[k] for k in spec["files"][name]["logical_unique_key"])
                old = found.get(key)
                if old is not None and old != row:
                    if name != "alias_map.csv" or {k: v for k, v in old.items() if k != "decision_id"} != {k: v for k, v in row.items() if k != "decision_id"}:
                        raise ValueError("Conflicting shared record: " + name + str(key))
                else:
                    found[key] = row
        result[name] = sorted(found.values(), key=canonical_json)
    return result


def load_inputs(root, paths, *, include_identity=False):
    manifests, tables = [], []
    for path in paths:
        manifest, data = read_manifest(root, path, contract()["files"])
        manifests.append(manifest)
        # Entity nodes are merged by B's existing merge_node, not by this metadata union.
        tables.append({name: rows for name, rows in data.items() if name not in ("nodes.csv", "edges.csv", "alias_map.csv")})
        tables[-1]["alias_map.csv"] = data["alias_map.csv"] if include_identity else []
    if include_identity:
        # A4 does not resolve identities. Ambiguous cross-corpus aliases have no
        # effective mapping in the combined snapshot; retain both source decisions
        # and explicitly queue the conflict without changing B's nodes or edges.
        aliases = {}
        for data in tables:
            for row in data["alias_map.csv"]:
                aliases.setdefault(row["alias_id"], []).append(row)
        conflicts = {k: rows for k, rows in aliases.items() if len({r["canonical_id"] for r in rows}) > 1}
        decisions = {d["decision_id"]: d for data in tables for d in data["merge_log.jsonl"]}
        for data in tables:
            data["alias_map.csv"] = [r for r in data["alias_map.csv"] if r["alias_id"] not in conflicts]
        for aid, rows in sorted(conflicts.items()):
            if any(any(c["table"] != "alias_map.csv" for c in decisions[r["decision_id"]]["changes"]) for r in rows):
                raise ValueError("Conflicting alias decision also affects identities; manual resolution required")
            tables[0]["needs_review.csv"].append(dict(
                review_id=identifier("review", "a4-cross-corpus-alias", aid), paper_id=None,
                entity_type=rows[0]["entity_type"], entity_id=None, field_name="canonical_id",
                reason="cross_corpus_alias_conflict: " + aid + "; source decisions retained; no automatic merge",
                candidate_ids=sorted({r["canonical_id"] for r in rows}),
                evidence_ids=sorted({e for r in rows for e in decisions[r["decision_id"]]["evidence_ids"]}),
                review_status="open", assigned_to=None, resolution_decision_id=None))
    data = combine(tables)
    for source in data["source_records.jsonl"]:
        body = gzip.decompress(within(root, source["raw_path"]).read_bytes())
        if sha256(body) != source["content_sha256"] or source["http_status"] != 200:
            raise ValueError("Raw source hash/status mismatch: " + source["source_record_id"])
        if source["source_record_id"] != identifier("source:" + source["source"].lower(), source["url"], source["content_sha256"]):
            raise ValueError("Source ID mismatch")
    return manifests, data


def field_binding(paper, field, texts, sources, provenance):
    """Fail closed on a stale, cross-paper, unselected or disputed text version."""
    text = texts.get(paper.get(field + "_text_version_id"))
    if text is None or text["paper_id"] != paper["paper_id"] or text["normalized_text"] != paper[field]:
        raise ValueError("Missing or mismatched selected text version")
    expected = text_record(text["paper_id"], text["source_record_id"], text["field_path"], text["normalized_text"], text["parser_version"], text["captured_at"])
    if text != expected:
        raise ValueError("Text ID/hash/normalization mismatch")
    source = sources.get(text["source_record_id"])
    if source is None or source["paper_id"] != paper["paper_id"] or source["fetched_at"] != text["captured_at"]:
        raise ValueError("Text source/paper/capture mismatch")
    prov = provenance.get((paper["paper_id"], field))
    if not prov or prov["validation_status"] not in ("auto_verified", "verified"):
        raise ValueError("Missing or disputed field provenance")
    if any(prov[k] != text[k] for k in ("source_record_id", "field_path")):
        raise ValueError("Selected source/field path mismatch")
    return text


def validate_nlp(data, original, project_id="mxh_cv_700"):
    for name in TABLES:
        validate_records(name, data[name])
    papers = {p["paper_id"]: p for p in original["papers.jsonl"]}
    registry = {r["paper_id"]: r for r in original["paper_registry.csv"]}
    texts = {t["text_version_id"]: t for t in original["text_versions.jsonl"]}
    sources = {s["source_record_id"]: s for s in original["source_records.jsonl"]}
    provenance = {(r["paper_id"], r["field_name"]): r for r in original["field_provenance.csv"]}
    nodes = {n["id"]: n for n in data["nodes.csv"]}
    evidence = {e["evidence_id"]: e for e in data["evidence.jsonl"]}
    for e in evidence.values():
        if not e["rule_id"] or not e["rule_version"] or e["evidence_id"] != evidence_id(e):
            raise ValueError("Evidence identity/rule missing")
        if e["text_version_id"] not in texts or e["paper_id"] not in papers:
            raise ValueError("Evidence text version/paper missing")
        paper, text = papers[e["paper_id"]], texts[e["text_version_id"]]
        fields = [f for f in ("title", "abstract") if paper[f + "_text_version_id"] == e["text_version_id"]
                  and paper[f] == text["normalized_text"]
                  and provenance.get((paper["paper_id"], f), {}).get("field_path") == text["field_path"]]
        if len(fields) != 1:
            raise ValueError("Evidence does not reference the selected title/abstract")
        field_binding(paper, fields[0], texts, sources, provenance)
        validate_nlp_evidence(e, text)  # Canonical v2 implementation, including Unicode slice.
        if e["source_url"] != sources[e["source_record_id"]]["url"] or e["captured_at"] != text["captured_at"] or e["owner"] != paper["owner"] or e["supporting_evidence_ids"]:
            raise ValueError("Evidence source/time/owner mismatch")
    seen, used = set(), set()
    for e in data["edges.csv"]:
        key = (e["src"], e["type"], e["dst"])
        if key in seen or e["edge_id"] != identifier("edge", *key):
            raise ValueError("Duplicate edge or unstable edge ID")
        seen.add(key)
        p, n = papers.get(e["src"]), nodes.get(e["dst"])
        if not p or not n or RELATIONS.get(e["type"]) != n["label"]:
            raise ValueError("NLP endpoint/type missing or invalid")
        if registry[e["src"]]["status"] != "cvf_verified" or p["scope"] != "core" or p["track"] != "main":
            raise ValueError("NLP Paper is not accepted core/main")
        if e["derivation"] != "nlp" or e["weight"] != 1 or e["validation_status"] != "accepted" or e["project_id"] != project_id or e["paper_ids"] != [e["src"]] or e["owner"] != p["owner"]:
            raise ValueError("Invalid NLP edge properties")
        if not e["evidence_ids"] or any(i not in evidence for i in e["evidence_ids"]):
            raise ValueError("NLP edge evidence missing")
        prefix = {"STUDIES_TASK": "a4-task-", "EVALUATED_ON": "a4-dataset-", "USES_METHOD": "b5-method-"}[e["type"]]
        for eid in e["evidence_ids"]:
            ev = evidence[eid]
            if ev["paper_id"] != e["src"] or not ev["rule_id"].startswith(prefix):
                raise ValueError("Edge/evidence Paper or rule mismatch")
        used.add(e["dst"])
    if used != set(nodes):
        raise ValueError("Orphan NLP dictionary node")
    for n in nodes.values():
        if n["project_id"] != project_id or n["label"] not in ("Task", "Dataset", "Method") or n["validation_status"] != "accepted":
            raise ValueError("Invalid NLP node")
        if set(n["properties_json"]) - set(contract()["node_properties"][n["label"]]):
            raise ValueError("Unexpected NLP node property")
        support = [evidence[i] for e in data["edges.csv"] if e["dst"] == n["id"] for i in e["evidence_ids"]]
        if n["source_record_ids"] != sorted({e["source_record_id"] for e in support}):
            raise ValueError("Node provenance differs from accepted evidence")
    for r in data["needs_review.csv"]:
        if r["paper_id"] not in papers or any(e not in evidence for e in r["evidence_ids"]):
            raise ValueError("Review foreign key missing")


def verify_graph_contract(root, manifest, contents=None):
    """Run the unmodified package verifier in a temporary root with real raw files.

    Repo manifests use repository-relative paths, whereas the historical verifier
    expects its manifest at the root. This is a path adapter, not a new validator.
    Hardlinks avoid copying raw data; no source or graph file is modified.
    """
    with verification_workspace(root) as sandbox:
        for entry in manifest["files"]:
            target = within(sandbox, entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            content = contents[Path(entry["path"]).name] if contents is not None else within(root, entry["path"]).read_bytes()
            target.write_bytes(content)
        source_path = next(f["path"] for f in manifest["files"] if Path(f["path"]).name == "source_records.jsonl")
        for source in load_records(within(sandbox, source_path)):
            target, origin = within(sandbox, source["raw_path"]), within(root, source["raw_path"])
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(origin, target)
                except OSError:
                    shutil.copyfile(origin, target)
        (sandbox / "snapshot_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return verify_contract(sandbox)
