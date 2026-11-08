"""Small, shared data-contract and file utilities (Python 3.12+)."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCHEMA_VERSION = "1.0.0"
PARSER_VERSION = "cvf-html-1.0.0"
REGISTRY_FIELDS = [
    "paper_id", "doi", "cvf_url", "conference", "conference_year", "owner", "status",
    "schema_version", "track", "scope", "venue_id", "title", "selection_rank",
    "source_record_id", "verified_at",
]
ORIGINAL_FIELDS = REGISTRY_FIELDS[:7]
METADATA_FIELDS = [
    "paper_id", "owner", "title", "conference", "conference_year", "track", "scope",
    "doi", "cvf_url", "pdf_url", "arxiv_url", "publication_date", "date_precision",
    "author_count", "authors_json", "abstract", "openalex_id", "citation_count",
    "affiliation_status", "references_status", "source_record_id",
]
AUTHORSHIP_FIELDS = [
    "authorship_id", "paper_id", "author_id", "author_name", "author_name_raw",
    "author_order", "identity_status", "affiliation_raw", "institution_id",
    "source_record_id", "owner",
]
UNDIRECTED_RELATIONS = {"COAUTHORED_WITH", "COLLABORATED_WITH"}
RELATIONS = {
    "AUTHORED", "AFFILIATED_WITH", "PUBLISHED_IN", "CITES", "BASED_IN",
    "COAUTHORED_WITH", "COLLABORATED_WITH", "STUDIES_TASK", "USES_METHOD", "EVALUATED_ON",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(prefix: str, *parts: str) -> str:
    return prefix + ":" + digest("\0".join(parts).encode("utf-8"))


def edge_key(src: str, relation: str, dst: str) -> tuple[str, str, str]:
    """Shared graph identity rule; this does not build/import any graph in A1."""
    if relation not in RELATIONS:
        raise ValueError("Unknown relation type")
    if relation in UNDIRECTED_RELATIONS:
        if src == dst:
            raise ValueError("Collaboration self-loops are not valid")
        src, dst = sorted((src, dst))
    return src, relation, dst


def edge_id(src: str, relation: str, dst: str) -> str:
    return stable_id("edge", *edge_key(src, relation, dst))


def evidence_id(paper_id: str | None, source_record_id: str, field_path: str,
                rule_id: str, rule_version: str, evidence_text: str | None = None,
                start_char: int | None = None, end_char: int | None = None,
                supporting_evidence_ids: tuple[str, ...] = ()) -> str:
    """Deterministic v1 evidence identity, available for the later graph modules."""
    if (start_char is None) != (end_char is None):
        raise ValueError("Evidence offsets must be both present or both null")
    if start_char is not None and (start_char < 0 or end_char < start_char):
        raise ValueError("Invalid evidence offsets")
    return stable_id("evidence", paper_id or "", source_record_id, field_path, rule_id, rule_version,
                     evidence_text or "", "" if start_char is None else str(start_char),
                     "" if end_char is None else str(end_char),
                     json.dumps(sorted(set(supporting_evidence_ids)), ensure_ascii=False, separators=(",", ":")))


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def canonical_cvf_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.netloc != "openaccess.thecvf.com":
        raise ValueError("Expected an HTTPS URL on openaccess.thecvf.com")
    if not re.fullmatch(r"/content/(CVPR2024|ICCV2023)/html/[^/]+_paper\.html", unquote(parts.path)):
        raise ValueError("Expected a main-conference CVPR2024/ICCV2023 detail URL")
    if parts.query:
        raise ValueError("Paper detail URLs must not have a query")
    return "https://openaccess.thecvf.com" + parts.path


def paper_id_from_url(url: str) -> str:
    url = canonical_cvf_url(url)
    parts = urlsplit(url).path.split("/")
    return f"cvf:{parts[2]}:{unquote(parts[-1]).removesuffix('_paper.html')}"


def venue_id(conference: str, year: int) -> str:
    return f"venue:{conference}:{year}:main"


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    if len(fields) != len(set(fields)) or any(None in row for row in rows):
        raise ValueError(f"Malformed CSV: {path}")
    return fields, rows


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # BOM makes Vietnamese text readable in Excel. Delimiter stays comma for Git/tools.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
