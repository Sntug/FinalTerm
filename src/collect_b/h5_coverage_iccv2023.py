import json
from collections import Counter
from pathlib import Path

from src.clean.h5_coverage import fraction
from src.clean.verify import verify
from src.collect.common import REPO_ROOT, json_bytes, load_config, load_selection, publish, within
from src.collect.contract import load_records

COLLECTOR = "config/b_iccv2023_trend_350.json"
H5 = "config/b_iccv2023_trend_h5.json"
OUT = "outputs/b_iccv2023/trend/h5_coverage.json"


def report(root):
    collector = load_config(root, COLLECTOR)
    selection = load_selection(root, collector)
    cfg = json.loads(within(root, H5).read_text(encoding="utf-8"))
    verification = verify(root, H5)
    metadata = json.loads(within(root, cfg["input_manifest"]).read_text(encoding="utf-8"))
    if metadata["source_snapshot_id"] != selection["source_snapshot_id"]:
        raise ValueError("Metadata snapshot is not bound to the selection lock")
    manifest_path = cfg["processed_dir"] + "/snapshot_manifest.json"
    manifest = json.loads(within(root, manifest_path).read_text(encoding="utf-8"))
    tables = {Path(f["path"]).name: within(root, f["path"]) for f in manifest["files"]}
    registry = sorted(load_records(tables["paper_registry.csv"]), key=lambda r: r["selection_rank"])
    expected = [(r["selection_rank"], r["paper_id"], r["cvf_url"]) for r in selection["papers"]]
    actual = [(r["selection_rank"], r["paper_id"], r["cvf_url"]) for r in registry]
    if actual != expected:
        raise ValueError("H5 registry differs from the locked sample")
    verified_count = sum(r["status"] == "cvf_verified" for r in registry)
    if verified_count != len(expected):
        raise ValueError(f"Only {verified_count}/{len(expected)} locked papers verified")
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
    publish({REPO_ROOT / OUT: json_bytes(result)})
    print(json.dumps(result, indent=2))
