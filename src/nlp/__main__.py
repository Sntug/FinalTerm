import argparse
import json
from pathlib import Path

from src.collect.common import REPO_ROOT
from .pipeline import run, DEFAULT_CONFIG

parser = argparse.ArgumentParser(description="Offline A4 Task/Dataset extraction (Contract v2)")
parser.add_argument("--root", type=Path, default=REPO_ROOT)
parser.add_argument("--config", default=DEFAULT_CONFIG)
args = parser.parse_args()
try:
    print(json.dumps(run(args.root, args.config), indent=2, ensure_ascii=False))
except (ValueError, KeyError, OSError) as exc:
    parser.exit(1, f"ERROR: {exc}\n")
