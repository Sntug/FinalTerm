"""Independent graph cross-checks; suspicious semantics remain human review risks."""
from collections import Counter, defaultdict
from itertools import combinations
import json
import re

from src.collect.contract import contract, validate_records
from src.collect.openalex import comparable, assessment
from src.clean.normalize import doi, arxiv, openalex
from src.clean.text import identifier, canonical_json, evidence_id, validate_nlp_evidence
from src.collect.common import paper_id_from_url

ISSUE_FIELDS = "issue_id owner severity finding_kind category check_id paper_ids entity_ids edge_ids evidence_ids source_record_ids evidence_text reason proposed_action status".split()
NLP_TYPES = {"STUDIES_TASK", "USES_METHOD", "EVALUATED_ON"}


class Findings:
    def __init__(self):
        self.rows = {}

    def add(self, check, owner, reason, *, kind="error", severity="P1", category="other", papers=(), entities=(), edges=(), evidence=(), sources=(), text="", action="Inspect the referenced raw source and correct the owner pipeline; rerun audit."):
        identity = [check, owner, reason, sorted(set(papers)), sorted(set(entities)), sorted(set(edges))]
        iid = identifier("a6-issue", canonical_json(identity))
        self.rows[iid] = dict(issue_id=iid, owner=owner, severity=severity, finding_kind=kind, category=category, check_id=check,
            paper_ids=sorted(set(papers)), entity_ids=sorted(set(entities)), edge_ids=sorted(set(edges)), evidence_ids=sorted(set(evidence)),
            source_record_ids=sorted(set(sources)), evidence_text=text, reason=reason, proposed_action=action, status="awaiting_" + owner if owner in ("A", "B") else "open")
        return iid


def corpus_checks(data, cfg, findings, bodies):
    owner = cfg["owner"]
    papers, registry = data["papers.jsonl"], {r["paper_id"]: r for r in data["paper_registry.csv"]}
    sources = {s["source_record_id"]: s for s in data["source_records.jsonl"]}
    groups, names = defaultdict(list), defaultdict(set)
    if len(papers) != cfg["target"] or len({p["paper_id"] for p in papers}) != cfg["target"]:
        findings.add("paper_count", owner, f"Expected {cfg['target']} unique core papers; observed {len(papers)} rows", category="identity")
    valid = 0
    for p in papers:
        pid = p["paper_id"]
        correct = (p["conference"], p["conference_year"], p["scope"], p["track"]) == (cfg["conference"], cfg["year"], "core", "main")
        try:
            correct = correct and paper_id_from_url(p["cvf_url"]) == pid and registry[pid]["status"] == "cvf_verified"
        except (ValueError, KeyError):
            correct = False
        valid += int(correct)
        if not correct:
            findings.add("paper_scope", owner, "Paper ID, edition, core/main status or registry acceptance differs", papers=[pid], category="time_or_version")
    for a in data["authorships.csv"]:
        groups[a["authorship_id"]].append(a)
        if a["author_id"]:
            names[comparable(a["author_name"])].add(a["author_id"])
        if a["affiliation_status"] == "verified":
            s = sources.get(a["affiliation_source_record_id"])
            if not s or s["paper_id"] != a["paper_id"] or s["source_kind"] not in ("work_detail", "paper_detail"):
                findings.add("affiliation_paper_source", owner, "Verified affiliation has no per-paper Work/conference source", papers=[a["paper_id"]], entities=[a["authorship_id"]], category="affiliation")
        if a["identity_status"] != "resolved" or a["affiliation_status"] == "needs_review":
            if not any(r["paper_id"] == a["paper_id"] and r["entity_id"] in (a["authorship_id"], a["author_id"]) and r["review_status"] == "open" for r in data["needs_review.csv"]):
                findings.add("unlogged_ambiguous_authorship", owner, "Ambiguous identity/affiliation has no open review for the occurrence", papers=[a["paper_id"]], entities=[a["authorship_id"]], category="identity")
    # Independently inspect the exact Work occurrence, not a current author profile.
    papers_by_id = {p["paper_id"]: p for p in papers}
    for rows in groups.values():
        a = rows[0]
        p = papers_by_id.get(a["paper_id"])
        sid = a["identity_source_record_id"]
        if not p or a["identity_status"] != "resolved" or not sid or sid not in bodies:
            continue
        source = sources.get(sid, {})
        if source.get("source") != "OpenAlex":
            continue  # Other verified ID schemes are left to canonical/source validators.
        w = json.loads(bodies[sid])
        wa = w.get("authorships", [])
        index = a["author_order"] - 1
        observed = wa[index] if 0 <= index < len(wa) else None
        ext = openalex(((observed or {}).get("author") or {}).get("id"), "A")
        expected = "author:openalex:" + ext.rsplit("/", 1)[-1] if ext else None
        if not observed or not assessment(p, w)["accepted"] or a["author_id"].startswith("author:openalex:") and a["author_id"] != expected:
            findings.add("author_work_binding", owner, "Resolved Author does not agree with the selected Work/ordered conference byline", papers=[a["paper_id"]], entities=[a["author_id"]], sources=[sid], category="identity")
        for r in rows:
            if r["affiliation_status"] == "verified" and r["institution_id"].startswith("institution:openalex:"):
                per_work = {"institution:openalex:" + i['id'].rsplit('/', 1)[-1] for i in (observed or {}).get("institutions", []) if openalex(i.get('id'), 'I')}
                if r["institution_id"] not in per_work or r["affiliation_source_record_id"] != sid:
                    findings.add("affiliation_occurrence", owner, "Institution is not on this author's occurrence in the selected Paper Work", papers=[a["paper_id"]], entities=[a["author_id"], r["institution_id"]], sources=[sid], category="affiliation")
    return dict(papers=len(papers), valid_core_papers=valid, target=cfg["target"], distinct_authorships=len(groups),
                unresolved_authorships=sum(not rows[0]["author_id"] for rows in groups.values()),
                missing_institution_authorships=sum(not any(r["institution_id"] for r in rows) for rows in groups.values()),
                open_reviews=sum(r["review_status"] == "open" for r in data["needs_review.csv"]),
                homonym_names=sum(len(ids) > 1 for ids in names.values()))


def identity_risks(datasets, graph, findings):
    claims, names = defaultdict(set), defaultdict(set)
    properties, sources_for = defaultdict(set), defaultdict(set)
    papers_for, evidence_for = defaultdict(set), defaultdict(set)
    # Cross-corpus ID claims are inspected before graph's alias quarantine.
    for data in datasets:
        for n in data["nodes.csv"]:
            sources_for[n["id"]].update(n["source_record_ids"])
            for field in ("openalex_id", "orcid", "ror", "country_code"):
                if n["properties_json"].get(field):
                    properties[(n["id"], field)].add(n["properties_json"][field])
        for a in data["alias_map.csv"]:
            if a["entity_type"] in ("Paper", "Author", "Institution"):
                claims[(a["entity_type"], a["source"], a["external_id"])].add(a["canonical_id"])
        for p in data["papers.jsonl"]:
            for source, value in (("DOI", doi(p["doi"])), ("CVF", p["cvf_url"]), ("OpenAlex", p["openalex_id"]), ("arXiv", arxiv(p["arxiv_url"]))):
                if value:
                    claims[("Paper", source, value)].add(p["paper_id"])
        for a in data["authorships.csv"]:
            for key in (a["author_id"], a["institution_id"]):
                if key:
                    papers_for[key].add(a["paper_id"])
    for n in graph["nodes.csv"]:
        if n["label"] in ("Author", "Institution"):
            names[(n["label"], comparable(n["name"]))].add(n["id"])
    for e in graph["edges.csv"]:
        for key in (e["src"], e["dst"]):
            evidence_for[key].update(e["evidence_ids"])
    risks = defaultdict(set)
    for (cid, field), values in sorted(properties.items()):
        if len(values) > 1:
            risks[cid].add("conflicting " + field + " declarations across corpora")
            findings.add("canonical_property_conflict", "A|B", f"Same canonical ID has conflicting {field} declarations: {sorted(values)}",
                kind="review_risk", severity="P2", category="affiliation" if field == "country_code" else "identity",
                entities=[cid], papers=papers_for[cid], sources=sources_for[cid],
                action="Review each paper/year source and campus/version scope; do not silently pick one scalar or merge people/institutions.")
    for (label, source, value), ids in sorted(claims.items()):
        if len(ids) > 1:
            for cid in ids:
                risks[cid].add(f"conflicting {source} alias: {value}")
            findings.add("shared_identifier", "A|B", f"{label} {source} identifier {value} points to multiple locked canonical IDs; do not merge automatically",
                kind="review_risk", severity="P2", category="identity", entities=ids,
                papers=ids if label == "Paper" else set().union(*(papers_for[i] for i in ids)),
                evidence=set().union(*(evidence_for[i] for i in ids)), action="A/B inspect original identifier declarations and record a manual decision if a merge/split is justified.")
    for (label, name), ids in sorted(names.items()):
        if name and len(ids) > 1:
            for cid in ids:
                risks[cid].add("same normalized name, different canonical IDs")
            findings.add("homonym", "A|B", f"{label} nodes share normalized name {name!r}; this can be legitimate homonymy",
                kind="review_risk", severity="P3", category="identity", entities=ids,
                papers=set().union(*(papers_for[i] for i in ids)), action="Compare coauthors, ORCID/ROR and per-paper affiliations; name alone cannot justify merging.")
    for n in graph["nodes.csv"]:
        if n["label"] == "Author" and not n["properties_json"].get("orcid"):
            risks[n["id"]].add("no independent ORCID corroboration; inspect Work/byline evidence")
        if n["label"] == "Institution" and not n["properties_json"].get("ror"):
            risks[n["id"]].add("no ROR corroboration; inspect per-work institution identity")
    return risks


def expected_metadata(data):
    """Independent set-based expectations; never call B's collaboration implementation."""
    papers = {p["paper_id"]: p for p in data["papers.jsonl"]}
    accepted = {r["paper_id"] for r in data["paper_registry.csv"] if r["status"] == "cvf_verified" and papers[r["paper_id"]]["scope"] == "core" and papers[r["paper_id"]]["track"] == "main"}
    expected, authors, affiliations = defaultdict(set), defaultdict(set), defaultdict(set)
    for a in data["authorships.csv"]:
        p = a["paper_id"]
        if p not in accepted or a["identity_status"] != "resolved" or not a["author_id"]:
            continue
        au = a["author_id"]
        expected[(au, "AUTHORED", p)].add(p)
        authors[p].add(au)
        if a["affiliation_status"] == "verified" and a["institution_id"]:
            expected[(au, "AFFILIATED_WITH", a["institution_id"])].add(p)
            affiliations[p].add((au, a["institution_id"]))
    for p in accepted:
        expected[(p, "PUBLISHED_IN", papers[p]["venue_id"])].add(p)
        for a, b in combinations(sorted(authors[p]), 2):
            expected[(a, "COAUTHORED_WITH", b)].add(p)
        for (a, i), (b, j) in combinations(sorted(affiliations[p]), 2):
            if a != b and i != j:
                src, dst = sorted((i, j))
                expected[(src, "COLLABORATED_WITH", dst)].add(p)
    by_work = {papers[p]["openalex_id"]: p for p in accepted if papers[p]["openalex_id"]}
    for p in accepted:
        if papers[p]["references_status"] == "verified":
            for ref in papers[p]["referenced_works"] or []:
                if ref in by_work and by_work[ref] != p:
                    expected[(p, "CITES", by_work[ref])].add(p)
    return expected


def graph_checks(data, manifest, findings):
    nodes = {n["id"]: n for n in data["nodes.csv"]}
    papers = {p["paper_id"]: p for p in data["papers.jsonl"]}
    evidence = {e["evidence_id"]: e for e in data["evidence.jsonl"]}
    texts = {t["text_version_id"]: t for t in data["text_versions.jsonl"]}
    sources = {s["source_record_id"]: s for s in data["source_records.jsonl"]}
    relations = {r["type"]: r for r in contract()["relations"]}
    expected = expected_metadata(data)
    actual = set()
    for table in ("nodes.csv", "edges.csv", "evidence.jsonl"):
        try:
            validate_records(table, data[table])
        except ValueError as exc:
            findings.add("schema_or_duplicate", "B", str(exc), category="other")
    keys, nlp_evidence = set(), set()
    for e in data["edges.csv"]:
        key = (e["src"], e["type"], e["dst"])
        typ, ids, pids = e["type"], [e["edge_id"]], e["paper_ids"]
        owner = "A" if typ in ("STUDIES_TASK", "EVALUATED_ON") else "B"
        def error(check, reason, category="other"):
            findings.add(check, owner, reason, papers=pids, edges=ids, evidence=e["evidence_ids"], category=category)
        if key in keys:
            error("duplicate_edge", "Repeated normalized (src,type,dst) key")
        keys.add(key)
        if e["src"] not in nodes or e["dst"] not in nodes:
            error("missing_endpoint", "Edge endpoint does not exist", "identity")
            continue
        spec = relations.get(typ)
        if not spec or (nodes[e["src"]]["label"], nodes[e["dst"]]["label"]) != (spec["src_label"], spec["dst_label"]):
            error("edge_direction_or_labels", "Unexpected relation type, endpoint labels or direction")
        if e["src"] == e["dst"] or spec and not spec["directed"] and not e["src"] < e["dst"]:
            error("self_loop_or_order", "Self-loop or non-canonical undirected order")
        if e["edge_id"] != identifier("edge", *key) or e["validation_status"] != "accepted" or e["project_id"] != manifest["project_id"]:
            error("edge_identity", "Edge ID, project or acceptance status differs")
        if not e["evidence_ids"] or any(i not in evidence for i in e["evidence_ids"]):
            error("missing_evidence", "Missing evidence reference", "missing_evidence")
        if any(p not in papers for p in pids):
            error("edge_paper_ids", "Supporting Paper does not exist", "identity")
        if typ in NLP_TYPES:
            if e["derivation"] != "nlp" or e["weight"] != 1 or pids != [e["src"]]:
                error("nlp_properties", "NLP edge must be Paper -> entity, weight 1, derivation nlp and own Paper support", "nlp_relation")
            for eid in e["evidence_ids"]:
                if eid not in evidence:
                    continue
                ev = evidence[eid]
                nlp_evidence.add(eid)
                try:
                    validate_nlp_evidence(ev, texts[ev["text_version_id"]])
                    p = papers[e["src"]]
                    prefix = {"STUDIES_TASK":"a4-task-", "EVALUATED_ON":"a4-dataset-", "USES_METHOD":"b5-method-"}[typ]
                    if ev["evidence_id"] != evidence_id(ev) or ev["paper_id"] != e["src"] or ev["text_version_id"] not in (p["title_text_version_id"], p["abstract_text_version_id"]) or not ev["rule_id"].startswith(prefix) or not ev["rule_version"] or ev["source_url"] != sources[ev["source_record_id"]]["url"]:
                        raise ValueError("NLP evidence identity, rule, selected field or source differs")
                    if manifest.get("rule_versions", {}).get(ev["rule_id"]) != ev["rule_version"]:
                        raise ValueError("NLP evidence rule version differs from the audited manifest")
                except (KeyError, ValueError, TypeError) as exc:
                    error("nlp_binding_or_offset", str(exc), "time_or_version")
                text = ev.get("evidence_text") or ""
                context_risk = re.search(r"\b(baseline|related work|previous|not|never|unlike|compared|rather than|instead of)\b", text, re.I)
                training_role_risk = typ == "EVALUATED_ON" and re.search(r"\bpre[- ]?train\w*\b", text, re.I)
                if context_risk or training_role_risk:
                    findings.add("nlp_context_risk", owner, "Sentence contains a negation, comparison, attribution or training cue; inspect the specific entity role, not just the keyword",
                        kind="review_risk", severity="P2", category="nlp_relation", papers=pids, edges=ids, evidence=[eid], sources=[ev["source_record_id"]], text=text,
                        action="Reproduce with this sentence, the destination entity and section; owner reviews clause scope and adds a regression case if wrong. No automatic human verdict.")
        elif typ in ("COAUTHORED_WITH", "COLLABORATED_WITH"):
            if e["derivation"] != "derived" or e["weight"] != len(set(pids)):
                error("derived_weight", "Weight must count distinct supporting core papers", "affiliation")
        elif e["derivation"] != "metadata" or e["weight"] != 1:
            error("metadata_properties", "Metadata edge must have derivation metadata and weight 1")
        if typ in {"AUTHORED", "AFFILIATED_WITH", "PUBLISHED_IN", "CITES", "COAUTHORED_WITH", "COLLABORATED_WITH"}:
            actual.add(key)
            support = expected.get(key, set())
            if not support or set(pids) != support or e["weight"] != (len(support) if typ in ("COAUTHORED_WITH", "COLLABORATED_WITH") else 1):
                error("independent_relation_support", f"Expected supporting core Paper IDs {sorted(support)}, got {pids}; counts rebuilt from authorships/references", "citation" if typ == "CITES" else "affiliation")
            if typ == "CITES" and not any(evidence.get(i, {}).get("field_path") == "json:referenced_works" for i in e["evidence_ids"]):
                findings.add("citation_evidence_specificity", "B", "Reference list supports this CITES pair, but attached evidence field paths do not explicitly identify referenced_works" if support else "No reference-list support and no specific citation evidence",
                    kind="review_risk" if support else "error", severity="P2" if support else "P1", category="missing_evidence", papers=pids, edges=ids, evidence=e["evidence_ids"],
                    action="B should attach precise metadata evidence at json:referenced_works (or the confirmed bibliography field). Inspect the Work raw source; do not infer CITES from cited_by_count.")
        if typ == "BASED_IN":
            iid = nodes[e["src"]]["properties_json"].get("openalex_id")
            country = nodes[e["dst"]]["properties_json"].get("country_code")
            matching = []
            for eid in e["evidence_ids"]:
                ev = evidence.get(eid, {})
                try:
                    obj = json.loads(ev.get("evidence_text") or "null")
                    if isinstance(obj, dict) and obj.get("id") == iid and obj.get("country_code") == country and ".institutions[" in (ev.get("field_path") or ""):
                        matching.append(eid)
                except (ValueError, TypeError):
                    pass
            if not matching:
                error("country_evidence", "No same-institution and same-country per-work evidence", "affiliation")
    for key in sorted(set(expected) - actual):
        findings.add("missing_expected_relation", "B", "Missing metadata/derived relation supported by accepted core data", papers=expected[key], entities=[key[0], key[2]])
    for node in nodes.values():
        cc = node["properties_json"].get("country_code")
        if node["label"] == "Institution" and cc and (node["id"], "BASED_IN", "country:" + cc) not in keys:
            findings.add("missing_country_relation", "B", "Institution has confirmed country metadata but no BASED_IN edge", entities=[node["id"], "country:" + cc], category="affiliation")
    if (len(nodes), len(data["edges.csv"])) != (manifest["node_count"], manifest["edge_count"]):
        findings.add("graph_counts", "B", "Graph CSV counts differ from manifest")
    for typ in sorted(set(relations) - {e["type"] for e in data["edges.csv"]}):
        findings.add("missing_relation_type", "A" if typ in ("STUDIES_TASK", "EVALUATED_ON") else "B", "No edges for required type " + typ, kind="review_risk", severity="P2")
    return dict(nodes=len(nodes), edges=len(data["edges.csv"]), counts_by_label=dict(Counter(n["label"] for n in nodes.values())),
                counts_by_type=dict(Counter(e["type"] for e in data["edges.csv"])), nlp_edges=sum(e["type"] in NLP_TYPES for e in data["edges.csv"]), nlp_evidence_checked=len(nlp_evidence))
