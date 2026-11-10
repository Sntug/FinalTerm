import argparse
import json
from pathlib import Path
from src.collect.common import REPO_ROOT
from .pipeline import DEFAULT_CONFIG, run, fetch_selected

parser = argparse.ArgumentParser(description="A5 metadata/source verification; offline by default")
parser.add_argument("--root", type=Path, default=REPO_ROOT)
parser.add_argument("--config", default=DEFAULT_CONFIG)
parser.add_argument("--fetch-only", action="store_true", help="Fetch only the bounded supplemental plan, cache receipts, then stop")
args = parser.parse_args()
try:
    result = fetch_selected(args.root, args.config) if args.fetch_only else run(args.root, args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
except (ValueError, KeyError, OSError) as exc:
    parser.exit(1, f"ERROR: {exc}\n")
