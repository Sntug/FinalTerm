"""Paper-scoped cross-checks; observations never merge canonical identities."""
from collections import defaultdict, Counter
from copy import deepcopy
import json
import re
from urllib.parse import quote, urlsplit

from src.clean.normalize import doi, arxiv, openalex, orcid, ror, clean_text
from src.clean.resolution import identity_conflicts, paper_candidates
from src.clean.text import canonical_json, identifier, evidence_id
from src.collect.openalex import assessment, comparable
from src.collect.cvf import parse_detail
from src.collect.common import paper_id_from_url
from src.collect.contract import contract
from .sources import arxiv_metadata

RULE, VERSION = "a5-source-crosscheck", "1.0.0"
COMPARISON_FIELDS = "comparison_id paper_id entity_type entity_id field_name current_value_json observed_value_json source_record_ids evidence_ids result reason".split()


def selected_work(paper, records, bodies):
    prov = next((p for p in records["field_provenance.csv"] if p["paper_id"] == paper["paper_id"] and p["field_name"] == "openalex_id"), None)
    if paper["openalex_status"] == "matched" and prov:
        sid = prov["source_record_id"]
        value = json.loads(bodies[sid])
        if value.get("id") == paper["openalex_id"] and assessment(paper, value)["accepted"]:
            return value, sid
    return None, None


def lookup_plan(records, bodies, cfg):
    plan, proposals = [], {}
    sources = records["source_records.jsonl"]
    papers = sorted(records["papers.jsonl"], key=lambda p: p["paper_id"])
    # Only unresolved Work/DOI cases; never re-fetch all 328 already matched Works.
    for p in papers:
        if not p["openalex_id"] or not p["doi"]:
            aid = arxiv(p["arxiv_url"])
            if aid and sum(x["source"] == "arXiv" for x in plan) < cfg["max_arxiv_papers"]:
                version = re.search(r"(v\d+)(?:\.pdf)?$", urlsplit(p["arxiv_url"]).path)
                plan.append(dict(paper_id=p["paper_id"], source="arXiv", url="https://arxiv.org/abs/" + aid + (version[1] if version else "")))
            for source in sources:
                if source["paper_id"] != p["paper_id"] or source["source"] != "OpenAlex" or source["source_kind"] != "work_search":
                    continue
                for w in json.loads(bodies[source["source_record_id"]]).get("results", []):
                    value = doi(w.get("doi"))
                    if value and comparable(w.get("display_name")) == comparable(p["title"]):
                        proposals.setdefault(p["paper_id"], set()).add(value)
    for p in papers:
        candidates = proposals.get(p["paper_id"], set())
        if not p["doi"] and len(candidates) == 1 and sum(x["source"] == "Crossref" for x in plan) < cfg["max_crossref_papers"]:
            plan.append(dict(paper_id=p["paper_id"], source="Crossref", url="https://api.crossref.org/works/" + quote(next(iter(candidates)), safe="")))
    return plan


class Audit:
    def __init__(self, original, snapshot, decided_at):
        self.data = deepcopy(original)
        self.snapshot, self.decided_at = snapshot, decided_at
        self.sources = {s["source_record_id"]: s for s in self.data["source_records.jsonl"]}
        self.evidence = {e["evidence_id"]: e for e in self.data["evidence.jsonl"]}
        self.reviews = {r["review_id"]: r for r in self.data["needs_review.csv"]}
        self.comparisons = {}
        self.updated_papers = set()
        self.nodes = {n["id"]: n for n in self.data["nodes.csv"]}

    def ev(self, paper, sid, path, value):
        source = self.sources[sid]
        e = dict.fromkeys(contract()["files"]["evidence.jsonl"]["fields"])
        e.update(evidence_kind="metadata", paper_id=paper["paper_id"], source_record_id=sid, source_url=source["url"],
                 field_path=path, evidence_text=canonical_json(value), rule_id=RULE, rule_version=VERSION,
                 captured_at=source["fetched_at"], supporting_evidence_ids=[], owner=paper["owner"])
        e["evidence_id"] = evidence_id(e)
        self.evidence[e["evidence_id"]] = e
        return e["evidence_id"]

    def compare(self, paper, entity, entity_id, field, current, observed, evidence, result, reason, review=False):
        sources = sorted({self.evidence[e]["source_record_id"] for e in evidence})
        cid = identifier("comparison", RULE, paper["paper_id"], entity, entity_id or "", field,
                         canonical_json(current), canonical_json(observed), canonical_json(sources), result, reason)
        row = dict(comparison_id=cid, paper_id=paper["paper_id"], entity_type=entity, entity_id=entity_id,
            field_name=field, current_value_json=canonical_json(current), observed_value_json=canonical_json(observed),
            source_record_ids=sources, evidence_ids=sorted(set(evidence)), result=result, reason=reason)
        self.comparisons[cid] = row
        if review:
            rid = identifier("review", RULE, cid)
            self.reviews[rid] = dict(review_id=rid, paper_id=paper["paper_id"], entity_type=entity, entity_id=entity_id,
                field_name=field, reason=f"{result}: {reason}; comparison_id={cid}; inspect original source before resolving",
                candidate_ids=sorted({str(v) for v in (observed if isinstance(observed, list) else [observed]) if isinstance(v, str)}),
                evidence_ids=row["evidence_ids"], review_status="open", assigned_to=paper["owner"], resolution_decision_id=None)
        return cid

    def update_doi(self, paper, value, sid, path, support):
        if paper["doi"] is not None:
            raise ValueError("DOI utility only fills a missing conference DOI")
        key = identifier("alias", "Paper", "DOI", value)
        if any(a["alias_id"] == key and a["canonical_id"] != paper["paper_id"] for a in self.data["alias_map.csv"]):
            return False
        did = identifier("decision", RULE, self.snapshot, paper["paper_id"], "doi", value, canonical_json(sorted(support)))
        registry = next(r for r in self.data["paper_registry.csv"] if r["paper_id"] == paper["paper_id"])
        provenance = next((p for p in self.data["field_provenance.csv"] if p["paper_id"] == paper["paper_id"] and p["field_name"] == "doi"), None)
        selected = dict(paper_id=paper["paper_id"], field_name="doi", source_record_id=sid, field_path=path,
                        selection_rule=RULE, validation_status="verified", reviewed_by=RULE + "-" + VERSION,
                        selected_at=self.sources[sid]["fetched_at"], candidate_source_record_ids=[sid])
        alias = dict(alias_id=key, entity_type="Paper", source="DOI", external_id=value, canonical_id=paper["paper_id"], decision_id=did)
        old_alias = next((a for a in self.data["alias_map.csv"] if a["alias_id"] == key), None)
        changes = [dict(table="papers.jsonl", record_key={"paper_id": paper["paper_id"]}, field="doi", before=None, after=value),
                   dict(table="paper_registry.csv", record_key={"paper_id": paper["paper_id"]}, field="doi", before=registry["doi"], after=value),
                   dict(table="field_provenance.csv", record_key={"paper_id": paper["paper_id"], "field_name": "doi"}, field="$row", before=deepcopy(provenance), after=selected),
                   dict(table="alias_map.csv", record_key={"alias_id": key}, field="$row", before=deepcopy(old_alias), after=alias)]
        paper["doi"] = registry["doi"] = value
        if provenance:
            provenance.update(selected)
        else:
            self.data["field_provenance.csv"].append(selected)
        if old_alias:
            old_alias.update(alias)
        else:
            self.data["alias_map.csv"].append(alias)
        self.data["merge_log.jsonl"].append(dict(decision_id=did, action="link", entity_type="Paper", input_ids=[value], output_ids=[paper["paper_id"]],
            affected_paper_ids=[paper["paper_id"]], affected_authorship_ids=[], changes=changes,
            reason="Exact title and complete ordered conference byline plus conference/year and DOI registry evidence; Paper ID preserved.",
            evidence_ids=sorted(support), proposed_by=paper["owner"], reviewed_by=RULE + "-" + VERSION, review_mode="rule",
            decided_at=self.decided_at, snapshot_before=self.snapshot, reverts_decision_id=None))
        self.updated_papers.add(paper["paper_id"])
        return True


def crosscheck(original, bodies, snapshot, decided_at, lookups):
    audit = Audit(original, snapshot, decided_at)
    papers = {p["paper_id"]: p for p in audit.data["papers.jsonl"]}
    work_info = {pid: selected_work(p, original, bodies) for pid, p in papers.items()}
    works = {pid: w for pid, (w, sid) in work_info.items() if w}
    bad_authors, bad_institutions = identity_conflicts(works)
    groups = defaultdict(list)
    for a in original["authorships.csv"]:
        groups[a["authorship_id"]].append(a)
    _, paper_conflicts, pairs = paper_candidates(list(papers.values()))
    for pid in sorted(papers):
        p = papers[pid]
        sid = p["representative_source_record_id"]
        raw = parse_detail(bodies[sid], p["cvf_url"], p["conference"], p["conference_year"])
        cvf_ev = audit.ev(p, sid, "html:meta[name=citation_title]@content", raw["title"])
        for field, current, observed, path in (
            ("cvf_id", pid, paper_id_from_url(p["cvf_url"]), "html:meta[name=citation_title]@content"),
            ("title", p["title"], clean_text(raw["title"]), "html:meta[name=citation_title]@content"),
            ("ordered_authors", [a["name"] for a in p["authors"]], [clean_text(a["name"]) for a in raw["authors"]], "html:meta[name=citation_author]@content[]")):
            e = audit.ev(p, sid, path, observed)
            matched = current == observed
            audit.compare(p, "Paper", pid, field, current, observed, [e], "matched" if matched else "conflict", "CVF conference representative", not matched)
        w, wsid = work_info[pid]
        if w:
            for field, current, observed, path in (
                ("openalex_id", p["openalex_id"], w["id"], "json:id"),
                ("doi", doi(p["doi"]), doi(w.get("doi")), "json:doi"),
                ("title", comparable(p["title"]), comparable(w.get("display_name")), "json:display_name"),
                ("ordered_authors", [comparable(a["name"]) for a in p["authors"]], [comparable(a.get("raw_author_name") or (a.get("author") or {}).get("display_name")) for a in w.get("authorships", [])], "json:authorships")):
                e = audit.ev(p, wsid, path, w.get(path[5:]))
                result = "missing" if observed is None else "matched" if current == observed else "conflict"
                audit.compare(p, "Paper", pid, field, current, observed, [cvf_ev, e], result, "Selected OpenAlex Work corroborated by A2 assessment", result == "conflict")
        else:
            evs, candidates = [cvf_ev], []
            for source in original["source_records.jsonl"]:
                if source["paper_id"] == pid and source["source"] == "OpenAlex" and source["source_kind"] == "work_search":
                    results = json.loads(bodies[source["source_record_id"]]).get("results", [])
                    candidates.extend(r.get("id") for r in results if r.get("id"))
                    evs.append(audit.ev(p, source["source_record_id"], "json:results", results))
            audit.compare(p, "Paper", pid, "openalex_id", p["openalex_id"], sorted(set(candidates)), evs, "unresolved", "Search candidates are not verified Work links; inspect title, complete byline, venue/version and search truncation", True)
        # A syntax-valid arXiv link from CVF is not a verification of its contents.
        aid = arxiv(p["arxiv_url"])
        if p["arxiv_url"]:
            e = audit.ev(p, sid, 'html:a[href*="arxiv.org/abs/"]@href', raw["arxiv_url"])
            current_version = re.search(r"v\d+(?:\.pdf)?$", urlsplit(p["arxiv_url"]).path)
            source_version = re.search(r"v\d+(?:\.pdf)?$", urlsplit(raw["arxiv_url"] or "").path)
            versions_equal = (current_version[0].removesuffix(".pdf") if current_version else None) == (source_version[0].removesuffix(".pdf") if source_version else None)
            linked = bool(aid and arxiv(raw["arxiv_url"]) == aid and versions_equal)
            audit.compare(p, "Paper", pid, "arxiv_link", p["arxiv_url"], raw["arxiv_url"], [e], "matched" if linked else "conflict", "CVF outbound link only; preprint content assessed separately", not linked)
        if aid and not any(x["paper_id"] == pid and x["source"] == "arXiv" for x in lookups):
            audit.compare(p, "Paper", pid, "arxiv_metadata", aid, None, [cvf_ev], "unverified", "Not selected for supplemental lookup; CVF link does not verify preprint metadata")
        for a in p["authors"]:
            rows = groups[a["authorship_id"]]
            row = rows[0]
            index = a["author_order"] - 1
            raw_name = raw["authors"][index]["name_raw"] if index < len(raw["authors"]) else [r["name_raw"] for r in raw["authors"]]
            occurrence_ev = audit.ev(p, sid, "html:meta[name=citation_author]@content[]", raw_name)
            observed, evs = None, [occurrence_ev]
            if w:
                index = a["author_order"] - 1
                observed = w["authorships"][index]
                evs.append(audit.ev(p, wsid, f"json:authorships[{index}]", observed))
            au = (observed or {}).get("author") or {}
            oid = openalex(au.get("id"), "A")
            target = "author:openalex:" + oid.rsplit("/", 1)[-1] if oid else None
            if row["author_id"] and target == row["author_id"] and oid not in bad_authors:
                result = "matched"
            elif row["author_id"] and target and row["author_id"] != target:
                result = "conflict"
            else:
                result = "unresolved"
            audit.compare(p, "Author", row["author_id"] or a["authorship_id"], "author_id", row["author_id"], target, evs, result,
                          "Ordered per-work author observation; unresolved/profile-name/ORCID conflicts require corroboration, never name-only merge", result != "matched")
            raw_oid = au.get("orcid") or (observed or {}).get("raw_orcid")
            canonical_orcid = orcid(raw_oid)
            current_orcid = audit.nodes.get(row["author_id"], {}).get("properties_json", {}).get("orcid")
            orcid_conflict = bool(raw_oid and not canonical_orcid or current_orcid and canonical_orcid and current_orcid != canonical_orcid)
            audit.compare(p, "Author", row["author_id"] or a["authorship_id"], "orcid", current_orcid, canonical_orcid or raw_oid, evs,
                          "conflict" if orcid_conflict else "matched" if canonical_orcid and current_orcid == canonical_orcid else "unverified" if canonical_orcid else "missing",
                          "Selected Work/current alias consistency; syntax/checksum alone is not ownership verification; no ORCID alias added", orcid_conflict)
            actual = sorted({r["institution_id"] for r in rows if r["institution_id"]})
            insts = (observed or {}).get("institutions") or []
            proposed = sorted({"institution:openalex:" + value.rsplit("/", 1)[-1] for inst in insts if (value := openalex(inst.get("id"), "I"))})
            incomplete = any(not r["institution_id"] and r["affiliation_status"] == "needs_review" for r in rows)
            result = "matched" if actual and actual == proposed and not incomplete else "conflict" if actual and proposed and set(actual) - set(proposed) else "unresolved" if insts or any(r["affiliation_raw"] for r in rows) else "missing"
            audit.compare(p, "Author", a["authorship_id"], "paper_affiliations", actual, proposed, evs, result,
                          "Affiliations from this Work only; preserve multiple institutions and unresolved raw strings; no profile/current employer lookup", result in ("conflict", "unresolved"))
            for index, inst in enumerate(insts):
                value = openalex(inst.get("id"), "I")
                cid = "institution:openalex:" + value.rsplit("/", 1)[-1] if value else None
                rid = ror(inst.get("ror"))
                current_ror = audit.nodes.get(cid, {}).get("properties_json", {}).get("ror")
                e = audit.ev(p, wsid, f'json:authorships[{a["author_order"] - 1}].institutions[{index}]', inst)
                status = "conflict" if value in bad_institutions or inst.get("ror") and not rid or current_ror and rid and current_ror != rid else "matched" if cid in actual else "unresolved"
                audit.compare(p, "Institution", cid or a["authorship_id"], "institution_identity", cid,
                              {"id": value, "ror": rid, "name": inst.get("display_name"), "country_code": inst.get("country_code")}, [e], status,
                              "Per-work institution identifiers; aliases do not merge parent/subsidiary institutions", status != "matched")
    for pids, issue, reason in pairs:
        for pid in pids:
            p = papers[pid]
            e = audit.ev(p, p["representative_source_record_id"], "html:meta[name=citation_title]@content", p["title"])
            audit.compare(p, "Paper", pid, issue, pid, pids, [e], "conflict" if issue == "identifier_collision" else "unresolved", reason + "; locked CVF Paper IDs require human merge/split decision", True)
    # Homonyms and spelling/ID differences are review candidates, never identity decisions.
    names = defaultdict(list)
    for aid, rows in groups.items():
        if rows[0]["author_id"]:
            names[comparable(rows[0]["author_name"])].append(rows[0])
    for rows in names.values():
        ids = sorted({r["author_id"] for r in rows})
        if len(ids) > 1:
            for row in rows:
                p = papers[row["paper_id"]]
                e = audit.ev(p, row["source_record_id"], "html:meta[name=citation_author]@content[]", row["author_name_raw"])
                audit.compare(p, "Author", row["author_id"], "homonym_distinct_ids", row["author_id"], ids, [e], "unresolved", "Same normalized display name, different IDs; compare coauthors and paper-scoped affiliations manually; do not merge", True)
    supplemental(audit, papers, lookups, bodies)
    audit.data["evidence.jsonl"] = list(audit.evidence.values())
    audit.data["needs_review.csv"] = list(audit.reviews.values())
    return audit


def supplemental(audit, papers, lookups, bodies):
    for item in lookups:
        p = papers[item["paper_id"]]
        field = "arxiv_metadata" if item["source"] == "arXiv" else "doi_registry"
        if item["status"] != "fetched":
            e = audit.ev(p, p["representative_source_record_id"], "html:meta[name=citation_title]@content", p["title"])
            audit.compare(p, "Paper", p["paper_id"], field, p["arxiv_url"] if item["source"] == "arXiv" else p["doi"], None,
                          [e], item["status"], f'{item["source"]}: {item["reason"]}; no successful source record fabricated', True)
            continue
        source = item["source_record"]
        sid = source["source_record_id"]
        if sid not in audit.sources:
            audit.sources[sid] = source
            audit.data["source_records.jsonl"].append(source)
        body = bodies[sid]
        if item["source"] == "arXiv":
            observed = arxiv_metadata(body)
            match = observed["arxiv_id"] == arxiv(p["arxiv_url"])
            title_ok = comparable(observed["title"]) == comparable(p["title"])
            byline = [comparable(a) for a in observed["authors"]] == [comparable(a["name"]) for a in p["authors"]]
            pinned = re.search(r"v(\d+)(?:\.pdf)?$", urlsplit(p["arxiv_url"] or "").path)
            revision_status = None
            if pinned:
                revision_status = "unverified" if not observed["version"] else None if observed["version"].endswith("v" + pinned[1]) else "conflict"
            result = revision_status or ("matched" if match and title_ok and byline else "version_difference" if match else "conflict")
            # A direct CVF link pins a preprint; changed byline/title remains visible as a version difference.
            e = audit.ev(p, sid, "html:meta[name=citation_arxiv_id]@content", observed["declared_identifier"])
            audit.compare(p, "Paper", p["paper_id"], "arxiv_metadata", {"title": p["title"], "authors": [a["name"] for a in p["authors"]]}, observed,
                          [e, audit.ev(p, sid, "html:meta[name=citation_title]@content", observed["title"]), audit.ev(p, sid, "html:meta[name=citation_author]@content[]", observed["authors_raw"])],
                          result,
                          "Conference title/byline stay authoritative; preprint date/version never replaces conference metadata", result != "matched")
        else:
            value = json.loads(body)["message"]
            observed_doi = doi(value.get("DOI"))
            title_ok = comparable((value.get("title") or [""])[0]) == comparable(p["title"])
            authors = [clean_text((a.get("given", "") + " " + a.get("family", "")).strip()) for a in value.get("author", [])]
            byline = [comparable(a) for a in authors] == [comparable(a["name"]) for a in p["authors"]]
            container = " ".join(value.get("container-title") or []) + " " + (value.get("event") or {}).get("name", "")
            venue_ok = (p["conference"].casefold() in container.casefold() or ("computer vision and pattern recognition" if p["conference"] == "CVPR" else "international conference on computer vision") in container.casefold()) and "workshop" not in container.casefold()
            parts = (value.get("published") or value.get("issued") or {}).get("date-parts") or [[]]
            conference_ok = value.get("type") == "proceedings-article" and parts[0] and parts[0][0] == p["conference_year"] and venue_ok
            requested_doi = doi(item["url"].split("/works/", 1)[1])
            trusted = bool(observed_doi and observed_doi == requested_doi and title_ok and byline and conference_ok)
            e = audit.ev(p, sid, "json:message", value)
            audit.compare(p, "Paper", p["paper_id"], "ordered_authors", [a["name"] for a in p["authors"]], authors, [e],
                          "matched" if byline else "conflict", "Crossref byline vs representative CVF; do not transfer per-author identifiers/affiliations across a mismatch", not byline)
            raw_affiliations = [{"name": name, "affiliations": a.get("affiliation", [])} for name, a in zip(authors, value.get("author", []))]
            audit.compare(p, "Paper", p["paper_id"], "crossref_affiliations", None, raw_affiliations, [e], "unverified",
                          "Publisher per-paper affiliation observations retained for manual resolution; no Institution ID inferred from organization names")
            result = "conflict" if p["doi"] and observed_doi != doi(p["doi"]) else "matched" if trusted and p["doi"] else "unresolved"
            if trusted and not p["doi"] and not any(q["doi"] == observed_doi and q["paper_id"] != p["paper_id"] for q in papers.values()):
                support = [e, audit.ev(p, p["representative_source_record_id"], "html:meta[name=citation_author]@content[]", [a["name_raw"] for a in p["authors"]])]
                if audit.update_doi(p, observed_doi, sid, "json:message.DOI", support):
                    result = "updated"
            checks = dict(doi=observed_doi, requested_doi_equal=observed_doi == requested_doi, title_equal=title_ok,
                          ordered_authors_equal=byline, conference_type_venue_year_valid=bool(conference_ok))
            audit.compare(p, "Paper", p["paper_id"], "doi_registry", None if result == "updated" else p["doi"], checks, [e], result,
                          "DOI registry must match requested DOI, exact title, full ordered byline, proceedings venue and year; preprint DOI cannot fill conference DOI", result in ("conflict", "unresolved"))
