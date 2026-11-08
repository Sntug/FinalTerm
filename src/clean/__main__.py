"""Run A3 offline; reads raw snapshots, never makes network requests."""
import argparse
import json
from pathlib import Path
from src.collect.common import REPO_ROOT
from .pipeline import DEFAULT_CONFIG, run
from .verify import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=REPO_ROOT)
    parser.add_argument('--config', default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        result = run(args.root, args.config)
        result['verification'] = verify(args.root, args.config)
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['delivery_complete']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
