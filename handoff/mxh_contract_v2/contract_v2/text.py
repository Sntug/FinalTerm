"""Text-version pinning and evidence identity for NLP modules A4/B5."""
import hashlib
import json
import unicodedata

NORMALIZATION_VERSION = "nfc-ws-1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identifier(prefix: str, *parts: str) -> str:
    return prefix + ":" + sha256("\0".join(parts).encode("utf-8"))


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def text_record(paper_id: str, source_record_id: str, field_path: str, text: str,
                parser_version: str, captured_at: str) -> dict:
    value = normalize(text)
    fingerprint = sha256(value.encode("utf-8"))
    tid = identifier("text:v2", source_record_id, field_path, parser_version, NORMALIZATION_VERSION, fingerprint)
    return dict(text_version_id=tid, paper_id=paper_id, source_record_id=source_record_id,
                field_path=field_path, parser_version=parser_version, normalization_version=NORMALIZATION_VERSION,
                normalized_text=value, normalized_text_sha256=fingerprint, captured_at=captured_at)


def validate_nlp_evidence(evidence: dict, text: dict) -> None:
    if evidence["evidence_kind"] != "nlp": raise ValueError("Expected NLP evidence")
    for key in ("paper_id", "source_record_id", "field_path", "text_version_id", "normalization_version", "normalized_text_sha256"):
        if evidence[key] != text[key]: raise ValueError("Evidence/text mismatch: " + key)
    if sha256(text["normalized_text"].encode("utf-8")) != text["normalized_text_sha256"]:
        raise ValueError("Text content does not match its hash")
    start, end = evidence["start_char"], evidence["end_char"]
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text["normalized_text"]):
        raise ValueError("Invalid half-open Unicode character offsets")
    if text["normalized_text"][start:end] != evidence["evidence_text"]:
        raise ValueError("Evidence slice is stale or incorrect")


def evidence_id(record: dict) -> str:
    return identifier("evidence", "2.0.0", record["evidence_kind"], record.get("paper_id") or "",
                      record.get("source_record_id") or "", record.get("field_path") or "",
                      record.get("text_version_id") or "", record.get("normalized_text_sha256") or "",
                      record.get("normalization_version") or "", record["rule_id"], record["rule_version"],
                      record.get("evidence_text") or "",
                      "" if record.get("start_char") is None else str(record["start_char"]),
                      "" if record.get("end_char") is None else str(record["end_char"]),
                      canonical_json(sorted(set(record["supporting_evidence_ids"]))))
