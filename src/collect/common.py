"""Stable CVF identities and file utilities for the repository integration."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from src.clean.text import canonical_json

REPO_ROOT = Path(__file__).resolve().parents[2]
PARSER_VERSION = "cvf-html-1.0.0"
CODE_VERSION = "a2-collector-1.2.0"
DEFAULT_CONFIG = "config/a_cvpr2024_pilot.json"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_cvf_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.netloc != "openaccess.thecvf.com":
        raise ValueError("Expected an HTTPS URL on openaccess.thecvf.com")
    if not re.fullmatch(r"/content/(CVPR2024|ICCV2023)/html/[^/]+_paper\.html", unquote(parts.path)):
        raise ValueError("Expected a main-conference CVPR2024/ICCV2023 detail URL")
    if parts.query:
        raise ValueError("Paper detail URLs must not have a query")
    return "https://openaccess.thecvf.com" + parts.path


def paper_id_from_url(url: str) -> str:
    parts = urlsplit(canonical_cvf_url(url)).path.split("/")
    return f"cvf:{parts[2]}:{unquote(parts[-1]).removesuffix('_paper.html')}"


def within(root: Path, relative: str) -> Path:
    """Resolve symlinks as well as '..'; never accept absolute paths in manifests."""
    root = root.resolve()
    if Path(relative).is_absolute():
        raise ValueError(f"Expected a relative path: {relative}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError(f"Path escapes its root: {relative}")
    return path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def record_bytes(name: str, fields: list[str], rows: list[dict]) -> bytes:
    if name.endswith(".jsonl"):
        return "".join(canonical_json(row) + "\n" for row in rows).encode("utf-8")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: canonical_json(value) if isinstance(value, (list, dict)) else value
                         for key, value in row.items()})
    return stream.getvalue().encode("utf-8-sig")


def publish(files: dict[Path, bytes]) -> None:
    """Resume equal files; refuse different existing bytes before writing any file.

    Each file is published atomically. A failed multi-file export is resumable;
    its snapshot manifest is always supplied last by the caller.
    """
    for path, content in files.items():
        if path.exists() and path.read_bytes() != content:
            raise ValueError(f"Refusing to overwrite different existing file: {path}")
    for path, content in files.items():
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=".a2-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(content)
            replace_file(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def load_config(root: Path, config_path: str = DEFAULT_CONFIG) -> dict:
    config = json.loads(within(root, config_path).read_text(encoding="utf-8"))
    if config["schema_version"] != "2.0.0" or (config["conference"], config["conference_year"]) not in {("CVPR", 2024), ("ICCV", 2023)}:
        raise ValueError("Unsupported schema or conference edition")
    if not config["owner"] or type(config["target_count"]) is not int or config["target_count"] < 1:
        raise ValueError("Owner and positive target_count required")
    corpus = config["conference"].lower() + str(config["conference_year"])
    for key, prefix in (("raw_dir", "data/raw/" + corpus), ("processed_dir", "data/processed/" + corpus), ("output_dir", "outputs")):
        path = within(root, config[key])
        if not path.is_relative_to(within(root, prefix)):
            raise ValueError("Output escapes configured corpus: " + key)
    if config["listing_url"] != f'https://openaccess.thecvf.com/{config["conference"]}{config["conference_year"]}?day=all':
        raise ValueError("Expected official main conference listing")
    if config.get("contract_dir") != "config/contracts/v2":
        raise ValueError("Use the canonical v2 contract")
    within(root, config["registry_input"])
    if config.get("checkpoint_file") and not within(root, config["checkpoint_file"]).is_relative_to(within(root, config["raw_dir"])):
        raise ValueError("Checkpoint must stay inside configured raw corpus")
    if type(config.get("batch_size", 25)) is not int or config.get("batch_size", 25) < 1:
        raise ValueError("Positive batch_size required")
    for key in ("delay_seconds", "timeout_seconds", "retries", "openalex_delay_seconds", "max_retry_wait_seconds"):
        if config[key] < 0 or (key == "timeout_seconds" and config[key] == 0):
            raise ValueError("Invalid transport configuration: " + key)
    return config


def load_selection(root: Path, config: dict) -> dict:
    with within(root, config["registry_input"]).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != config["target_count"]:
        raise ValueError("Registry count must equal target_count; no implicit sampling")
    ids, urls = set(), set()
    for rank, row in enumerate(rows, 1):
        url = canonical_cvf_url(row["cvf_url"])
        pid = paper_id_from_url(url)
        if pid != row["paper_id"] or not pid.startswith(f'cvf:{config["conference"]}{config["conference_year"]}:'):
            raise ValueError("Registry ID/URL or conference mismatch")
        if row["owner"] != config["owner"] or row["conference"] != config["conference"] or int(row["conference_year"]) != config["conference_year"]:
            raise ValueError("Registry owner/conference/year mismatch")
        if pid in ids or url in urls:
            raise ValueError("Duplicate registry URL/ID")
        ids.add(pid); urls.add(url)
        row["cvf_url"] = url
        row["selection_rank"] = rank
    result = {"papers": rows, "seed": config["seed"], "source_snapshot_id": "registry:" + __import__("hashlib").sha256(within(root, config["registry_input"]).read_bytes()).hexdigest()}
    if config.get("selection_file"):
        locked = json.loads(within(root, config["selection_file"]).read_text(encoding="utf-8"))
        if locked.get("registry_sha256") and locked["registry_sha256"] != __import__("hashlib").sha256(within(root, config["registry_input"]).read_bytes()).hexdigest():
            raise ValueError("Locked registry hash changed")
        if config.get("selection_lock_copy") and within(root, config["selection_lock_copy"]).read_bytes() != within(root, config["selection_file"]).read_bytes():
            raise ValueError("Selection lock copies differ")
        if locked["seed"] != config["seed"] or [(p["paper_id"], p["cvf_url"]) for p in locked["papers"]] != [(p["paper_id"],p["cvf_url"]) for p in rows]:
            raise ValueError("Registry differs from locked selection")
        for row, old in zip(rows, locked["papers"]):
            if row.get("source_record_id") != old["source_record_id"]:
                raise ValueError("Locked source ID changed")
        result.update({k:v for k,v in locked.items() if k != "papers"})
    return result


def atomic_json(path: Path, value: object) -> None:
    """Replace a collector-owned checkpoint/report or manifest pointer atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".a2-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(json_bytes(value))
        replace_file(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def replace_file(source, destination):
    """Bounded retries for Windows readers briefly denying atomic replacement."""
    for attempt in range(6):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if os.name != 'nt' or attempt == 5:
                raise
            time.sleep(0.1 * (attempt + 1))
