"""Verify A4 tables by Contract v2 and replay; optionally verify a complete graph."""
import argparse
import json
from pathlib import Path

from contract_v2.text import identifier
from src.collect.common import REPO_ROOT, within
from .pipeline import prepare, DEFAULT_CONFIG, code_version, dictionary_versions
from .validation import TABLES, TREND_PROJECT, read_manifest, validate_nlp, verify_graph_contract
from src.collect.contract import contract


def verify(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    cfg, inputs, original, extractor, expected, summary = prepare(root, config_path)
    manifest, data = read_manifest(root, cfg["output_dir"] + "/snapshot_manifest.json", TABLES)
    trend = "graph_config" in cfg
    project = TREND_PROJECT if trend else contract()["project_id"]
    counts = (len(data["nodes.csv"]), len(data["edges.csv"])) if trend else (None, None)
    if (manifest["project_id"] != project or manifest["graph_ready"] is not trend
            or (manifest["node_count"], manifest["edge_count"]) != counts
            or manifest["model"] != (extractor.runtime if trend else extractor.model)):
        raise ValueError("NLP project, readiness, counts or model mismatch")
    if manifest["code_version"] != code_version(extractor) or manifest["input_manifests"] != cfg["input_manifests"]:
        raise ValueError("A4 config/code mismatch")
    if manifest["source_snapshot_id"] != identifier("snapshot:v2", *[m["snapshot_id"] for m in inputs]):
        raise ValueError("A4 source snapshot mismatch")
    if manifest["dictionary_versions"] != dictionary_versions(extractor) or extractor.runtime not in manifest["parser_versions"]:
        raise ValueError("A4 dictionary/runtime mismatch")
    validate_nlp(data, original, project)
    if trend and any(manifest["rule_versions"].get(ev["rule_id"]) != ev["rule_version"] for ev in data["evidence.jsonl"]):
        raise ValueError("Evidence rule/version differs from H7 manifest")
    if data != expected:
        raise ValueError("A4 output differs from deterministic rule replay")
    actual = json.loads(within(root, cfg["output_dir"] + "/summary.json").read_text(encoding="utf-8"))
    summary.update(snapshot_id=manifest["snapshot_id"], graph_ready=trend, model=extractor.runtime, network_requests=0)
    if actual != summary:
        raise ValueError("A4 summary differs from replay")
    return dict(passed=True, deterministic_replay=True, **summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--graph-manifest", help="Optional complete graph manifest, relative to root")
    args = parser.parse_args()
    try:
        result = verify(args.root, args.config)
        if args.graph_manifest:
            manifest, _ = read_manifest(args.root, args.graph_manifest)
            result["graph_contract"] = verify_graph_contract(args.root, manifest)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
