from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.graph.export_graph import ROOT, build
from src.graph.load_neo4j import content_hash, credentials, load, read_snapshot
from contract_v2.text import canonical_json, identifier, sha256
from src.collect.common import json_bytes, publish, record_bytes, within
from src.collect.contract import contract, load_records, validate_records
from src.collect.pilot import snapshot_payload
from src.nlp.validation import TABLES, combine, load_inputs, validate_nlp, verify_graph_contract

CONFIG = "config/trend_graph.json"
COUNT_KEYS = ("node_count", "edge_count", "counts_by_label", "counts_by_type", "total_weight", "weight_by_type")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fingerprint(manifest):
    return "snapshot:v2:" + sha256(canonical_json(snapshot_payload(manifest)).encode())


def split_editions(root, cfg):
    present, missing = [], []
    for e in cfg["editions"]:
        ready = (root / e["h5_dir"] / "snapshot_manifest.json").exists() and (root / e["snapshots_dir"]).is_dir()
        (present if ready else missing).append(e)
    return present, missing


def load_corpus(root, editions):
    return load_inputs(root, [e["h5_dir"] + "/snapshot_manifest.json" for e in editions], include_identity=True)


def table_files(directory, tables):
    spec, files, contents = contract(), [], {}
    for name in sorted(tables):
        validate_records(name, tables[name])
        contents[name] = record_bytes(name, spec["files"][name]["fields"], tables[name])
        files.append(dict(path=f"{directory}/{name}", sha256=sha256(contents[name]), record_count=len(tables[name]), role=spec["files"][name]["stage"]))
    return files, contents


def write(root, directory, manifest, contents, immutable=False):
    out = within(root, directory)
    files = {out / name: body for name, body in contents.items()}
    files[out / "snapshot_manifest.json"] = json_bytes(manifest)
    if immutable:
        publish(files)
        return
    out.mkdir(parents=True, exist_ok=True)
    for path, body in files.items():
        path.write_bytes(body)


def make_fixture(root, cfg):
    from src.nlp.pipeline import code_version, dictionary_versions, extract
    from src.nlp.rules import METHOD_RULE_IDS, RULE_IDS, RULE_VERSION, Extractor

    inputs, original = load_corpus(root, split_editions(root, cfg)[0])
    with within(root, cfg["gold_set"]).open(encoding="utf-8-sig", newline="") as stream:
        gold = {r["paper_id"] for r in csv.DictReader(stream)}
    original = {**original, "papers.jsonl": [p for p in original["papers.jsonl"] if p["paper_id"] not in gold]}
    base, methods = read_json(ROOT / "config/a4_dictionary.json"), read_json(ROOT / "config/b5_method_dictionary.json")
    extractor = Extractor({**base, "methods": methods["methods"]}, "blank")
    extractor.base_dictionary, extractor.method_dictionary = base, methods
    data, summary = extract(original, extractor, cfg["project_id"])
    files, contents = table_files(cfg["fixture_dir"], data)
    manifest = dict(
        project_id=cfg["project_id"], schema_version="2.0.0", code_version=code_version(extractor) + "+fixture",
        normalization_version="nfc-ws-1", parser_versions=[extractor.runtime],
        rule_versions={k: RULE_VERSION for k in (*RULE_IDS, *METHOD_RULE_IDS, "a4-review")},
        dictionary_versions=dictionary_versions(extractor), applied_decision_ids=[], graph_ready=True,
        node_count=len(data["nodes.csv"]), edge_count=len(data["edges.csv"]), files=files,
        source_snapshot_id=identifier("snapshot:v2", *[m["snapshot_id"] for m in inputs]),
        created_at=max(m["created_at"] for m in inputs), model="fixture:" + extractor.runtime, fixture=True)
    manifest["snapshot_id"] = fingerprint(manifest)
    contents["summary.json"] = json_bytes({**summary, "fixture": True, "gold_papers_excluded": len(gold)})
    write(root, cfg["fixture_dir"], manifest, contents)


def read_h7(root, path, original, project_id):
    manifest = read_json(within(root, path))
    missing = (set(contract()["snapshot_manifest"]["required"]) | {"model"}) - set(manifest)
    if missing:
        raise ValueError(f"H7 manifest keys missing: {sorted(missing)}")
    if manifest["graph_ready"] is not True:
        raise ValueError("H7 graph_ready is not true")
    if manifest["project_id"] not in (project_id, contract()["project_id"]) or manifest["schema_version"] != "2.0.0":
        raise ValueError("H7 project or schema version mismatch")
    if manifest["snapshot_id"] != fingerprint(manifest):
        raise ValueError("H7 snapshot fingerprint mismatch")
    if not (manifest["dictionary_versions"] and manifest["code_version"] and manifest["model"]):
        raise ValueError("H7 dictionary_versions, code_version and model must be set")
    if not all(re.search(r"\b[0-9a-f]{64}\b", str(v)) for v in manifest["dictionary_versions"].values()):
        raise ValueError("H7 dictionary_versions must carry the dictionary sha256")
    data = {}
    for entry in manifest["files"]:
        table = within(root, entry["path"])
        if not table.is_file():
            raise ValueError("H7 file missing: " + entry["path"])
        if sha256(table.read_bytes()) != entry["sha256"]:
            raise ValueError("H7 file hash mismatch: " + table.name)
        if table.name in TABLES:
            data[table.name] = load_records(table)
            if len(data[table.name]) != entry["record_count"]:
                raise ValueError("H7 record count mismatch: " + table.name)
    if set(data) != set(TABLES):
        raise ValueError(f"H7 files must list {TABLES}")
    validate_nlp(data, original, manifest["project_id"])
    for name in ("nodes.csv", "edges.csv"):
        data[name] = [{**r, "project_id": project_id} for r in data[name]]
    return manifest, data


def assemble(root, cfg, editions, h7_path, out_dir):
    base = {"project_id": cfg["project_id"],
            "inputs": [{"name": e["name"], "snapshots_dir": e["snapshots_dir"], "a3_dir": e["h5_dir"]} for e in editions]}
    nodes, edges, manifests, inputs, report = build(base, root)
    _, original = load_corpus(root, editions)
    h7, nlp = read_h7(root, h7_path, original, cfg["project_id"])

    by_id = {n["id"]: n for n in nodes}
    papers = {p["paper_id"]: p for p in original["papers.jsonl"]}
    for node in nodes:
        if node["label"] == "Paper" and any(node["properties_json"].get(f + "_text_version_id") != papers[node["id"]][f + "_text_version_id"]
                                            for f in ("title", "abstract")):
            raise ValueError("Graph Paper text differs from H5: " + node["id"])
    clash = sorted(set(by_id) & {n["id"] for n in nlp["nodes.csv"]})
    if clash:
        raise ValueError("H7 node ID already in base graph: " + clash[0])
    for edge in nlp["edges.csv"]:
        if by_id.get(edge["src"], {}).get("label") != "Paper":
            raise ValueError("H7 edge source is not an accepted Paper: " + edge["src"])

    tables = combine([original, {name: nlp[name] for name in ("evidence.jsonl", "needs_review.csv")}])
    tables["nodes.csv"] = sorted(nodes + nlp["nodes.csv"], key=lambda n: (n["label"], n["id"]))
    tables["edges.csv"] = sorted(edges + nlp["edges.csv"], key=lambda e: (e["type"], e["src"], e["dst"]))
    files, contents = table_files(out_dir, tables)

    selected = {a["decision_id"] for a in original["alias_map.csv"]}
    unapplied = {d["decision_id"] for d in original["merge_log.jsonl"]
                 if d["changes"] and all(c["table"] == "alias_map.csv" for c in d["changes"]) and d["decision_id"] not in selected}
    union = lambda key: {x for m in [*manifests, h7] for x in m[key]}
    merged = lambda key: {k: v for m in [*manifests, h7] for k, v in m[key].items()}
    manifest = dict(
        project_id=cfg["project_id"], schema_version="2.0.0", code_version=cfg["code_version"], normalization_version="nfc-ws-1",
        parser_versions=sorted(union("parser_versions")),
        rule_versions={**merged("rule_versions"), "b3-graph-export": "1.0.1", "b4-collab-edges": "1.0.0"},
        dictionary_versions=merged("dictionary_versions"), applied_decision_ids=sorted(union("applied_decision_ids") - unapplied),
        graph_ready=True, node_count=len(tables["nodes.csv"]), edge_count=len(tables["edges.csv"]), files=files)
    manifest["snapshot_id"] = fingerprint(manifest)
    manifest["created_at"] = max(m["created_at"] for m in [*manifests, h7])
    manifest["source_snapshot_id"] = "snapshot:v2:" + sha256(canonical_json([inputs, h7["snapshot_id"]]).encode())
    manifest["input_snapshots"] = inputs
    manifest["h7"] = {k: h7[k] for k in ("snapshot_id", "model", "code_version", "dictionary_versions")} | {"fixture": bool(h7.get("fixture"))}

    weights = Counter()
    for e in tables["edges.csv"]:
        weights[e["type"]] += e["weight"]
    manifest["counts_by_label"] = dict(sorted(Counter(n["label"] for n in tables["nodes.csv"]).items()))
    manifest["counts_by_type"] = dict(sorted(Counter(e["type"] for e in tables["edges.csv"]).items()))
    manifest["total_weight"] = sum(weights.values())
    manifest["weight_by_type"] = dict(sorted(weights.items()))

    venue = {r["paper_id"]: r["venue_id"] for r in original["paper_registry.csv"]}
    accepted = Counter(r["venue_id"] for r in original["paper_registry.csv"] if r["status"] == "cvf_verified")
    registered = Counter(venue.values())
    nlp_edges = Counter(venue[e["src"]] for e in nlp["edges.csv"])
    manifest["editions"] = []
    for e, snap in zip(editions, inputs):
        if not registered[e["venue_id"]]:
            raise ValueError(f"No papers for {e['venue_id']} in {e['h5_dir']}")
        manifest["editions"].append(dict(name=e["name"], venue_id=e["venue_id"], h5_snapshot_id=snap["a3_snapshot_id"],
                                         papers_registered=registered[e["venue_id"]], papers_accepted=accepted[e["venue_id"]],
                                         nlp_edges=nlp_edges[e["venue_id"]]))
    return manifest, contents


def recount(connection, project_id):
    from neo4j import GraphDatabase

    uri, user, password = connection
    with GraphDatabase.driver(uri, auth=(user, password)) as driver, driver.session(database="neo4j", default_access_mode="READ") as session:
        labels = {r["k"]: r["c"] for r in session.run("MATCH (n {project_id:$p}) RETURN labels(n)[0] AS k, count(*) AS c", p=project_id)}
        rows = list(session.run("MATCH ({project_id:$p})-[r]->({project_id:$p}) RETURN type(r) AS k, count(r) AS c, sum(r.weight) AS w", p=project_id))
    return dict(node_count=sum(labels.values()), edge_count=sum(r["c"] for r in rows), counts_by_label=labels,
                counts_by_type={r["k"]: r["c"] for r in rows}, total_weight=sum(r["w"] for r in rows),
                weight_by_type={r["k"]: r["w"] for r in rows})


def contract_check(root, manifest, contents=None):
    try:
        result = verify_graph_contract(root, manifest, contents)
    except (ValueError, KeyError, OSError) as exc:
        return dict(passed=False, error=str(exc))
    return {k: result[k] for k in ("passed", "records_checked", "tables_checked", "raw_sources_checked", "text_versions_checked")}


def database_checks(snapshot, manifest, connection):
    from neo4j.exceptions import DriverError, Neo4jError

    _, nodes, rels = read_snapshot(snapshot, manifest["project_id"])
    csv_hash = content_hash(nodes, rels)
    expected = {k: manifest[k] for k in COUNT_KEYS}
    hashes = []
    try:
        for _ in range(2):
            hashes.append(load(snapshot, manifest["project_id"], connection=connection)["content_sha256"])
        double = dict(passed=hashes == [csv_hash, csv_hash], load_hashes=hashes, csv_hash=csv_hash)
    except (DriverError, Neo4jError, RuntimeError) as exc:
        double = dict(passed=False, load_hashes=hashes, csv_hash=csv_hash, error=str(exc))
    actual = recount(connection, manifest["project_id"])
    return csv_hash, dict(double_load=double, recount=dict(passed=bool(hashes) and actual == expected, neo4j=actual, manifest=expected))


def lock_blockers(missing, fixture, editions, target, conditions):
    blockers = []
    if missing:
        blockers.append("Thiếu H5: " + ", ".join(missing))
    if fixture:
        blockers.append("H7 đang là fixture, chưa có H7 thật của A")
    blockers += [f"{e['name']}: {e['papers_registered']} bài đăng ký, cần {target}" for e in editions if e["papers_registered"] != target]
    blockers += [f"{e['name']}: không có cạnh NLP nào trong H7" for e in editions if not e["nlp_edges"]]
    blockers += [f"Điều kiện {name} không đạt" for name, result in conditions.items() if not result["passed"]]
    return blockers


def run(root, cfg, mode, connection=None):
    report_path = root / cfg["check_report"]
    published = root / cfg["output_dir"] / "snapshot_manifest.json"
    if mode == "dryrun" and (published.exists() or report_path.exists() and read_json(report_path).get("locked")):
        raise ValueError("Snapshot đã khóa; chạy thử sẽ ghi đè báo cáo và dữ liệu Neo4j nên bị từ chối")
    present, missing = split_editions(root, cfg)
    missing = [e["name"] for e in missing]
    real = (root / cfg["nlp_manifest"]).exists()
    if mode == "lock":
        if missing:
            raise ValueError("Chưa khóa được, thiếu H5: " + ", ".join(missing))
        if not real or read_json(root / cfg["nlp_manifest"]).get("fixture"):
            raise ValueError("Chưa khóa được, thiếu H7 thật tại " + cfg["nlp_manifest"])
    h7_path = cfg["nlp_manifest"] if real else cfg["fixture_dir"] + "/snapshot_manifest.json"
    if not real:
        make_fixture(root, cfg)
    connection = connection or credentials()
    from neo4j import GraphDatabase

    with GraphDatabase.driver(connection[0], auth=connection[1:]) as driver:
        driver.verify_connectivity()

    out_dir = cfg["output_dir"] if mode == "lock" else cfg["dryrun_dir"]
    manifest, contents = assemble(root, cfg, present, h7_path, out_dir)
    conditions = {"contract": contract_check(root, manifest, contents)}
    target = cfg["target_count"]
    if mode == "lock":
        early = lock_blockers(missing, manifest["h7"]["fixture"], manifest["editions"], target, conditions)
        if early:
            raise ValueError("Chưa khóa được: " + "; ".join(early))
        if published.exists() and published.read_bytes() != json_bytes(manifest):
            raise ValueError("Snapshot đã khóa khác bản vừa dựng; không ghi đè " + cfg["output_dir"])
    write(root, cfg["dryrun_dir"], manifest, contents)
    csv_hash, database = database_checks(root / cfg["dryrun_dir"], manifest, connection)
    conditions.update(database)
    blockers = lock_blockers(missing, manifest["h7"]["fixture"], manifest["editions"], target, conditions)
    locked = mode == "lock" and not blockers
    if locked:
        write(root, out_dir, manifest, contents, immutable=True)
    report = dict(
        mode=mode, locked=locked, status="ĐÃ KHÓA" if locked else "BẢN THỬ, CHƯA KHÓA", blockers=blockers,
        project_id=manifest["project_id"], snapshot_dir=out_dir if locked else cfg["dryrun_dir"], snapshot_id=manifest["snapshot_id"], content_sha256=csv_hash,
        h7=manifest["h7"] | {"path": h7_path}, missing_editions=missing, editions=manifest["editions"], conditions=conditions,
        checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dryrun", "lock"))
    parser.add_argument("--config", default=CONFIG)
    args = parser.parse_args()
    try:
        report = run(ROOT, read_json(ROOT / args.config), args.mode)
    except ValueError as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps({k: report[k] for k in ("status", "snapshot_id", "content_sha256", "missing_editions", "blockers")}
                     | {"conditions": {k: v["passed"] for k, v in report["conditions"].items()}}, ensure_ascii=False, indent=1))
    ok = all(v["passed"] for v in report["conditions"].values()) and (args.mode != "lock" or report["locked"])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
