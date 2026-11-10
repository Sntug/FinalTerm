"""Deterministic samples and strict aggregation of human-supplied judgments."""
from collections import Counter
import csv
import io
import json
from datetime import datetime

from src.clean.text import canonical_json, identifier, sha256
from src.collect.contract import contract

RATINGS = {"correct", "incorrect", "unverifiable", "pending_review"}
ERROR_GROUPS = {"identity", "affiliation", "nlp_relation", "citation", "missing_evidence", "time_or_version", "other"}
REVIEW_FIELDS = "review_status error_group review_notes reviewer_name reviewed_at".split()
EDGE_FIELDS = ("sample_id edge_id type src dst src_name dst_name weight paper_ids owner rule_owner assigned_reviewer review_phase "
               "evidence_ids evidence_json evidence_context_note automatic_issue_ids").split() + REVIEW_FIELDS
NODE_FIELDS = ("sample_id node_id label name owner properties_json source_record_ids paper_ids selection_reasons automatic_issue_ids "
               "assigned_reviewer evidence_json").split() + REVIEW_FIELDS


def rank(seed, value):
    return sha256((str(seed) + "\0" + value).encode())


def csv_bytes(fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: canonical_json(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    return stream.getvalue().encode("utf-8-sig")


def pending():
    return dict(review_status="pending_review", error_group="", review_notes="", reviewer_name="", reviewed_at="")


def samples(data, manifest, issues, risks, cfg):
    seed = cfg["seed"]
    evidence = {e["evidence_id"]: e for e in data["evidence.jsonl"]}
    nodes = {n["id"]: n for n in data["nodes.csv"]}
    issues_by_edge, issues_by_node = {}, {}
    for issue in issues:
        for key in issue["edge_ids"]:
            issues_by_edge.setdefault(key, []).append(issue["issue_id"])
        for key in issue["entity_ids"]:
            issues_by_node.setdefault(key, []).append(issue["issue_id"])
    edges, counts = [], Counter()
    strata = {}
    for typ in [r["type"] for r in contract()["relations"]]:
        candidates = sorted((e for e in data["edges.csv"] if e["type"] == typ and e["validation_status"] == "accepted"), key=lambda e: rank(seed, e["edge_id"]))
        selected = candidates[:cfg["edges_per_type"]]
        strata[typ] = dict(available=len(candidates), sampled=len(selected), requested=cfg["edges_per_type"])
        for e in selected:
            reviewer = min(("A", "B"), key=lambda a: (counts[a], a))
            counts[reviewer] += 1
            row = dict(sample_id=identifier("a6-edge-sample", manifest["snapshot_id"], e["edge_id"], "primary", reviewer, str(seed)),
                edge_id=e["edge_id"], type=typ, src=e["src"], dst=e["dst"], src_name=nodes[e["src"]]["name"], dst_name=nodes[e["dst"]]["name"],
                weight=e["weight"], paper_ids=e["paper_ids"], owner=e["owner"], rule_owner="A" if typ in ("STUDIES_TASK", "EVALUATED_ON") else "B",
                assigned_reviewer=reviewer, review_phase="primary", evidence_ids=e["evidence_ids"],
                evidence_json=[evidence[i] for i in sorted(e["evidence_ids"], key=lambda i: rank(seed, i))[:3] if i in evidence],
                evidence_context_note=f"Up to 3 exact records shown; all {len(e['evidence_ids'])} IDs retained. Read full evidence.jsonl from the graph manifest for all supporting records.",
                automatic_issue_ids=sorted(issues_by_edge.get(e["edge_id"], [])), **pending())
            edges.append(row)
    for primary in ("A", "B"):
        pool = [e for e in edges if e["review_phase"] == "primary" and e["assigned_reviewer"] == primary]
        # Prefer one per relation; deterministic fallback handles sparse types.
        chosen = []
        for typ in [r["type"] for r in contract()["relations"]]:
            group = sorted((e for e in pool if e["type"] == typ), key=lambda e: rank(seed, "cross" + e["edge_id"]))
            if group and len(chosen) < cfg["cross_reviews_per_person"]:
                chosen.append(group[0])
        rest = sorted((e for e in pool if e not in chosen), key=lambda e: rank(seed, "cross" + e["edge_id"]))
        chosen += rest[:max(0, cfg["cross_reviews_per_person"] - len(chosen))]
        reviewer = "B" if primary == "A" else "A"
        for e in chosen:
            edges.append({**e, "sample_id": identifier("a6-edge-sample", manifest["snapshot_id"], e["edge_id"], "cross", reviewer, str(seed)),
                          "assigned_reviewer": reviewer, "review_phase": "cross", **pending()})
    papers_by_node, evidence_by_node = {}, {}
    for edge in data["edges.csv"]:
        for cid in (edge["src"], edge["dst"]):
            papers_by_node.setdefault(cid, set()).update(edge["paper_ids"])
            evidence_by_node.setdefault(cid, set()).update(edge["evidence_ids"])
    candidates = [n for n in nodes.values() if n["id"] in risks and n["label"] in ("Author", "Institution")]
    score = lambda n: (-(100 * sum("conflicting" in r for r in risks[n["id"]]) + 20 * sum("same normalized name" in r for r in risks[n["id"]]) + len(issues_by_node.get(n["id"], []))), rank(seed, n["id"]))
    node_rows = []
    for index, n in enumerate(sorted(candidates, key=score)[:cfg["node_count"]]):
        # Include representative evidence for up to five supporting papers; all source IDs remain in the row.
        evs, represented = [], set()
        for eid in sorted(evidence_by_node.get(n["id"], set()), key=lambda i: rank(seed, i)):
            if eid in evidence and evidence[eid]["paper_id"] not in represented:
                evs.append(evidence[eid])
                represented.add(evidence[eid]["paper_id"])
            if len(evs) == 5:
                break
        node_rows.append(dict(sample_id=identifier("a6-node-sample", manifest["snapshot_id"], n["id"], str(seed)), node_id=n["id"], label=n["label"],
            name=n["name"], owner=n["owner"], properties_json=n["properties_json"], source_record_ids=n["source_record_ids"],
            paper_ids=sorted(papers_by_node.get(n["id"], set())), selection_reasons=sorted(risks[n["id"]]),
            automatic_issue_ids=sorted(issues_by_node.get(n["id"], [])), assigned_reviewer="A" if index % 2 == 0 else "B", evidence_json=evs, **pending()))
    return edges, node_rows, dict(strata=strata, primary_by_reviewer=dict(counts),
        unique_edges=sum(counts.values()), cross_review_rows=sum(e["review_phase"] == "cross" for e in edges),
        nodes_sampled=len(node_rows), node_candidates=len(candidates))


def decode_csv(body):
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline="")))


def form_fingerprint(rows):
    fixed = sorted(({k: v for k, v in row.items() if k not in REVIEW_FIELDS} for row in rows), key=lambda r: r["sample_id"])
    return sha256(canonical_json(fixed).encode())


def human_summary(edge_rows, node_rows):
    seen = set()
    for row in edge_rows + node_rows:
        if row["sample_id"] in seen or row["assigned_reviewer"] not in ("A", "B"):
            raise ValueError("Duplicate sample ID or invalid reviewer assignment")
        seen.add(row["sample_id"])
        if row["review_status"] not in RATINGS or row["error_group"] and row["error_group"] not in ERROR_GROUPS:
            raise ValueError("Invalid review status/error group")
        if row["review_status"] != "pending_review":
            if not row["reviewer_name"].strip() or not row["reviewed_at"].strip():
                raise ValueError("Graded rows require a human reviewer name and timestamp")
            date = datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError("Review timestamp must include timezone")
            if row["review_status"] in ("incorrect", "unverifiable") and (not row["error_group"] or not row["review_notes"].strip()):
                raise ValueError("Negative/unverifiable judgments require error group and explanation")
    primary = [r for r in edge_rows if r["review_phase"] == "primary"]
    if any(r["review_phase"] not in ("primary", "cross") for r in edge_rows):
        raise ValueError("Invalid edge review phase")
    def metric(rows):
        counts = Counter(r["review_status"] for r in rows)
        graded = len(rows) - counts["pending_review"]
        return dict(total=len(rows), graded=graded, pending=counts["pending_review"], correct=counts["correct"], incorrect=counts["incorrect"],
                    unverifiable=counts["unverifiable"], conservative_precision=counts["correct"] / graded if graded else None)
    index = {r["edge_id"]: r for r in primary}
    agreement, disagreements = 0, []
    for r in (r for r in edge_rows if r["review_phase"] == "cross"):
        p = index.get(r["edge_id"])
        if not p or p["assigned_reviewer"] == r["assigned_reviewer"]:
            raise ValueError("Cross-review must refer to the other person's primary sample")
        if p["review_status"] != "pending_review" and r["review_status"] != "pending_review":
            if p["review_status"] == r["review_status"]:
                agreement += 1
            else:
                disagreements.append(r["edge_id"])
    result = dict(primary=metric(primary), cross=metric([r for r in edge_rows if r["review_phase"] == "cross"]), nodes=metric(node_rows),
                  cross_agreements=agreement, cross_disagreements=disagreements,
                  primary_by_reviewer={owner: metric([r for r in primary if r["assigned_reviewer"] == owner]) for owner in ("A", "B")})
    result["human_audit_complete"] = bool(primary and node_rows) and all(result[k]["pending"] == 0 for k in ("primary", "cross", "nodes"))
    result["human_findings_clear"] = result["human_audit_complete"] and not disagreements and all(result[k]["incorrect"] == result[k]["unverifiable"] == 0 for k in ("primary", "cross", "nodes"))
    return result
