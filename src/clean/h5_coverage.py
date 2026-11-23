"""Verify the CVPR 2025 H5 handoff and measure coverage on the locked sample."""
import json
from collections import Counter
from pathlib import Path

from src.collect.common import REPO_ROOT, json_bytes, load_config, load_selection, publish, within
from src.collect.contract import load_records
from .verify import verify


def fraction(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                percent=round(100 * numerator / denominator, 2) if denominator else None)


def report(root):
    collector = load_config(root, "config/a_cvpr2025_350.json")
    selection = load_selection(root, collector)
    config_path = "config/a_cvpr2025_h5.json"
    cfg = json.loads(within(root, config_path).read_text(encoding="utf-8"))
    verification = verify(root, config_path)
    metadata = json.loads(within(root, cfg["input_manifest"]).read_text(encoding="utf-8"))
    if metadata["source_snapshot_id"] != selection["source_snapshot_id"]:
        raise ValueError("Metadata snapshot is not bound to the selection lock")
    manifest_path = cfg["processed_dir"] + "/snapshot_manifest.json"
    manifest = json.loads(within(root, manifest_path).read_text(encoding="utf-8"))
    tables = {Path(f["path"]).name: within(root, f["path"]) for f in manifest["files"]}
    registry = sorted(load_records(tables["paper_registry.csv"]), key=lambda r: r["selection_rank"])
    expected = [(r["selection_rank"], r["paper_id"], r["cvf_url"]) for r in selection["papers"]]
    actual = [(r["selection_rank"], r["paper_id"], r["cvf_url"]) for r in registry]
    if actual != expected or any(r["status"] != "cvf_verified" for r in registry):
        raise ValueError("H5 registry differs from the verified locked sample")
    papers = load_records(tables["papers.jsonl"])
    statuses = Counter(p["openalex_status"] for p in papers)
    if statuses["not_collected"]:
        raise ValueError("OpenAlex collection is incomplete")
    byline = load_records(tables["authorships.csv"])
    verified = [r for r in byline if r["affiliation_status"] == "verified" and r["institution_id"]]
    return dict(manifest=manifest_path, selection_snapshot_id=selection["source_snapshot_id"],
                verified_locked_papers=fraction(len(registry), collector["target_count"]),
                abstract=fraction(sum(bool(p["abstract"]) for p in papers), len(papers)),
                papers_with_verified_affiliation=fraction(len({r["paper_id"] for r in verified}), len(papers)),
                authorships_with_verified_affiliation=fraction(len({r["authorship_id"] for r in verified}),
                                                              len({r["authorship_id"] for r in byline})),
                openalex_status_counts=dict(sorted(statuses.items())), verification=verification)


if __name__ == "__main__":
    result = report(REPO_ROOT)
    publish({REPO_ROOT / "outputs/trend/quality/cvpr2025_h5.json": json_bytes(result)})
    print(json.dumps(result, indent=2))
