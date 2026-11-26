import hashlib
import http.client
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config/trend_slm.json"
METRICS = ("eval_count", "eval_duration", "prompt_eval_count", "total_duration", "load_duration")
TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}
KEYWORDS = {"type", "properties", "required", "additionalProperties", "items", "enum", "maxItems", "title", "description"}
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def load_config(path=CONFIG_PATH):
    return json.loads(Path(path).read_text("utf-8"))


def request(config, endpoint, body=None):
    data = None if body is None else json.dumps(body).encode()
    call = urllib.request.Request(config["host"] + endpoint, data, {"Content-Type": "application/json"})
    with OPENER.open(call, timeout=config["timeout_seconds"]) as response:
        return json.load(response)


def post_generate(config, body):
    for attempt in range(config.get("retries", 2) + 1):
        try:
            return request(config, "/api/generate", body)
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == config.get("retries", 2):
                raise RuntimeError(f"Ollama HTTP {error.code}: {error.read().decode(errors='replace')}") from error
        except (OSError, http.client.HTTPException):
            if attempt == config.get("retries", 2):
                raise
        time.sleep(config.get("retry_wait_seconds", 5) * (attempt + 1))


def live_digest(config, model):
    for entry in request(config, "/api/tags")["models"]:
        if entry["name"] == model:
            return entry["digest"]
    raise RuntimeError(f"model {model} is not installed; run: ollama pull {model}")


def check_schema(schema):
    unknown = set(schema) - KEYWORDS
    kind = schema.get("type")
    if unknown or (kind is not None and (not isinstance(kind, str) or kind not in TYPES)) \
            or not isinstance(schema.get("additionalProperties", True), bool):
        raise TypeError(f"unsupported schema: keywords {sorted(unknown)}, type {kind!r}")
    for child in [*schema.get("properties", {}).values(), schema.get("items", {})]:
        if child:
            check_schema(child)


def validate(value, schema, path="$"):
    kind = schema.get("type")
    if kind and (not isinstance(value, TYPES[kind]) or (isinstance(value, bool) and kind != "boolean")):
        raise ValueError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: value not in enum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise ValueError(f"{path}: missing {name}")
        for name, item in value.items():
            if name in properties:
                validate(item, properties[name], f"{path}.{name}")
            elif schema.get("additionalProperties") is False:
                raise ValueError(f"{path}: unexpected {name}")
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", len(value)):
            raise ValueError(f"{path}: too many items")
        for index, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{path}[{index}]")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def generate(prompt, cache_key, *, schema=None, system=None, model=None, config=None):
    config = config or load_config()
    model = model or config["model"]
    digest = config["model_digests"][model]
    key = hashlib.sha256(json.dumps([cache_key, prompt, digest], ensure_ascii=False).encode()).hexdigest()
    options = {name: config[name] for name in ("temperature", "seed", "num_ctx", "num_predict")}
    params = json.loads(json.dumps({"schema": schema, "system": system, "options": options, "think": False}))
    path = ROOT / config["cache_dir"] / f"{key}.json"
    if path.exists():
        record = json.loads(path.read_text("utf-8"))
        if record["params"] == params:
            return {**record, "cached": True}
    found = live_digest(config, model)
    if found != digest:
        raise RuntimeError(f"{model} digest {found[:12]} differs from config {digest[:12]}")
    body = {"model": model, "prompt": prompt, "stream": False, "think": False, "options": options,
            "truncate": False, "shift": False}
    if schema is not None:
        body["format"] = schema
    if system is not None:
        body["system"] = system
    reply = post_generate(config, body)
    record = {"key": key, "model": model, "model_digest": digest, "params": params, "response": reply["response"],
              "done_reason": reply.get("done_reason"), "metrics": {name: reply.get(name, 0) for name in METRICS},
              "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    write_json(path, record)
    return {**record, "cached": False}


def completed(record):
    if record["done_reason"] == "length":
        raise ValueError(f"output truncated at num_predict, cache key {record['key']}")
    return record["response"]


def parse_json(record, schema):
    value = json.loads(completed(record))
    validate(value, schema)
    return value


def generate_json(prompt, schema, cache_key, *, system=None, model=None, config=None):
    check_schema(schema)
    record = generate(prompt, cache_key, schema=schema, system=system, model=model, config=config)
    return parse_json(record, schema)


def generate_text(prompt, cache_key, *, system=None, model=None, config=None):
    answer = completed(generate(prompt, cache_key, system=system, model=model, config=config))
    _, closing, after = answer.rpartition("</think>")
    return after.strip() if closing else answer
