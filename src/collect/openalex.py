"""Conservative Work matching, independent of Author identity resolution."""
import re
import unicodedata
from urllib.parse import urlencode, urlsplit

from .cache import openalex_source
from .contract import contract
from src.clean.text import evidence_id, identifier, normalize, text_record

RULE_VERSION = "1.1.0"
CVPR_2026_RULE_VERSION = "1.2.0"


def rule_version(edition):
    if (edition["conference"], edition["conference_year"]) == ("CVPR", 2026):
        return CVPR_2026_RULE_VERSION
    return RULE_VERSION


def comparable(value):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value or "").casefold())


def matches_cvf_name(cvf_author, observed_name):
    """Accept the CVF display name or the same explicit surname/given-name pair."""
    if not comparable(observed_name):
        return False
    raw = (cvf_author.get("name_raw") or "").split(",")
    observed = observed_name.split(",")
    if len(raw) == len(observed) == 2:
        return all(comparable(part) for part in raw) and list(map(comparable, raw)) == list(map(comparable, observed))
    return comparable(cvf_author["name"]) == comparable(observed_name)


def ordered_byline_matches(paper, openalex_authorships):
    authors = paper["authors"]
    names = [a.get("raw_author_name") or (a.get("author") or {}).get("display_name") for a in openalex_authorships]
    if not authors or len(names) != len(authors):
        return False
    if rule_version(paper) == CVPR_2026_RULE_VERSION:
        return all(matches_cvf_name(a, name) for a, name in zip(authors, names))
    return [comparable(a["name"]) for a in authors] == [comparable(name) for name in names]


def arxiv_identifier(url):
    """Return the base arXiv ID and optional explicit version on an official URL."""
    try:
        parts = urlsplit(url or "")
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.query or parts.fragment:
        return None
    host = parts.netloc.lower()
    path = parts.path
    if host in ("arxiv.org", "www.arxiv.org") and path.startswith(("/abs/", "/pdf/")):
        identifier = path[5:]
        if path.startswith("/pdf/"):
            identifier = identifier.removesuffix(".pdf")
    elif host in ("doi.org", "dx.doi.org") and path.lower().startswith("/10.48550/arxiv."):
        identifier = path[len("/10.48550/arxiv."):]
    else:
        return None
    match = re.fullmatch(r"(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(v[1-9]\d*)?", identifier)
    return match.groups() if match else None


def arxiv_linked(cvf_url, work_urls):
    target = arxiv_identifier(cvf_url)
    if not target:
        return False
    same_id = [other for url in work_urls if (other := arxiv_identifier(url)) and other[0] == target[0]]
    return bool(same_id) and all(not target[1] or not version or version == target[1] for _, version in same_id)


def assessment(paper, work):
    title = comparable(paper["title"]) == comparable(work.get("display_name"))
    authors = ordered_byline_matches(paper, work.get("authorships", []))
    locations = work.get("locations") or []
    links = {x.get(k) for x in locations for k in ("landing_page_url", "pdf_url") if x.get(k)}
    linked = bool(links & {paper["cvf_url"], paper.get("pdf_url"), paper.get("arxiv_url")})
    if rule_version(paper) == CVPR_2026_RULE_VERSION:
        linked = bool(links & {paper["cvf_url"], paper.get("pdf_url")}) or arxiv_linked(
            paper.get("arxiv_url"), links | {work.get("doi")})
    venue_names = [((x.get("source") or {}).get("display_name") or "").casefold() for x in locations]
    venue = any((paper["conference"].lower() in name or
                 ("conference on computer vision and pattern recognition" if paper["conference"] == "CVPR" else "international conference on computer vision") in name)
                and "workshop" not in name for name in venue_names)
    year = work.get("publication_year") == paper["conference_year"]
    doi = bool(paper.get("doi")) and paper["doi"].lower() == (work.get("doi") or "").removeprefix("https://doi.org/").lower()
    # Even a DOI/URL requires corroboration; matching bylines do not resolve people.
    accepted = title and authors and (doi or (venue and year) or (linked and abs((work.get("publication_year") or 0) - paper["conference_year"]) <= 1))
    return {"work_id": work.get("id"), "title_equal": title, "ordered_authors_equal": authors,
            "venue_match": venue, "year_equal": year, "version_link": linked, "doi_equal": doi, "accepted": accepted}


def collect_work(cache, paper):
    params = {"per_page": 10}
    if paper.get("doi"):
        params["filter"] = "doi:" + paper["doi"]
    else:
        params["search.title"] = '"' + paper["title"].replace('"', ' ') + '"'
    value, meta = cache.get("https://api.openalex.org/works?" + urlencode(params))
    sources = [openalex_source(meta, paper["paper_id"], "work_search")]
    if not value["results"] and not paper.get("doi"):
        # Broader search is only a fallback to retain review candidates.
        value, meta = cache.get("https://api.openalex.org/works?" + urlencode({"per_page": 10, "search": paper["title"]}))
        sources.append(openalex_source(meta, paper["paper_id"], "work_search"))
    candidates = value["results"]
    checks = [assessment(paper, work) for work in candidates]
    accepted = [c for c in checks if c["accepted"]]
    status = "not_found" if not candidates else "needs_review"
    work = None
    truncated = value.get("meta", {}).get("count", len(candidates)) > len(candidates)
    if len(accepted) == 1 and not truncated:
        wid = accepted[0]["work_id"]
        if not re.fullmatch(r"https://openalex.org/W\d+", wid or ""):
            raise ValueError("Malformed Work ID")
        work, detail = cache.get("https://api.openalex.org/works/" + wid.rsplit("/", 1)[-1])
        sources.append(openalex_source(detail, paper["paper_id"], "work_detail"))
        if work.get("id") == wid and assessment(paper, work)["accepted"]:
            status = "matched"
        else:
            work = None
    audit = {"paper_id": paper["paper_id"], "status": status, "rule_version": rule_version(paper),
             "candidate_checks": checks, "search_truncated": truncated,
             "source_record_ids": [s["source_record_id"] for s in sources],
             "work_id": work["id"] if work else None}
    return work, sources, audit


def enrich(records, paper, work, sources, audit):
    version = rule_version(paper)
    paper["openalex_status"] = audit["status"]
    if work is None:
        if audit["status"] == "needs_review":
            source = sources[-1]
            evidence = {k: None for k in contract()["files"]["evidence.jsonl"]["fields"]}
            evidence.update(evidence_kind="metadata", paper_id=paper["paper_id"], source_record_id=source["source_record_id"],
                            source_url=source["url"], field_path="json:results", rule_id="openalex-work-match", rule_version=version,
                            captured_at=source["fetched_at"], supporting_evidence_ids=[], owner=paper["owner"])
            evidence["evidence_id"] = evidence_id(evidence)
            records["evidence.jsonl"].append(evidence)
            records["needs_review.csv"].append({"review_id": identifier("review", paper["paper_id"], "openalex-work-match"),
                "paper_id": paper["paper_id"], "entity_type": "Paper", "entity_id": paper["paper_id"], "field_name": "openalex_id",
                "reason": "No unique Work meeting title, byline and venue/year or identifier/version-link rule; inspect matching.json",
                "candidate_ids": [c["work_id"] for c in audit["candidate_checks"] if c["work_id"]],
                "evidence_ids": [evidence["evidence_id"]], "review_status": "open", "assigned_to": paper["owner"], "resolution_decision_id": None})
        return
    source = sources[-1]
    sid = source["source_record_id"]
    def provenance(field, source_field):
        records["field_provenance.csv"].append({"paper_id": paper["paper_id"], "field_name": field,
            "source_record_id": sid, "field_path": "json:" + source_field, "selection_rule": "openalex-work-match-" + version,
            "validation_status": "auto_verified", "reviewed_by": None, "selected_at": source["fetched_at"], "candidate_source_record_ids": [sid]})
    paper["openalex_id"] = work["id"]
    provenance("openalex_id", "id")
    preprint_doi = version == CVPR_2026_RULE_VERSION and (work.get("doi") or "").lower().startswith("https://doi.org/10.48550/arxiv.")
    if not paper["doi"] and not preprint_doi and re.fullmatch(r"https://doi.org/10\.\d{4,9}/\S+", work.get("doi") or ""):
        paper["doi"] = work["doi"].removeprefix("https://doi.org/").lower()
        provenance("doi", "doi")
    count = work.get("cited_by_count")
    if type(count) is int and count >= 0:
        paper.update(citation_count=count, citation_count_source_record_id=sid, citation_count_observed_at=source["fetched_at"])
        provenance("citation_count", "cited_by_count")
    refs = work.get("referenced_works")
    if isinstance(refs, list) and all(isinstance(x, str) and re.fullmatch(r"https://openalex.org/W\d+", x) for x in refs):
        paper.update(referenced_works=refs, references_status="verified")
        provenance("referenced_works", "referenced_works")
    else:
        paper["references_status"] = "missing_in_source"
    index = work.get("abstract_inverted_index")
    if paper["abstract"] is None and isinstance(index, dict) and index:
        positions = [(pos, word) for word, offsets in index.items() for pos in offsets]
        if sorted(p for p, _ in positions) == list(range(len(positions))):
            abstract = normalize(" ".join(word for _, word in sorted(positions)))
            text = text_record(paper["paper_id"], sid, "json:abstract_inverted_index", abstract, "openalex-json-1.0.0", source["fetched_at"])
            records["text_versions.jsonl"].append(text)
            paper.update(abstract=abstract, abstract_text_version_id=text["text_version_id"])
            provenance("abstract", "abstract_inverted_index")
