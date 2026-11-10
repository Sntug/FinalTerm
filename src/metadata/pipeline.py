"""Immutable A5 verification snapshot and compact, source-backed comparison sidecars."""
from collections import Counter, defaultdict
import csv
import gzip
import io
import json
from pathlib import Path

from src.nlp.validation import read_manifest, verify_graph_contract
from src.collect.common import REPO_ROOT, within, publish, json_bytes, record_bytes
from src.collect.contract import contract, validate_records
from src.collect.pilot import snapshot_payload
from src.clean.text import canonical_json, identifier, sha256
from src.clean.normalize import doi, arxiv, openalex
from src.clean.verify import validate_integrity
from .audit import crosscheck, lookup_plan, RULE, VERSION, COMPARISON_FIELDS
from .sources import SupplementalCache

DEFAULT_CONFIG = "config/a_cvpr2024_a5.json"
CODE_VERSION = "a5-metadata-1.0.0"


def load(root, config_path):
    cfg = json.loads(within(root, config_path).read_text(encoding="utf-8"))
    required = {"input_manifest", "processed_dir", "raw_dir", "conference", "conference_year", "target_count", "max_arxiv_papers", "max_crossref_papers", "delay_seconds", "retries", "timeout_seconds", "max_retry_wait_seconds"}
    if set(cfg) != required or (cfg["conference"], cfg["conference_year"]) not in (("CVPR", 2024), ("ICCV", 2023)):
        raise ValueError("Invalid A5 config/edition")
    corpus = cfg["conference"].lower() + str(cfg["conference_year"])
    out = within(root, cfg["processed_dir"])
    if not out.is_relative_to(within(root, "data/processed/" + corpus)) or not within(root, cfg["raw_dir"]).is_relative_to(within(root, "data/raw/" + corpus)):
        raise ValueError("A5 output/cache outside configured corpus")
    for key, limit in (("max_arxiv_papers", 20), ("max_crossref_papers", 10), ("retries", 3), ("target_count", 350)):
        if type(cfg[key]) is not int or not 0 <= cfg[key] <= limit or key == "target_count" and cfg[key] == 0:
            raise ValueError("Invalid bounded setting: " + key)
    if cfg["delay_seconds"] < 3 or not 0 < cfg["timeout_seconds"] <= 60 or not 0 <= cfg["max_retry_wait_seconds"] <= 60:
        raise ValueError("Invalid transport timing")
    source, data = read_manifest(root, cfg["input_manifest"], contract()["files"])
    if out.is_relative_to(within(root, cfg["input_manifest"]).parent) or any(within(root, f["path"]).is_relative_to(out) for f in source["files"]):
        raise ValueError("A5 output overlaps locked input")
    validate_integrity(data)
    if len(data["papers.jsonl"]) != cfg["target_count"] or any((p["conference"], p["conference_year"], p["scope"], p["track"]) != (cfg["conference"], cfg["conference_year"], "core", "main") for p in data["papers.jsonl"]):
        raise ValueError("A5 paper scope/count mismatch")
    bodies = {}
    for s in data["source_records.jsonl"]:
        path = within(root, s["raw_path"])
        if not path.is_relative_to(within(root, "data/raw")):
            raise ValueError("Source raw outside data/raw")
        body = gzip.decompress(path.read_bytes())
        if sha256(body) != s["content_sha256"] or s["http_status"] != 200 or s["source_record_id"] != identifier("source:" + s["source"].lower(), s["url"], s["content_sha256"]):
            raise ValueError("Raw source hash/identity mismatch")
        bodies[s["source_record_id"]] = body
    return cfg, source, data, bodies


def fetch_selected(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    cfg, source, original, bodies = load(root, config_path)
    cache = SupplementalCache(root, cfg, offline=False)
    plan = lookup_plan(original, bodies, cfg)
    results = [cache.fetch(item) for item in plan]
    return dict(planned=len(plan), network_requests_this_run=cache.network_requests,
                results=[{k: item[k] for k in ("paper_id", "source", "url", "status", "reason")} for item in results])


def comparisons_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COMPARISON_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: canonical_json(v) if isinstance(v, list) else v for k, v in row.items()})
    return stream.getvalue().encode("utf-8-sig")


def summarize(original, audit, plan, lookups):
    data = audit.data
    groups = defaultdict(list)
    for row in data["authorships.csv"]:
        groups[row["authorship_id"]].append(row)
    comparisons = list(audit.comparisons.values())
    papers = data["papers.jsonl"]
    return dict(papers_reviewed=len(papers), source_records_before=len(original["source_records.jsonl"]), source_records_after=len(data["source_records.jsonl"]),
        sources_added=len(data["source_records.jsonl"]) - len(original["source_records.jsonl"]),
        paper_ids_syntax_valid={"cvf": len(papers), "doi": sum(bool(doi(p["doi"])) for p in papers), "openalex": sum(bool(openalex(p["openalex_id"], "W")) for p in papers), "arxiv": sum(bool(arxiv(p["arxiv_url"])) for p in papers)},
        papers_with_verified_openalex=sum(c["field_name"] == "openalex_id" and c["result"] == "matched" for c in comparisons),
        papers_with_verified_doi=sum(c["field_name"] == "doi" and c["result"] == "matched" and json.loads(c["observed_value_json"]) is not None or c["field_name"] == "doi_registry" and c["result"] == "updated" for c in comparisons),
        arxiv_preprints_matched=sum(c["field_name"] == "arxiv_metadata" and c["result"] == "matched" for c in comparisons),
        papers_updated=len(audit.updated_papers), authors_updated=0, institutions_updated=0, affiliations_updated=0,
        distinct_authorships=len(groups), authorships_without_author_id=sum(not rows[0]["author_id"] for rows in groups.values()),
        authorships_without_institution_id=sum(not any(r["institution_id"] for r in rows) for rows in groups.values()),
        authorship_rows_missing_institution=sum(not r["institution_id"] for r in data["authorships.csv"]),
        distinct_authors=len({r["author_id"] for r in data["authorships.csv"] if r["author_id"]}),
        distinct_institutions=len({r["institution_id"] for r in data["authorships.csv"] if r["institution_id"]}),
        comparisons=len(comparisons), comparisons_by_result=dict(Counter(c["result"] for c in comparisons)),
        conflicts=sum(c["result"] == "conflict" for c in comparisons), unresolved=sum(c["result"] == "unresolved" for c in comparisons),
        reviews_before=len(original["needs_review.csv"]), reviews_after=len(data["needs_review.csv"]),
        reviews_added=len(data["needs_review.csv"]) - len(original["needs_review.csv"]), open_reviews=sum(r["review_status"] == "open" for r in data["needs_review.csv"]),
        lookups_planned=len(plan), lookups_by_status=dict(Counter(x["status"] for x in lookups)),
        network_requests_recorded=sum(x["network_requests"] for x in lookups),
        lookup_sources_unavailable=sum(x["status"] == "unavailable" for x in lookups),
        graph_ready=False, graph_rebuild_required=bool(audit.updated_papers), nlp_text_versions_changed=False,
        automatic_identity_merges=0, processing_errors=0,
        limitation="Cached Work matches verify consistency of conference metadata, not independent human identity. Unfetched/unavailable preprints and unresolved identities remain unverified.")


def prepare(root, config_path):
    cfg, source, original, bodies = load(root, config_path)
    plan = lookup_plan(original, bodies, cfg)
    cache = SupplementalCache(root, cfg, offline=True)
    lookups = [cache.fetch(item) for item in plan]
    for item in lookups:
        s = item["source_record"]
        if s:
            if (s["paper_id"], s["url"], s["source"]) != (item["paper_id"], item["url"], item["source"]) or s["source_record_id"] != identifier("source:" + s["source"].lower(), s["url"], s["content_sha256"]):
                raise ValueError("Supplemental source binding mismatch")
            bodies[s["source_record_id"]] = cache.body(s)
    created = max([source["created_at"]] + [i["source_record"]["fetched_at"] for i in lookups if i["source_record"]])
    audit = crosscheck(original, bodies, source["snapshot_id"], created, lookups)
    # All shared table schemas plus A3 identity/provenance invariants are reused unchanged.
    validate_integrity(audit.data)
    return cfg, source, original, audit, plan, lookups, summarize(original, audit, plan, lookups), created


def make_output(root, config_path):
    cfg, source, original, audit, plan, lookups, summary, created = prepare(root, config_path)
    spec, output, files = contract(), {}, []
    directory = cfg["processed_dir"]
    for name, rows in audit.data.items():
        validate_records(name, rows)
        path = directory + "/" + name
        body = record_bytes(name, spec["files"][name]["fields"], rows)
        output[within(root, path)] = body
        files.append(dict(path=path, sha256=sha256(body), record_count=len(rows), role=spec["files"][name]["stage"]))
    comparison_path = directory + "/metadata_comparison.csv"
    comparison_body = comparisons_bytes(sorted(audit.comparisons.values(), key=lambda r: r["comparison_id"]))
    lookup_body = json_bytes(lookups)
    impact = dict(paper_ids=sorted(audit.updated_papers), authorship_ids=[], changed_fields=["doi"] if audit.updated_papers else [],
                  author_ids_changed=False, institution_ids_changed=False, affiliations_changed=False, text_versions_changed=False,
                  regenerate_graph=bool(audit.updated_papers), revalidate_a4_manifest_binding=True,
                  note="A5 does not emit a final graph or modify Neo4j. Use B exporter to rebuild after choosing this snapshot; old A4 adapter inputs must be rebound/replayed for a new metadata manifest.")
    manifest = dict(project_id=spec["project_id"], schema_version=spec["schema_version"], code_version=CODE_VERSION,
        source_snapshot_id=source["snapshot_id"], created_at=created, normalization_version=source["normalization_version"],
        parser_versions=sorted(set(source["parser_versions"] + ["a5-source-metadata-1.0.0"])),
        rule_versions={**source["rule_versions"], RULE: VERSION}, dictionary_versions=source["dictionary_versions"],
        applied_decision_ids=source["applied_decision_ids"] + [d["decision_id"] for d in audit.data["merge_log.jsonl"] if d["decision_id"] not in source["applied_decision_ids"]],
        graph_ready=False, node_count=None, edge_count=None, files=sorted(files, key=lambda f: f["path"]))
    manifest["snapshot_id"] = "snapshot:v2:" + sha256(canonical_json(snapshot_payload(manifest)).encode())
    manifest["verification_artifacts"] = {"metadata_comparison.csv": sha256(comparison_body), "lookup_results.json": sha256(lookup_body), "graph_impact.json": sha256(json_bytes(impact))}
    summary.update(snapshot_id=manifest["snapshot_id"], source_snapshot_id=source["snapshot_id"])
    output[within(root, comparison_path)] = comparison_body
    output[within(root, directory + "/lookup_results.json")] = lookup_body
    output[within(root, directory + "/graph_impact.json")] = json_bytes(impact)
    output[within(root, directory + "/summary.json")] = json_bytes(summary)
    # B's existing API reads Paper tables from one child snapshot directory.
    for name in ("papers.jsonl", "paper_registry.csv"):
        output[within(root, directory + "/paper_snapshots/current/" + name)] = output[within(root, directory + "/" + name)]
    output[within(root, directory + "/paper_snapshots/current/snapshot_manifest.json")] = json_bytes(manifest)
    output[within(root, directory + "/snapshot_manifest.json")] = json_bytes(manifest)
    return manifest, output, summary


def run(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    manifest, output, summary = make_output(root, config_path)
    contents = {p.name: body for p, body in output.items() if p.name in contract()["files"]}
    verify_graph_contract(root, manifest, contents)  # Original Contract v2 verifier, graph_ready stays false.
    publish(output)
    return summary


def exporter_input(config, name=None):
    return dict(name=name or config["conference"] + str(config["conference_year"]),
                snapshots_dir=config["processed_dir"] + "/paper_snapshots", a3_dir=config["processed_dir"])
