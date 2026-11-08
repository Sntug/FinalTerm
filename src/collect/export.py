"""Convert CVF observations to the existing v2 contract without identity guesses."""
from __future__ import annotations

from src.clean.text import identifier, text_record
from .common import PARSER_VERSION
from .contract import contract, validate_records


def export_records(observations: list[dict], sources: list[dict], listing: dict) -> dict[str, list[dict]]:
    spec = contract()
    records = {name: [] for name in spec["files"]}
    records["source_records.jsonl"] = sources
    for rank, old in enumerate(observations, 1):
        pid, sid = old["paper_id"], old["source_record_id"]
        paper = {field: old.get(field) for field in spec["files"]["papers.jsonl"]["fields"]}
        paper.update(schema_version=spec["schema_version"], representative_source_record_id=sid,
                     citation_count_source_record_id=None, citation_count_observed_at=None,
                     title_text_version_id=None, abstract_text_version_id=None)
        paper["authors"] = [{**author, "authorship_id": identifier("authorship", pid, str(author["author_order"]))}
                            for author in old["authors"]]
        selectors = {"title": "html:meta[name=citation_title]@content",
                     "abstract": "html:div#abstract.text",
                     "authors": "html:meta[name=citation_author]@content[]",
                     "publication_date": ("html:div.bibref.text" if len(old["citation_publication_date_raw"]) == 4
                                          and old["date_precision"] == "month"
                                          else "html:meta[name=citation_publication_date]@content"),
                     "pdf_url": "html:meta[name=citation_pdf_url]@content",
                     "arxiv_url": 'html:a[href*="arxiv.org/abs/"]@href'}
        for field in ("title", "abstract"):
            if old[field] is not None:
                text = text_record(pid, sid, selectors[field], old[field + "_raw"], PARSER_VERSION, old["captured_at"])
                if text["normalized_text"] != old[field]:
                    raise ValueError("Parser text differs from the v2 normalizer")
                records["text_versions.jsonl"].append(text)
                paper[field + "_text_version_id"] = text["text_version_id"]
        if old["doi"] is not None:
            selectors["doi"] = old["doi_field_path"]
        for field, selector in selectors.items():
            if old[field]:
                records["field_provenance.csv"].append({
                    "paper_id": pid, "field_name": field, "source_record_id": sid, "field_path": selector,
                    "selection_rule": "cvf-representative-1", "validation_status": "auto_verified",
                    "reviewed_by": None, "selected_at": old["captured_at"], "candidate_source_record_ids": [sid]})
        for field in ("conference", "conference_year", "track"):
            records["field_provenance.csv"].append({
                "paper_id": pid, "field_name": field, "source_record_id": listing["source_record_id"],
                "field_path": 'html:a[href="' + old["cvf_url"].removeprefix("https://openaccess.thecvf.com") + '"]',
                "selection_rule": "official-main-listing-1", "validation_status": "auto_verified", "reviewed_by": None,
                "selected_at": listing["fetched_at"], "candidate_source_record_ids": [listing["source_record_id"]]})
        records["papers.jsonl"].append(paper)
        registry = {field: paper.get(field) for field in spec["files"]["paper_registry.csv"]["fields"]}
        registry.update(status="cvf_verified", selection_rank=rank, source_record_id=sid, verified_at=old["captured_at"])
        records["paper_registry.csv"].append(registry)
        for author in paper["authors"]:
            records["authorships.csv"].append({
                "authorship_id": author["authorship_id"], "paper_id": pid,
                "author_id": None, "author_name": author["name"], "author_name_raw": author["name_raw"],
                "author_order": author["author_order"], "identity_status": "unresolved",
                "affiliation_raw": None, "institution_id": None, "source_record_id": sid, "owner": old["owner"],
                "identity_source_record_id": None, "affiliation_source_record_id": None,
                "affiliation_status": "not_collected", "decision_ids": []})
    for name, rows in records.items():
        validate_records(name, rows)
    return records
