"""Verify v2 metadata/graph exports and text bindings without third-party packages."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path

from .model import FILES, NODE_PROPERTIES, RELATIONS, VERSION, schema_for
from .text import canonical_json, evidence_id, identifier, normalize, sha256, text_record, validate_nlp_evidence


def load_records(path: Path) -> list[dict]:
    fields = FILES[path.name][0]
    schema = schema_for(path.name)
    if path.suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != fields: raise ValueError("Header mismatch: " + path.name)
            rows = list(reader)
        for row in rows:
            if set(row) != set(fields): raise ValueError("Malformed CSV: " + path.name)
            for name, value in row.items():
                kinds = schema["properties"][name]["type"]
                kinds = kinds if isinstance(kinds,list) else [kinds]
                if value=="" and "null" in kinds: row[name] = None
                elif "integer" in kinds: row[name] = int(value)
                elif "array" in kinds or "object" in kinds: row[name] = json.loads(value)
    else:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if set(row) != set(fields): raise ValueError("Record keys mismatch: " + path.name)
        for name, value in row.items():
            prop = schema["properties"][name]
            kinds = prop["type"] if isinstance(prop["type"],list) else [prop["type"]]
            ok = any((kind=="string" and isinstance(value,str)) or (kind=="integer" and type(value) is int)
                     or (kind=="array" and isinstance(value,list)) or (kind=="object" and isinstance(value,dict))
                     or (kind=="null" and value is None) for kind in kinds)
            if not ok: raise ValueError("Invalid type: " + path.name + "." + name)
            if "const" in prop and value != prop["const"]: raise ValueError("Version mismatch: " + path.name)
            if "enum" in prop and value not in prop["enum"]: raise ValueError("Invalid enum: " + path.name + "." + name)
    return rows


def verify(root: Path) -> dict:
    root = root.resolve()
    manifest = json.loads((root / "snapshot_manifest.json").read_text(encoding="utf-8"))
    if manifest["schema_version"] != VERSION: raise ValueError("Manifest schema mismatch")
    payload = {key: manifest[key] for key in ["project_id","schema_version","code_version","normalization_version",
               "parser_versions","rule_versions","dictionary_versions","applied_decision_ids","graph_ready","node_count","edge_count","files"]}
    if manifest["snapshot_id"] != "snapshot:v2:" + sha256(canonical_json(payload).encode()):
        raise ValueError("Snapshot fingerprint mismatch")
    data = {}
    if {Path(f["path"]).name for f in manifest["files"]} != set(FILES): raise ValueError("Missing/extra contract tables")
    for file in manifest["files"]:
        path = (root / file["path"]).resolve()
        if root not in path.parents: raise ValueError("Unsafe manifest path")
        if sha256(path.read_bytes()) != file["sha256"]: raise ValueError("File hash mismatch: " + path.name)
        rows = load_records(path)
        if len(rows) != file["record_count"]: raise ValueError("Record count mismatch")
        key = FILES[path.name][1]
        keys = [tuple(row[k] for k in key) for row in rows]
        if len(keys) != len(set(keys)): raise ValueError("Duplicate logical key: " + path.name)
        data[path.name] = rows
    sources = {s["source_record_id"]: s for s in data["source_records.jsonl"]}
    papers = {p["paper_id"]: p for p in data["papers.jsonl"]}
    texts = {t["text_version_id"]: t for t in data["text_versions.jsonl"]}
    registry = {r["paper_id"]: r for r in data["paper_registry.csv"]}
    if set(registry)!=set(papers): raise ValueError("Registry/Paper IDs differ")
    for s in sources.values():
        path = (root / s["raw_path"]).resolve()
        if root not in path.parents: raise ValueError("Unsafe raw path")
        body = gzip.decompress(path.read_bytes())
        if sha256(body)!=s["content_sha256"]: raise ValueError("Raw source hash mismatch")
        if s["source"]=="CVF" and identifier("source:cvf",s["url"],s["content_sha256"])!=s["source_record_id"]:
            raise ValueError("CVF source ID changed")
    for text in texts.values():
        if text["source_record_id"] not in sources or text["paper_id"] not in papers: raise ValueError("Text foreign key missing")
        expected = text_record(text["paper_id"],text["source_record_id"],text["field_path"],text["normalized_text"],text["parser_version"],text["captured_at"])
        if expected!=text: raise ValueError("Invalid text version/hash/normalization")
    for p in papers.values():
        if p["representative_source_record_id"] not in sources: raise ValueError("Paper representative source missing")
        for field in ("title","abstract"):
            tid = p[field+"_text_version_id"]
            if p[field] is None and tid is None: continue
            if tid not in texts or texts[tid]["normalized_text"]!=p[field] or texts[tid]["paper_id"]!=p["paper_id"]:
                raise ValueError("Paper/text binding mismatch")
        if p["citation_count"] is not None and (p["citation_count_source_record_id"] not in sources or not p["citation_count_observed_at"]):
            raise ValueError("Citation metric lacks provenance/time")
    for a in data["authorships.csv"]:
        if a["paper_id"] not in papers or a["source_record_id"] not in sources: raise ValueError("Authorship source missing")
        if a["identity_status"]=="resolved" and (not a["author_id"] or a["identity_source_record_id"] not in sources):
            raise ValueError("Resolved Author lacks identity evidence")
        if a["affiliation_status"]=="verified" and (not a["institution_id"] or a["affiliation_source_record_id"] not in sources):
            raise ValueError("Verified affiliation lacks evidence")
    for row in data["field_provenance.csv"]:
        if row["paper_id"] not in papers or row["source_record_id"] not in sources: raise ValueError("Field provenance source missing")
    evidence = {e["evidence_id"]:e for e in data["evidence.jsonl"]}
    for e in evidence.values():
        if e["evidence_id"]!=evidence_id(e): raise ValueError("Evidence ID mismatch")
        if e["evidence_kind"]=="nlp":
            if e["text_version_id"] not in texts: raise ValueError("Evidence text version missing")
            validate_nlp_evidence(e,texts[e["text_version_id"]])
        elif e["evidence_kind"]=="metadata":
            if e["source_record_id"] not in sources or not e["field_path"]: raise ValueError("Metadata evidence source missing")
            if e["source_url"]!=sources[e["source_record_id"]]["url"]: raise ValueError("Metadata source URL mismatch")
        elif not e["supporting_evidence_ids"]: raise ValueError("Derived evidence has no support")
        if e["evidence_kind"]!="nlp" and any(e[k] is not None for k in ("start_char","end_char","text_version_id","normalized_text_sha256","normalization_version")):
            raise ValueError("Non-NLP evidence must not claim NLP coordinates")
        if e["evidence_kind"]=="derived" and any(e[k] is not None for k in ("source_record_id","source_url","field_path","evidence_text")):
            raise ValueError("Derived evidence must refer to supporting evidence instead of a fabricated direct quote")
        if any(parent not in evidence for parent in e["supporting_evidence_ids"]): raise ValueError("Evidence parent missing")
    done, visiting = set(), set()
    def visit(eid):
        if eid in visiting: raise ValueError("Cyclic evidence support")
        if eid in done: return
        visiting.add(eid)
        for parent in evidence[eid]["supporting_evidence_ids"]: visit(parent)
        visiting.remove(eid); done.add(eid)
    for eid in evidence: visit(eid)
    decisions = {d["decision_id"]:d for d in data["merge_log.jsonl"]}
    for d in decisions.values():
        if not d["changes"] or not d["reason"] or not d["reviewed_by"]: raise ValueError("Decision lacks reversible changes/reason/reviewer")
        if d["action"] in {"merge","split"} and (d["review_mode"]!="manual" or d["reviewed_by"] not in {"A","B"}):
            raise ValueError("Merge/split requires a recorded human review")
        if d["action"]=="merge" and not (len(d["input_ids"])>=2 and len(d["output_ids"])==1): raise ValueError("Invalid merge cardinality")
        if d["action"]=="split" and not (len(d["input_ids"])==1 and len(d["output_ids"])>=2): raise ValueError("Invalid split cardinality")
        if d["action"]=="retract" and d["reverts_decision_id"] not in decisions: raise ValueError("Retraction decision missing")
    if any(d not in decisions for d in manifest["applied_decision_ids"]): raise ValueError("Applied decision missing")
    nodes = {n["id"]:n for n in data["nodes.csv"] if n["validation_status"]=="accepted"}
    for node in nodes.values():
        if node["project_id"]!=manifest["project_id"]: raise ValueError("Wrong node project")
        props = node["properties_json"]
        if set(props)-set(NODE_PROPERTIES[node["label"]]): raise ValueError("Unknown node properties")
        if any(isinstance(v,dict) or (isinstance(v,list) and any(isinstance(i,(dict,list)) for i in v)) for v in props.values()):
            raise ValueError("Nested Neo4j property object")
    relation_spec = {r[0]:r[1:] for r in RELATIONS}
    active_edges = [e for e in data["edges.csv"] if e["validation_status"]=="accepted"]
    for edge in active_edges:
        if edge["project_id"]!=manifest["project_id"] or edge["src"] not in nodes or edge["dst"] not in nodes: raise ValueError("Edge endpoint/project missing")
        sl,dl,directed = relation_spec[edge["type"]]
        if (nodes[edge["src"]]["label"],nodes[edge["dst"]]["label"])!=(sl,dl): raise ValueError("Wrong endpoint labels")
        if not directed and not edge["src"] < edge["dst"]: raise ValueError("Undirected duplicate/self-loop order")
        if edge["edge_id"]!=identifier("edge",edge["src"],edge["type"],edge["dst"]): raise ValueError("Edge ID mismatch")
        expected_weight = len(set(edge["paper_ids"])) if not directed else 1
        if edge["weight"]!=expected_weight or expected_weight<1: raise ValueError("Wrong edge weight")
        if not edge["evidence_ids"] or any(e not in evidence for e in edge["evidence_ids"]): raise ValueError("Edge evidence missing")
    if manifest["graph_ready"]:
        if (manifest["node_count"],manifest["edge_count"])!=(len(nodes),len(active_edges)): raise ValueError("Active graph counts differ")
    elif manifest["node_count"] is not None or manifest["edge_count"] is not None:
        raise ValueError("Unbuilt graph must have null measured counts")
    return {"schema_version":VERSION,"snapshot_id":manifest["snapshot_id"],"passed":True,
            "tables_checked":len(data),"records_checked":sum(len(r) for r in data.values()),
            "raw_sources_checked":len(sources),"text_versions_checked":len(texts),"graph_ready":manifest["graph_ready"],
            "limitation":"Validates export integrity; does not prove entity/edge semantic accuracy or execute Neo4j."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    args = parser.parse_args()
    try: result = verify(args.root)
    except (ValueError,KeyError,OSError) as exc: parser.exit(1,str(exc)+"\n")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__": main()
