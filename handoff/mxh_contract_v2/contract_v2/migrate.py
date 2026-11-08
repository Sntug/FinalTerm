"""Non-destructive A1 v1 -> metadata v2 migration. No API calls or Neo4j writes."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .model import FILES, PAPERS, VERSION
from .text import NORMALIZATION_VERSION, canonical_json, identifier, sha256, text_record


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_records(path: Path, rows: list[dict]) -> None:
    fields = FILES[path.name][0]
    if path.suffix == ".csv":
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: canonical_json(v) if isinstance(v, (list,dict)) else v for k,v in row.items()})
    else:
        path.write_text("".join(canonical_json(row)+"\n" for row in rows), encoding="utf-8")


def migrate(input_root: Path, output_root: Path) -> dict:
    input_root, output_root = input_root.resolve(), output_root.resolve()
    if output_root.exists(): raise ValueError("Output must be a new directory; v1 is never overwritten")
    if output_root == input_root or input_root in output_root.parents:
        raise ValueError("Output must be outside the original v1 package")
    old_papers = read_jsonl(input_root / "data/raw/pilot_papers.jsonl")
    old_sources = read_jsonl(input_root / "data/raw/source_records.jsonl")
    old_authors = read_csv(input_root / "data/processed/authorships.csv")
    old_registry = read_csv(input_root / "data/processed/paper_registry.csv")
    old_manifest = json.loads((input_root / "data/processed/selection_manifest.json").read_text(encoding="utf-8"))
    old_summary = json.loads((input_root / "outputs/pilot_summary.json").read_text(encoding="utf-8"))
    if not old_papers or any(p["schema_version"] != "1.0.0" for p in old_papers):
        raise ValueError("This migration supports only the delivered A1 v1 snapshot")
    for name in ("nodes.csv", "edges.csv", "evidence.jsonl", "merge_log.jsonl"):
        p = input_root / "data/processed" / name
        if p.exists() and ((read_csv(p) if p.suffix==".csv" else read_jsonl(p))):
            raise ValueError("Existing graph/decision records must be migrated or rebuilt explicitly: " + name)
    if any(a["author_id"] or a["institution_id"] or a["identity_status"] != "unresolved" for a in old_authors):
        raise ValueError("Enriched identities need provenance-aware migration; refusing to invent it")
    if any(p["openalex_status"] != "not_collected" or p["openalex_id"] or p["citation_count"] is not None for p in old_papers):
        raise ValueError("OpenAlex-enriched data require a different migration")
    source_by_id = {s["source_record_id"]: s for s in old_sources}
    for source in old_sources:
        path = (input_root / source["raw_path"]).resolve()
        if input_root not in path.parents or not path.exists(): raise ValueError("Unsafe/missing source path")
        if sha256(gzip.decompress(path.read_bytes())) != source["content_sha256"]:
            raise ValueError("Source bytes do not match source hash")
    for p in old_papers:
        if p["source_record_id"] not in source_by_id: raise ValueError("Missing paper source")
    if len(old_registry) != len(old_papers) or len({p["paper_id"] for p in old_papers}) != len(old_papers):
        raise ValueError("Duplicate/mismatched paper registry")
    output_root.mkdir(parents=True)
    folder = output_root / "data/processed"; folder.mkdir(parents=True)
    legacy = output_root / "legacy_v1"; legacy.mkdir()
    for rel in ["data/raw/pilot_papers.jsonl", "data/raw/source_records.jsonl", "data/processed/paper_registry.csv",
                "data/processed/authorships.csv", "data/processed/selection_manifest.json", "outputs/pilot_summary.json"]:
        shutil.copyfile(input_root / rel, legacy / Path(rel).name)
    for source in old_sources:
        dest = (output_root / source["raw_path"]).resolve()
        if output_root not in dest.parents: raise ValueError("Unsafe target raw path")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(input_root / source["raw_path"], dest)
    sources = [{**s, "schema_version": VERSION} for s in old_sources]
    registry = [{**r, "schema_version": VERSION, "conference_year": int(r["conference_year"]),
                 "selection_rank": int(r["selection_rank"]), "doi": r["doi"] or None} for r in old_registry]
    authorships = [{**a, "author_order": int(a["author_order"]), "author_id": None, "institution_id": None,
                    "affiliation_raw": None, "identity_source_record_id": None, "affiliation_source_record_id": None,
                    "affiliation_status": "not_collected", "decision_ids": []} for a in old_authors]
    texts, papers, provenance = [], [], []
    listing_sources = {c["owner"]: c["listing_source_record_id"] for c in old_manifest["corpora"]}
    for old in old_papers:
        pid, sid = old["paper_id"], old["source_record_id"]
        paper = {name: old.get(name) for name in PAPERS}
        paper.update(schema_version=VERSION, representative_source_record_id=sid,
                     citation_count_source_record_id=None, citation_count_observed_at=None,
                     references_status="not_collected", title_text_version_id=None, abstract_text_version_id=None)
        paper["authors"] = [{**a, "authorship_id": identifier("authorship", pid, str(a["author_order"]))} for a in old["authors"]]
        for field, selector in [("title", "html:meta[name=citation_title]@content"), ("abstract", "html:div#abstract.text")]:
            if old[field]:
                text = text_record(pid, sid, selector, old[field+"_raw"], old["parser_version"], old["captured_at"])
                if text["normalized_text"] != old[field]: raise ValueError("v1 text cannot be reproduced by nfc-ws-1")
                texts.append(text); paper[field+"_text_version_id"] = text["text_version_id"]
        selectors = {"title": "html:meta[name=citation_title]@content", "authors": "html:meta[name=citation_author]@content[]",
                     "abstract": "html:div#abstract.text", "publication_date": "html:div.bibref.text",
                     "pdf_url": "html:meta[name=citation_pdf_url]@content", "arxiv_url": 'html:a[href*="arxiv.org/abs/"]@href'}
        for field, selector in selectors.items():
            if old[field]:
                provenance.append(dict(paper_id=pid, field_name=field, source_record_id=sid, field_path=selector,
                                       selection_rule="cvf-representative-1", validation_status="auto_verified", reviewed_by=None,
                                       selected_at=old["captured_at"], candidate_source_record_ids=[sid]))
        for field in ("conference", "conference_year"):
            lid = listing_sources[old["owner"]]
            provenance.append(dict(paper_id=pid, field_name=field, source_record_id=lid,
                                   field_path='html:a[href="'+old["cvf_url"].removeprefix("https://openaccess.thecvf.com")+'"]',
                                   selection_rule="official-main-listing-1", validation_status="auto_verified", reviewed_by=None,
                                   selected_at=source_by_id[lid]["fetched_at"], candidate_source_record_ids=[lid]))
        papers.append(paper)
    records = {"paper_registry.csv": registry, "papers.jsonl": papers, "source_records.jsonl": sources,
               "authorships.csv": authorships, "text_versions.jsonl": texts, "field_provenance.csv": provenance}
    for name in FILES: write_records(folder / name, records.get(name, []))
    files = []
    for name, (_, _, role) in FILES.items():
        p = folder / name
        files.append(dict(path=p.relative_to(output_root).as_posix(), sha256=sha256(p.read_bytes()),
                          record_count=len(records.get(name, [])), role=role))
    manifest = dict(project_id="mxh_cv_700", schema_version=VERSION, code_version="a1-migration-2.0.0",
                    normalization_version=NORMALIZATION_VERSION, parser_versions=sorted({p["parser_version"] for p in old_papers}),
                    rule_versions={}, dictionary_versions={}, applied_decision_ids=[], graph_ready=False,
                    node_count=None, edge_count=None, files=files)
    snapshot = "snapshot:v2:" + sha256(canonical_json(manifest).encode())
    manifest.update(snapshot_id=snapshot, source_snapshot_id=old_summary["snapshot_id"],
                    created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    (output_root / "snapshot_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    report = dict(schema_version=VERSION, source_snapshot_id=old_summary["snapshot_id"], snapshot_id=snapshot,
                  papers=len(papers), authorship_observations=len(authorships), source_records=len(sources),
                  text_versions=len(texts), field_provenance_records=len(provenance),
                  paper_ids_preserved=[r["paper_id"] for r in registry]==[r["paper_id"] for r in old_registry],
                  source_ids_preserved=[s["source_record_id"] for s in sources]==[s["source_record_id"] for s in old_sources],
                  graph_ready=False, merges_executed=0, author_identity_resolved=False,
                  graph_mutated=False, api_requests=0)
    (output_root / "migration_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try: report = migrate(args.input, args.output)
    except (ValueError, KeyError, OSError) as exc: parser.exit(1, str(exc)+"\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
