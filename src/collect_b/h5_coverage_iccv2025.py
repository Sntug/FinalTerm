import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from src.collect.common import REPO_ROOT, json_bytes, publish, within
from src.collect.contract import load_records
from . import h5_coverage_iccv2023 as base

COLLECTOR = "config/b_iccv2025_350.json"
H5 = "config/b_iccv2025_h5.json"
OUT = "outputs/b_iccv2025/h5_coverage.json"


def review_counts(rows):
    return dict(rows=len(rows), papers=len({r["paper_id"] for r in rows if r["paper_id"]}),
                by_entity=dict(sorted(Counter(r["entity_type"] for r in rows).items())))


def report(root):
    with patch.multiple(base, COLLECTOR=COLLECTOR, H5=H5):
        result = base.report(root)
    manifest = json.loads(within(root, result["manifest"]).read_text(encoding="utf-8"))
    tables = {Path(f["path"]).name: f["path"] for f in manifest["files"]}
    result["needs_review"] = review_counts(load_records(within(root, tables["needs_review.csv"])))
    return result


if __name__ == "__main__":
    result = report(REPO_ROOT)
    publish({REPO_ROOT / OUT: json_bytes(result)})
    print(json.dumps(result, indent=2))
