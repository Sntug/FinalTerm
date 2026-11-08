"""Import only A's locked CVF snapshots as data, never import handoff code."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from src.clean.text import identifier, sha256
from .common import (DEFAULT_CONFIG, REPO_ROOT, json_bytes, load_config,
                     load_selection, publish, read_jsonl, within)


def bootstrap(root: Path, input_root: Path, config_path: str = DEFAULT_CONFIG) -> dict:
    root, input_root = root.resolve(), input_root.resolve()
    config = load_config(root, config_path)
    selection = load_selection(root, config)
    sources_path = input_root / "data/raw/source_records.jsonl"
    sources = read_jsonl(sources_path)
    by_id = {source["source_record_id"]: source for source in sources}
    if len(by_id) != len(sources):
        raise ValueError("Duplicate source IDs in bootstrap input")
    requested = [(selection["listing_source_record_id"], None, config["listing_url"], "listing")]
    requested += [(item["source_record_id"], item["paper_id"], item["cvf_url"], "paper_detail")
                  for item in selection["papers"]]
    files, imported = {}, []
    for sid, pid, url, kind in requested:
        source = by_id[sid]
        if (source["paper_id"], source["url"], source["source_kind"], source["source"], source["http_status"]) != (pid, url, kind, "CVF", 200):
            raise ValueError("Bootstrap source does not match the locked A1 selection")
        raw_path = within(input_root, source["raw_path"])
        compressed = raw_path.read_bytes()
        body = gzip.decompress(compressed)
        if sha256(body) != source["content_sha256"] or identifier("source:cvf", url, sha256(body)) != sid:
            raise ValueError("Bootstrap source hash/ID mismatch")
        old_meta_path = input_root / "data/raw/http" / (sha256(url.encode()) + ".json")
        old_meta = json.loads(old_meta_path.read_text(encoding="utf-8"))
        if any(source[key] != value for key, value in old_meta.items()):
            raise ValueError("Bootstrap HTTP cache metadata disagrees with its source record")
        relative = config["raw_dir"] + "/http/" + source["content_sha256"] + ".html.gz"
        meta = {**old_meta, "raw_path": relative}
        files[within(root, relative)] = compressed
        files[within(root, config["raw_dir"] + "/http/" + old_meta_path.name)] = json_bytes(meta)
        imported.append({"source_record_id": sid, "paper_id": pid, "url": url,
                         "content_sha256": sha256(body), "raw_path": relative,
                         "compressed_sha256": sha256(compressed),
                         "original_raw_path": source["raw_path"]})
    manifest = {"kind": "a1-" + config["conference"].lower() + str(config["conference_year"]) + "-cache-import", "owner": config["owner"], "network_requests": 0,
                "source_snapshot_id": selection["source_snapshot_id"],
                "input_source_records_sha256": sha256(sources_path.read_bytes()), "sources": imported}
    files[within(root, config["raw_dir"] + "/bootstrap_manifest.json")] = json_bytes(manifest)
    publish(files)
    return {"imported_sources": len(imported), "network_requests": 0, "owner": config["owner"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="A1 package directory; read as data only")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        result = bootstrap(args.root, args.input, args.config)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
