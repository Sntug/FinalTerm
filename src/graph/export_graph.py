"""Combine A (CVPR 2024) + B (ICCV 2023) A3 outputs into one accepted-only graph snapshot (contract v2)."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "handoff/mxh_contract_v2"))
from contract_v2.migrate import read_csv, read_jsonl, write_records  # noqa: E402
from contract_v2.model import NODE_PROPERTIES  # noqa: E402
from contract_v2.text import canonical_json, identifier, sha256  # noqa: E402

CONFIG = ROOT / "config/b_graph_700.json"
PUBLISH = ("project_id schema_version code_version normalization_version parser_versions rule_versions "
           "dictionary_versions applied_decision_ids graph_ready node_count edge_count files").split()


def origin(ids):
    return sorted({"CVF" if i.startswith("source:cvf:") else "OpenAlex" if i.startswith("source:openalex:") else i.split(":")[1] for i in ids})


def owners(*values):
    return "|".join(sorted({o for v in values for o in v.split("|")}))


def props(label, record):
    return {k: record[k] for k in NODE_PROPERTIES[label] if record.get(k) is not None}


def merge_node(old, new, conflicts):
    """Same id from both teams: union lists, old (A) wins scalar conflicts."""
    old["source_origin"] = sorted(set(old["source_origin"]) | set(new["source_origin"]))
    old["source_record_ids"] = sorted(set(old["source_record_ids"]) | set(new["source_record_ids"]))
    old["owner"] = owners(old["owner"], new["owner"])
    if old["name"] != new["name"]:
        conflicts.append((old["id"], "name", old["name"], new["name"]))
    for k, v in new["properties_json"].items():
        cur = old["properties_json"].get(k)
        if k == "aliases":
            old["properties_json"][k] = sorted(set(cur or []) | set(v))
        elif cur is None:
            old["properties_json"][k] = v
        elif cur != v:
            conflicts.append((old["id"], k, cur, v))


def build(cfg, root=ROOT):
    pid = cfg["project_id"]
    nodes, conflicts, report = {}, [], {}
    papers, registry, authorships, evidence, inputs = {}, {}, [], defaultdict(set), []
    manifests = []
    for inp in cfg["inputs"]:
        snaps = sorted(p for p in (root / inp["snapshots_dir"]).iterdir() if p.is_dir())
        assert len(snaps) == 1, f"expected one snapshot dir in {inp['snapshots_dir']}"
        a3 = root / inp["a3_dir"]
        for p in read_jsonl(snaps[0] / "papers.jsonl"):
            papers[p["paper_id"]] = p
        registry.update({r["paper_id"]: r for r in read_csv(snaps[0] / "paper_registry.csv")})
        authorships += read_csv(a3 / "authorships.csv")
        for e in read_jsonl(a3 / "evidence.jsonl"):
            evidence[(e["paper_id"], e["source_record_id"])].add(e["evidence_id"])
        for r in read_csv(a3 / "nodes.csv"):
            if r["validation_status"] != "accepted":
                continue
            n = dict(id=r["id"], label=r["label"], name=r["name"], owner=r["owner"], source_origin=json.loads(r["source_origin"]),
                     source_record_ids=json.loads(r["source_record_ids"]), validation_status="accepted", project_id=pid,
                     properties_json=props(r["label"], json.loads(r["properties_json"])))
            if r["id"] in nodes:
                merge_node(nodes[r["id"]], n, conflicts)
            else:
                nodes[r["id"]] = n
        m = json.loads((snaps[0] / "snapshot_manifest.json").read_text(encoding="utf-8"))
        m3 = json.loads((a3 / "snapshot_manifest.json").read_text(encoding="utf-8"))
        manifests += [m, m3]
        inputs.append({"name": inp["name"], "papers_snapshot_id": m["snapshot_id"], "a3_snapshot_id": m3["snapshot_id"]})
    report["paper_status"] = dict(Counter(r["status"] for r in registry.values()))
    report["name_prop_conflicts"] = conflicts

    # Paper / VenueEdition
    accepted = {i for i, r in registry.items() if r["status"] == "cvf_verified"}
    venues = {}
    for i in sorted(accepted):
        p = papers[i]
        ids = [p["representative_source_record_id"]] + ([p["citation_count_source_record_id"]] if p.get("citation_count_source_record_id") else [])
        nodes[i] = dict(id=i, label="Paper", name=p["title"], owner=p["owner"], source_origin=origin(ids), source_record_ids=sorted(ids),
                        validation_status="accepted", project_id=pid, properties_json=props("Paper", p))
        v = venues.setdefault(p["venue_id"], dict(id=p["venue_id"], label="VenueEdition", name=f"{p['conference']} {p['conference_year']} ({p['track']})",
                              owner=p["owner"], source_origin=["CVF"], source_record_ids=[], validation_status="accepted", project_id=pid,
                              properties_json=props("VenueEdition", p)))
        v["owner"] = owners(v["owner"], p["owner"])
    nodes.update(venues)

    # Country
    for n in [n for n in nodes.values() if n["label"] == "Institution" and n["properties_json"].get("country_code")]:
        cid = "country:" + n["properties_json"]["country_code"]
        c = nodes.setdefault(cid, dict(id=cid, label="Country", name=cid[8:], owner=n["owner"], source_origin=[], source_record_ids=[],
                                       validation_status="accepted", project_id=pid, properties_json={"country_code": cid[8:]}))
        c["owner"] = owners(c["owner"], n["owner"])
        c["source_origin"] = sorted(set(c["source_origin"]) | set(n["source_origin"]))
        c["source_record_ids"] = sorted(set(c["source_record_ids"]) | set(n["source_record_ids"]))

    # Edges keyed by (src,type,dst); repeated support merges instead of multiplying.
    edges = {}

    def add(src, typ, dst, owner, paper_ids, srcs):
        e = edges.setdefault((src, typ, dst), dict(owner=owner, papers=set(), srcs=set()))
        e["owner"] = owners(e["owner"], owner)
        e["papers"] |= set(paper_ids)
        e["srcs"] |= set(srcs)

    for a in authorships:
        if a["paper_id"] not in accepted or a["identity_status"] != "resolved" or not a["author_id"]:
            continue
        add(a["author_id"], "AUTHORED", a["paper_id"], a["owner"], [a["paper_id"]], [a["identity_source_record_id"]])
        if a["affiliation_status"] == "verified" and a["institution_id"]:
            add(a["author_id"], "AFFILIATED_WITH", a["institution_id"], a["owner"], [a["paper_id"]], [a["affiliation_source_record_id"]])
    # evidence for AFFILIATED_WITH needs per-paper pairing: recompute with (paper, source) pairs
    pair_ev = defaultdict(set)
    for a in authorships:
        if a["paper_id"] in accepted and a["author_id"] and a["identity_source_record_id"]:
            pair_ev[(a["author_id"], "AUTHORED", a["paper_id"])] |= evidence.get((a["paper_id"], a["identity_source_record_id"]), set())
        if a["paper_id"] in accepted and a["author_id"] and a["institution_id"] and a["affiliation_status"] == "verified":
            pair_ev[(a["author_id"], "AFFILIATED_WITH", a["institution_id"])] |= evidence.get((a["paper_id"], a["affiliation_source_record_id"]), set())
    by_oa = defaultdict(list)
    for i in accepted:
        if papers[i].get("openalex_id"):
            by_oa[papers[i]["openalex_id"]].append(i)
    assert all(len(v) == 1 for v in by_oa.values()), "duplicate openalex_id among core papers"
    for i in sorted(accepted):
        p = papers[i]
        rep = p["representative_source_record_id"]
        add(i, "PUBLISHED_IN", p["venue_id"], p["owner"], [i], [rep])
        pair_ev[(i, "PUBLISHED_IN", p["venue_id"])] |= evidence.get((i, rep), set())
        for ref in p.get("referenced_works") or []:
            if ref in by_oa and by_oa[ref][0] != i:
                dst = by_oa[ref][0]
                srcs = [rep] + ([p["citation_count_source_record_id"]] if p.get("citation_count_source_record_id") else [])
                add(i, "CITES", dst, p["owner"], [i], srcs)
                pair_ev[(i, "CITES", dst)] |= set().union(*(evidence.get((i, s), set()) for s in srcs))
    inst_papers = defaultdict(set)
    for (s, t, d), e in edges.items():
        if t == "AFFILIATED_WITH":
            inst_papers[d] |= e["papers"]
    for iid in sorted(inst_papers):
        cc = nodes[iid]["properties_json"].get("country_code")
        if cc:  # BASED_IN supported by the papers whose verified affiliations use this institution
            add(iid, "BASED_IN", "country:" + cc, nodes[iid]["owner"], inst_papers[iid], nodes[iid]["source_record_ids"])
    for iid, n in nodes.items():  # institutions with country but no verified affiliation still need BASED_IN
        cc = n["properties_json"].get("country_code")
        if n["label"] == "Institution" and cc and (iid, "BASED_IN", "country:" + cc) not in edges:
            add(iid, "BASED_IN", "country:" + cc, n["owner"], [], n["source_record_ids"])

    rows = []
    for (s, t, d), e in sorted(edges.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])):
        assert s in nodes and d in nodes, f"dangling edge endpoint {s} {t} {d}"
        rows.append(dict(edge_id=identifier("edge", s, t, d), src=s, dst=d, type=t, weight=1, derivation="metadata",
                         validation_status="accepted", evidence_ids=sorted(pair_ev.get((s, t, d), set())), paper_ids=sorted(e["papers"]),
                         owner=e["owner"], source_origin=origin(e["srcs"]) if e["srcs"] else [], project_id=pid))
    return sorted(nodes.values(), key=lambda n: (n["label"], n["id"])), rows, manifests, inputs, report


def export(cfg=None, root=ROOT, out_dir=None):
    cfg = cfg or json.loads(CONFIG.read_text(encoding="utf-8"))
    nodes, edges, manifests, inputs, report = build(cfg, root)
    out = Path(out_dir) if out_dir else root / cfg["output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    write_records(out / "nodes.csv", nodes)
    write_records(out / "edges.csv", edges)
    rel = Path(cfg["output_dir"])
    files = [dict(path=str(rel / f), sha256=sha256((out / f).read_bytes()), record_count=len(r), role="graph")
             for f, r in (("nodes.csv", nodes), ("edges.csv", edges))]
    merge = lambda key: sorted({x for m in manifests for x in m[key]})
    manifest = dict(
        project_id=cfg["project_id"], schema_version="2.0.0", code_version=cfg["code_version"], normalization_version="nfc-ws-1",
        parser_versions=merge("parser_versions"),
        rule_versions={**{k: v for m in manifests for k, v in m["rule_versions"].items()}, "b3-graph-export": "1.0.0"},
        dictionary_versions={k: v for m in manifests for k, v in m["dictionary_versions"].items()},
        applied_decision_ids=merge("applied_decision_ids"), graph_ready=True, node_count=len(nodes), edge_count=len(edges), files=files)
    manifest["snapshot_id"] = "snapshot:v2:" + sha256(canonical_json({k: manifest[k] for k in PUBLISH}).encode())
    # deterministic: latest input timestamp instead of wall clock
    manifest["created_at"] = max(m["created_at"] for m in manifests)
    manifest["source_snapshot_id"] = "snapshot:v2:" + sha256(canonical_json(inputs).encode())
    manifest["input_snapshots"] = inputs
    manifest["counts_by_label"] = dict(sorted(Counter(n["label"] for n in nodes).items()))
    manifest["counts_by_type"] = dict(sorted(Counter(e["type"] for e in edges).items()))
    (out / "snapshot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest, report


if __name__ == "__main__":
    m, r = export()
    print(json.dumps({k: m[k] for k in ("snapshot_id", "node_count", "edge_count", "counts_by_label", "counts_by_type")}, indent=1))
    print("paper registry status:", r["paper_status"])
    print("property conflicts:", r["name_prop_conflicts"])
