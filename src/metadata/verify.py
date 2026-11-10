"""Schema, raw hashes, provenance and exact deterministic A5 replay."""
import argparse
import json
from pathlib import Path
from src.collect.common import REPO_ROOT, within
from src.collect.contract import contract
from src.nlp.validation import read_manifest, verify_graph_contract
from .pipeline import make_output, DEFAULT_CONFIG


def verify(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    expected, output, summary = make_output(root, config_path)
    path = next(p for p in output if p.name == "snapshot_manifest.json" and p.parent.name != "current")
    manifest, tables = read_manifest(root, path.relative_to(root).as_posix(), contract()["files"])
    if manifest != expected:
        raise ValueError("A5 manifest differs from replay")
    for p, content in output.items():
        if not p.exists() or p.read_bytes() != content:
            raise ValueError("A5 output differs from replay: " + str(p.relative_to(root)))
    validation = verify_graph_contract(root, manifest)
    return dict(passed=True, deterministic_replay=True, contract_validation=validation, **summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root, args.config), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
