import argparse
import json
from pathlib import Path
from src.collect.common import REPO_ROOT
from .pipeline import run, summarize, DEFAULT_CONFIG

parser = argparse.ArgumentParser(description="A6 offline quality audit and human review forms")
parser.add_argument("action", choices=("run", "summarize"), nargs="?", default="run")
parser.add_argument("--root", type=Path, default=REPO_ROOT)
parser.add_argument("--config", default=DEFAULT_CONFIG)
args = parser.parse_args()
try:
    result = (run if args.action == "run" else summarize)(args.root, args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
except (OSError, ValueError, KeyError) as exc:
    parser.exit(1, f"ERROR: {exc}\n")
