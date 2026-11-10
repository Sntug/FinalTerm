"""Extract immutable A4 intermediate tables from selected A2/A3 text versions."""
from collections import Counter
import json
from pathlib import Path

from contract_v2.text import canonical_json, evidence_id, identifier, sha256
from src.collect.common import REPO_ROOT, within, publish, record_bytes, json_bytes
from src.collect.contract import contract
from src.collect.pilot import snapshot_payload
from .rules import Extractor, RULE_IDS, METHOD_RULE_IDS, RULE_VERSION
from .validation import TABLES, load_inputs, field_binding, validate_nlp

CODE_VERSION = "a4-nlp-1.0.0"
DEFAULT_CONFIG = "config/a4_nlp_700.json"


def extract(original, extractor, project_id="mxh_cv_700"):
    nodes, edges, evidence, reviews = {}, {}, {}, {}
    texts = {t["text_version_id"]: t for t in original["text_versions.jsonl"]}
    sources = {s["source_record_id"]: s for s in original["source_records.jsonl"]}
    registry = {r["paper_id"]: r for r in original["paper_registry.csv"]}
    provenance = {(r["paper_id"], r["field_name"]): r for r in original["field_provenance.csv"]}
    counts = Counter()

    def review(paper, field, reason, candidate=None, ev=None):
        entity = extractor.entities[candidate.entity_id] if candidate else None
        rid = identifier("review", "a4", paper["paper_id"], field, reason, candidate.entity_id if candidate else "",
                         ev["evidence_id"] if ev else str(paper.get(field + "_text_version_id")))
        rejected = reason in {"prior_work_or_baseline", "training_or_mixed_roles", "application_example", "negated_or_mixed_claim", "hypothetical_or_question"}
        reviews[rid] = dict(review_id=rid, paper_id=paper["paper_id"], entity_type=entity["label"] if entity else "Paper",
            entity_id=None, field_name=field, reason=reason, candidate_ids=[candidate.entity_id] if candidate else [],
            evidence_ids=[ev["evidence_id"]] if ev else [], review_status="rejected" if rejected else "open",
            assigned_to=paper["owner"], resolution_decision_id=None)

    for paper in sorted(original["papers.jsonl"], key=lambda p: p["paper_id"]):
        counts["papers_input"] += 1
        if registry.get(paper["paper_id"], {}).get("status") != "cvf_verified" or paper["scope"] != "core" or paper["track"] != "main":
            review(paper, "status", "paper_not_accepted_core_main")
            continue
        counts["papers_processed"] += 1
        for field in ("title", "abstract"):
            if paper[field] is None and paper[field + "_text_version_id"] is None:
                counts["missing_fields"] += 1
                continue
            try:
                text = field_binding(paper, field, texts, sources, provenance)
            except ValueError as exc:
                review(paper, field, "invalid_text_binding: " + str(exc))
                counts["invalid_fields"] += 1
                continue
            counts["fields_processed"] += 1
            for c in extractor.candidates(text["normalized_text"], field):
                counts["candidate_mentions"] += 1
                ent, source = extractor.entities[c.entity_id], sources[text["source_record_id"]]
                ev = dict(evidence_kind="nlp", paper_id=paper["paper_id"], source_record_id=source["source_record_id"],
                    source_url=source["url"], field_path=text["field_path"], evidence_text=text["normalized_text"][c.start:c.end],
                    start_char=c.start, end_char=c.end, rule_id=c.rule_id or "a4-review", rule_version=RULE_VERSION,
                    captured_at=text["captured_at"], supporting_evidence_ids=[], owner=paper["owner"],
                    text_version_id=text["text_version_id"], normalized_text_sha256=text["normalized_text_sha256"], normalization_version=text["normalization_version"])
                ev["evidence_id"] = evidence_id(ev)
                evidence[ev["evidence_id"]] = ev
                if c.reason:
                    review(paper, field, c.reason, c, ev)
                    continue
                typ = {"Task": "STUDIES_TASK", "Dataset": "EVALUATED_ON", "Method": "USES_METHOD"}[ent["label"]]
                eid = identifier("edge", paper["paper_id"], typ, ent["id"])
                edge = edges.setdefault(eid, dict(edge_id=eid, src=paper["paper_id"], dst=ent["id"], type=typ, weight=1,
                    derivation="nlp", validation_status="accepted", evidence_ids=[], paper_ids=[paper["paper_id"]],
                    owner=paper["owner"], source_origin=[], project_id=project_id))
                edge["evidence_ids"] = sorted(set(edge["evidence_ids"] + [ev["evidence_id"]]))
                edge["source_origin"] = sorted(set(edge["source_origin"] + [source["source"]]))
                node = nodes.setdefault(ent["id"], dict(id=ent["id"], label=ent["label"], name=ent["name"], owner=paper["owner"],
                    source_origin=[], source_record_ids=[], validation_status="accepted", project_id=project_id,
                    properties_json={k: ent[k] for k in contract()["node_properties"][ent["label"]] if k in ent}))
                node["source_origin"] = sorted(set(node["source_origin"] + [source["source"]]))
                node["source_record_ids"] = sorted(set(node["source_record_ids"] + [source["source_record_id"]]))
                node["owner"] = "|".join(sorted(set(node["owner"].split("|") + [paper["owner"]])))
    data = dict(zip(TABLES, [sorted(v.values(), key=canonical_json) for v in (nodes, edges, evidence, reviews)]))
    validate_nlp(data, original, project_id)
    counts.update({"nodes": len(nodes), "edges": len(edges), "evidence": len(evidence),
                   "accepted_evidence": len({i for e in edges.values() for i in e["evidence_ids"]}),
                   "rejected": sum(r["review_status"] == "rejected" for r in reviews.values()),
                   "review_open": sum(r["review_status"] == "open" for r in reviews.values())})
    return data, {**dict(counts), "counts_by_label": dict(Counter(n["label"] for n in nodes.values())),
                  "counts_by_type": dict(Counter(e["type"] for e in edges.values())),
                  "review_by_reason": dict(Counter(r["reason"] for r in reviews.values()))}


def code_version(extractor):
    return CODE_VERSION + ("+b5-1.0.0" if extractor.method_dictionary else "")


def dictionary_versions(extractor):
    version = lambda d: d["version"] + ":" + sha256(canonical_json(d).encode())
    result = {"a4-cv": version(extractor.base_dictionary)}
    if extractor.method_dictionary:
        result["b5-method"] = version(extractor.method_dictionary)
    return result


def prepare(root, config_path):
    cfg = json.loads(within(root, config_path).read_text(encoding="utf-8"))
    if not {"input_manifests", "output_dir", "dictionary", "model"} <= set(cfg) <= {"input_manifests", "output_dir", "dictionary", "model", "method_dictionary"} or not cfg["input_manifests"]:
        raise ValueError("Invalid A4 config")
    out = within(root, cfg["output_dir"])
    if not out.is_relative_to(within(root, "data/processed")):
        raise ValueError("A4 output must be under data/processed")
    manifests, original = load_inputs(root, cfg["input_manifests"])
    protected = [within(root, f["path"]) for m in manifests for f in m["files"]]
    if any(within(root, p).is_relative_to(out) for p in cfg["input_manifests"]) or any(p.is_relative_to(out) for p in protected):
        raise ValueError("A4 output overlaps input snapshot")
    dictionary = json.loads(within(root, cfg["dictionary"]).read_text(encoding="utf-8"))
    method_dictionary = None
    if cfg.get("method_dictionary"):
        method_dictionary = json.loads(within(root, cfg["method_dictionary"]).read_text(encoding="utf-8"))
    extractor = Extractor({**dictionary, "methods": method_dictionary["methods"]} if method_dictionary else dictionary, cfg["model"])
    extractor.base_dictionary, extractor.method_dictionary = dictionary, method_dictionary
    data, summary = extract(original, extractor)
    return cfg, manifests, original, extractor, data, summary


def run(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    cfg, inputs, original, extractor, data, summary = prepare(root, config_path)
    spec, files, contents = contract(), [], {}
    for name in TABLES:
        body = record_bytes(name, spec["files"][name]["fields"], data[name])
        path = cfg["output_dir"] + "/" + name
        files.append(dict(path=path, sha256=sha256(body), record_count=len(data[name]), role=spec["files"][name]["stage"]))
        contents[within(root, path)] = body
    manifest = dict(project_id=spec["project_id"], schema_version=spec["schema_version"], code_version=code_version(extractor),
        normalization_version="nfc-ws-1", parser_versions=sorted({v for m in inputs for v in m["parser_versions"]} | {extractor.runtime}),
        rule_versions={k: RULE_VERSION for k in (*RULE_IDS, *(METHOD_RULE_IDS if extractor.method_dictionary else ()), "a4-review")},
        dictionary_versions=dictionary_versions(extractor),
        applied_decision_ids=[], graph_ready=False, node_count=None, edge_count=None, files=files,
        source_snapshot_id=identifier("snapshot:v2", *[m["snapshot_id"] for m in inputs]),
        created_at=max(m["created_at"] for m in inputs))
    manifest["snapshot_id"] = "snapshot:v2:" + sha256(canonical_json(snapshot_payload(manifest)).encode())
    # Adapter metadata is outside table schemas; evidence section is recovered from paper text-version IDs.
    manifest["input_manifests"] = cfg["input_manifests"]
    manifest["config_path"] = config_path
    manifest["model"] = extractor.model
    summary.update(snapshot_id=manifest["snapshot_id"], graph_ready=False, model=extractor.runtime, network_requests=0)
    contents[within(root, cfg["output_dir"] + "/summary.json")] = json_bytes(summary)
    contents[within(root, cfg["output_dir"] + "/snapshot_manifest.json")] = json_bytes(manifest)
    publish(contents)  # Refuses a different existing output; immutable, resumable, manifest last.
    return summary
