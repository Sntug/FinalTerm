"""Optional A4 input adapter for B's exporter; no alternate exporter or loader."""
from pathlib import Path

from contract_v2.text import identifier
from .validation import TABLES, load_inputs, read_manifest, validate_nlp, combine


def augment(cfg, root, nodes, edges, report):
    manifest, nlp = read_manifest(root, cfg["nlp_manifest"], TABLES)
    if manifest["graph_ready"] is not False:
        raise ValueError("Expected A4 intermediate manifest")
    paths = [str(Path(inp["a3_dir"]) / "snapshot_manifest.json") for inp in cfg["inputs"]]
    inputs, original = load_inputs(root, paths, include_identity=True)
    if manifest["source_snapshot_id"] != identifier("snapshot:v2", *[m["snapshot_id"] for m in inputs]):
        raise ValueError("A4/graph input snapshot mismatch; rerun A4 for these inputs")
    validate_nlp(nlp, original, cfg["project_id"])
    from .verify import verify
    if verify(root, manifest["config_path"])["snapshot_id"] != manifest["snapshot_id"]:
        raise ValueError("NLP manifest differs from verified A4 output")
    by_id = {n["id"]: n for n in nodes}
    for node in nlp["nodes.csv"]:
        if node["id"] in by_id:
            raise ValueError("NLP node ID already present in base graph: " + node["id"])
        by_id[node["id"]] = node
    keys = {(e["src"], e["type"], e["dst"]) for e in edges}
    for edge in nlp["edges.csv"]:
        if edge["src"] not in by_id or by_id[edge["src"]]["label"] != "Paper":
            raise ValueError("NLP source Paper missing from accepted graph")
        if (edge["src"], edge["type"], edge["dst"]) in keys:
            raise ValueError("Duplicate NLP edge in base graph")
    papers = {p["paper_id"]: p for p in original["papers.jsonl"]}
    for node in nodes:
        if node["label"] == "Paper":
            paper = papers.get(node["id"])
            if not paper or any(node["properties_json"].get(f + "_text_version_id") != paper[f + "_text_version_id"] for f in ("title", "abstract")):
                raise ValueError("Base graph Paper text differs from A4 input")
    tables = combine([original, {n: nlp[n] for n in ("evidence.jsonl", "needs_review.csv")}])
    tables["nodes.csv"] = sorted(by_id.values(), key=lambda n: (n["label"], n["id"]))
    tables["edges.csv"] = sorted(edges + nlp["edges.csv"], key=lambda e: (e["type"], e["src"], e["dst"]))
    report["a4"] = dict(snapshot_id=manifest["snapshot_id"], nodes=len(nlp["nodes.csv"]), edges=len(nlp["edges.csv"]), evidence=len(nlp["evidence.jsonl"]))
    report["cross_corpus_alias_reviews"] = sum(r["reason"].startswith("cross_corpus_alias_conflict:") for r in original["needs_review.csv"])
    selected_alias_decisions = {a["decision_id"] for a in original["alias_map.csv"]}
    report["unapplied_alias_decision_ids"] = sorted(d["decision_id"] for d in original["merge_log.jsonl"]
        if d["changes"] and all(c["table"] == "alias_map.csv" for c in d["changes"])
        and d["decision_id"] not in selected_alias_decisions)
    return tables, manifest
