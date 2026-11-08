"""Shared CVF/OpenAlex metadata collector."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import DEFAULT_CONFIG, REPO_ROOT
from .pilot import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--offline", action="store_true", help="Use only cached responses; never access the network")
    args = parser.parse_args()
    try:
        result = run(args.root, args.config, offline=args.offline)
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["collection_complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
