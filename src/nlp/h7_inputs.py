"""Prepare CVF abstracts for H7 development or non-gold candidate discovery."""
import argparse
import csv
import gzip
import io
import json
from pathlib import Path

from src.clean.normalize import clean_text
from src.clean.text import sha256, text_record
from src.collect.common import REPO_ROOT, publish, record_bytes, within
from src.collect.cvf import parse_detail
from src.gold.__main__ import FIELDS, LOCKS, select_edition


def manifest_table(root, manifest, name):
    entries = [f for f in manifest["files"] if Path(f["path"]).name == name]
    if len(entries) != 1:
        raise ValueError(f"Expected one {name} in metadata manifest")
    entry = entries[0]
    content = within(root, entry["path"]).read_bytes()
    if sha256(content) != entry["sha256"]:
        raise ValueError(f"Metadata hash mismatch: {name}")
    stream = io.StringIO(content.decode("utf-8-sig"), newline="")
    return list(csv.DictReader(stream)) if name.endswith(".csv") else [json.loads(line) for line in stream]


def prepare(root, edition, manifest_path, group):
    if group not in ("dev", "candidates"):
        raise ValueError("Expected dev or candidates")
    policy = json.loads((root / "config/a_trend_project.json").read_text("utf-8"))
    gold_path = root / "data/gold/gold_set.csv"
    expected = []
    locks = {}
    for name, filename in LOCKS.items():
        locks[name] = json.loads((root / "config" / filename).read_text("utf-8"))
        expected.extend(select_edition(name, locks[name], policy))
    gold_bytes = gold_path.read_bytes()
    gold_hash = sha256(gold_bytes)
    if gold_bytes != record_bytes(gold_path.name, FIELDS, expected):
        raise ValueError("Gold split differs from H4 replay")
    splits = {r["paper_id"]: r["split"] for r in csv.DictReader(io.StringIO(gold_bytes.decode("utf-8-sig")))}

    manifest = json.loads(within(root, manifest_path).read_text("utf-8"))
    registry = manifest_table(root, manifest, "paper_registry.csv")
    registry_by_id = {r["paper_id"]: r for r in registry}
    lock = locks[edition]
    papers = lock["papers"]
    if len(registry) != len(papers) or set(registry_by_id) != {p["paper_id"] for p in papers}:
        raise ValueError(f"{edition}: registry differs from H3")
    sources = {s["source_record_id"]: s for s in manifest_table(root, manifest, "source_records.jsonl")}
    provenance = {r["paper_id"]: r for r in manifest_table(root, manifest, "field_provenance.csv")
                  if r["field_name"] == "abstract"}
    rows = []
    for paper in papers:
        pid = paper["paper_id"]
        if splits.get(pid, "candidates") != group:
            continue
        reg = registry_by_id[pid]
        if reg["status"] != "cvf_verified" or reg["scope"] != "core" or reg["track"] != "main":
            continue
        if pid not in provenance:
            continue
        binding = provenance[pid]
        source = sources[binding["source_record_id"]]
        if (source["paper_id"] != pid or source["source_kind"] != "paper_detail" or
                source["source"] != "CVF" or source["url"] != paper["cvf_url"] or
                binding["field_path"] != "html:div#abstract.text"):
            raise ValueError(f"{pid}: unsupported abstract source")
        body = gzip.decompress(within(root, source["raw_path"]).read_bytes())
        if sha256(body) != source["content_sha256"]:
            raise ValueError(f"{pid}: raw CVF hash mismatch")
        detail = parse_detail(body, source["url"], lock["conference"], lock["conference_year"])
        if not detail["abstract"]:
            raise ValueError(f"{pid}: empty abstract with recorded provenance")
        text, version = detail["abstract"], detail["parser_version"]
        if binding["selection_rule"] == "a3-html-nfc-ws-1":
            text, version = clean_text(text), "a3-metadata-1.0.0"
        elif binding["selection_rule"] != "cvf-representative-1":
            raise ValueError(f"{pid}: unsupported abstract selection rule")
        row = text_record(pid, source["source_record_id"], binding["field_path"], text,
                          version, source["fetched_at"])
        row.update(venue_edition=edition, metadata_snapshot_id=manifest["snapshot_id"],
                   selection_snapshot_id=lock["source_snapshot_id"], gold_sha256=gold_hash,
                   group=group)
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", required=True, choices=LOCKS)
    parser.add_argument("--manifest", required=True, help="verified metadata manifest relative to repository root")
    parser.add_argument("--group", required=True, choices=("dev", "candidates"))
    args = parser.parse_args()
    rows = prepare(REPO_ROOT, args.edition, args.manifest, args.group)
    output = REPO_ROOT / "outputs/trend/nlp/inputs" / f"{args.edition}_{args.group}.jsonl"
    publish({output: record_bytes(output.name, [], rows)})
    print(f"{args.edition} {args.group}: {len(rows)} abstracts -> {output.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
