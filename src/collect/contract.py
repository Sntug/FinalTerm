"""Read the canonical v2 files, never reconstruct a second schema in Python."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .common import REPO_ROOT

CONTRACT_DIR = REPO_ROOT / "config/contracts/v2"


def contract() -> dict:
    return json.loads((CONTRACT_DIR / "data_contract.json").read_text(encoding="utf-8"))


def schema_for(name: str) -> dict:
    return json.loads((CONTRACT_DIR / contract()["files"][name]["record_schema"]).read_text(encoding="utf-8"))


def validate_json(value: object, schema: dict, path: str = "$") -> list[str]:
    """Validate only the type/constraint subset used by the delivered schemas.

    Adapted from the A1 validator. This is not a general Draft 2020-12 engine.
    """
    errors = []
    types = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
             "string": lambda v: isinstance(v, str), "integer": lambda v: type(v) is int,
             "number": lambda v: type(v) in (int, float), "boolean": lambda v: type(v) is bool,
             "null": lambda v: v is None}
    expected = schema.get("type")
    if expected and not any(types[t](value) for t in (expected if isinstance(expected, list) else [expected])):
        return [f"{path}: expected {expected}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: outside enum")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        for key, item in value.items():
            if key in schema.get("properties", {}):
                errors.extend(validate_json(item, schema["properties"][key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: unexpected property")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: too few items")
        for index, item in enumerate(value):
            errors.extend(validate_json(item, schema.get("items", {}), f"{path}[{index}]"))
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: too short")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: invalid pattern")
    elif type(value) in (int, float) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: below minimum")
    return errors


def validate_records(name: str, rows: list[dict]) -> None:
    spec, schema = contract()["files"][name], schema_for(name)
    keys = []
    for index, row in enumerate(rows):
        errors = validate_json(row, schema, f"{name}[{index}]")
        if errors:
            raise ValueError("; ".join(errors))
        keys.append(tuple(row[key] for key in spec["logical_unique_key"]))
    if len(keys) != len(set(keys)):
        raise ValueError(f"Duplicate logical key: {name}")


def load_records(path: Path) -> list[dict]:
    spec, schema = contract()["files"][path.name], schema_for(path.name)
    if path.suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != spec["fields"]:
                raise ValueError(f"Header mismatch: {path.name}")
            rows = list(reader)
        for row in rows:
            if set(row) != set(spec["fields"]) or any(value is None for value in row.values()):
                raise ValueError(f"Malformed CSV: {path.name}")
            for key, value in row.items():
                kinds = schema["properties"][key]["type"]
                kinds = kinds if isinstance(kinds, list) else [kinds]
                if value == "" and "null" in kinds:
                    row[key] = None
                elif "integer" in kinds:
                    row[key] = int(value)
                elif "array" in kinds or "object" in kinds:
                    row[key] = json.loads(value)
    else:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    validate_records(path.name, rows)
    return rows
