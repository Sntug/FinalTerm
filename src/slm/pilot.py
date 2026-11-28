import csv
import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path

from . import client

SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "array", "items": {"type": "string"}, "maxItems": limit}
                   for name, limit in (("tasks", 5), ("methods", 8), ("datasets", 8))},
    "required": ["tasks", "methods", "datasets"],
    "additionalProperties": False,
}

PROMPT = """Extract candidate entities from the title and abstract of a computer vision paper.
Return JSON with three lists:
- tasks: research problems the paper addresses.
- methods: named techniques, model families or architectures the paper uses or proposes.
- datasets: named datasets or benchmarks the paper evaluates on.
Copy each name exactly as written in the text. Do not invent names. Use an empty list when the text names none.

Example text:
Title: Faster Lane Detection at Night
Abstract: We study lane detection in low light. Our model combines a vision transformer with contrastive learning and is tested on CULane.
Example JSON:
{{"tasks": ["lane detection"], "methods": ["vision transformer", "contrastive learning"], "datasets": ["CULane"]}}

Text:
{text}
JSON:"""


def select(pools, gold, counts, seed):
    chosen = []
    for edition, count in counts.items():
        pool = pools[edition]
        held_out = gold.get(edition, set())
        unknown = held_out - {paper["paper_id"] for paper in pool}
        if unknown or not held_out:
            raise ValueError(f"{edition}: cannot prove gold exclusion, {len(unknown)} gold IDs not in the pool")
        usable = [p for p in pool if p["paper_id"] not in held_out and p.get("title") and p.get("abstract")]
        usable.sort(key=lambda p: hashlib.sha256(f"{seed}\n{p['paper_id']}".encode()).hexdigest())
        chosen += [(edition, paper) for paper in usable[:count]]
    return chosen


def read_papers(processed_dir):
    manifest = json.loads((client.ROOT / processed_dir / "snapshot_manifest.json").read_text("utf-8"))
    entry = next(f for f in manifest["files"] if Path(f["path"]).name == "papers.jsonl")
    raw = (client.ROOT / entry["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise ValueError(f"{entry['path']}: sha256 differs from manifest")
    return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]


def read_gold(path):
    gold = {}
    with open(client.ROOT / path, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            gold.setdefault(row["venue_edition"], set()).add(row["paper_id"])
    return gold


def ollama_rss_gb():
    lines = subprocess.run(["ps", "-axo", "rss=,command="], capture_output=True, text=True, check=True).stdout
    total = 0
    for line in lines.splitlines():
        rss, _, command = line.strip().partition(" ")
        executable = command.split(" -")[0]
        if "ollama" in executable or "llama-server" in executable:
            total += int(rss)
    return total / 1024 ** 2


class PeakMemory:
    def __enter__(self):
        self.peak, self.done = ollama_rss_gb(), threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()
        return self

    def sample(self):
        while not self.done.wait(0.5):
            self.peak = max(self.peak, ollama_rss_gb())

    def __exit__(self, *error):
        self.done.set()
        self.thread.join()


def loaded_gb(config, model):
    for entry in client.request(config, "/api/ps")["models"]:
        if entry["name"] == model:
            return entry["size"] / 1024 ** 3
    return None


def unload(config, models):
    for model in models:
        try:
            client.request(config, "/api/generate", {"model": model, "keep_alive": 0})
        except OSError:
            pass


def summarize(rows, papers_total):
    count = len(rows)
    seconds = sum(r["seconds"] for r in rows) / count
    generation = sum(r["eval_seconds"] for r in rows)
    peak = lambda name: max((r[name] for r in rows if r.get(name) is not None), default=None)
    return {
        "papers": count,
        "valid_json": sum(r["valid"] for r in rows),
        "valid_json_rate": sum(r["valid"] for r in rows) / count,
        "tokens_per_second": round(sum(r["eval_count"] for r in rows) / generation, 2) if generation else None,
        "mean_seconds_per_paper": round(seconds, 2),
        "max_load_seconds": round(max(r["load_seconds"] for r in rows), 2),
        "hours_for_1750_papers": round(seconds * papers_total / 3600, 2),
        "peak_ram_rss_gb": peak("ram_rss_gb"),
        "ollama_loaded_gb": peak("loaded_gb"),
    }


def decide(models, order, max_hours, min_valid):
    for name in order:
        if models[name]["hours_for_1750_papers"] <= max_hours and models[name]["valid_json_rate"] >= min_valid:
            return name
    return None


def run_paper(config, model, edition, paper, previous):
    text = f"Title: {paper['title']}\nAbstract: {paper['abstract']}"
    prompt = PROMPT.format(text=text)
    with PeakMemory() as memory:
        record = client.generate(prompt, text, schema=SCHEMA, model=model, config=config)
    metrics = record["metrics"]
    try:
        output, error = client.parse_json(record, SCHEMA), None
    except ValueError as problem:
        output, error = None, str(problem)
    if record["cached"]:
        old = previous.get((model, paper["paper_id"], record["key"]), {})
        ram = {name: old.get(name) for name in ("ram_rss_gb", "loaded_gb", "load_average")}
    else:
        loaded = loaded_gb(config, model)
        ram = {"ram_rss_gb": round(memory.peak, 2), "loaded_gb": loaded and round(loaded, 2),
               "load_average": round(os.getloadavg()[0], 1)}
    row = {
        "model": model, "venue_edition": edition, "paper_id": paper["paper_id"], "cache_key": record["key"],
        "valid": error is None, "error": error, "output": output,
        "eval_count": metrics["eval_count"], "eval_seconds": metrics["eval_duration"] / 1e9,
        "seconds": (metrics["total_duration"] - metrics["load_duration"]) / 1e9,
        "load_seconds": metrics["load_duration"] / 1e9, **ram,
    }
    return row, record["cached"]


def sysctl(name):
    return subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=True).stdout.strip()


def main():
    config = client.load_config()
    settings = config["pilot"]
    pools = {edition: read_papers(source["processed_dir"]) for edition, source in settings["sources"].items()}
    counts = {edition: source["n"] for edition, source in settings["sources"].items()}
    papers = select(pools, read_gold(settings["gold_set"]), counts, str(config["seed"]))
    output = client.ROOT / settings["output_dir"]
    details = output / "details.jsonl"
    previous = {}
    if details.exists():
        for line in details.read_text("utf-8").splitlines():
            row = json.loads(line)
            previous[(row["model"], row["paper_id"], row["cache_key"])] = row
    order = [config["model"], config["fallback_model"]]
    rows, hits = [], 0
    output.mkdir(parents=True, exist_ok=True)
    for model in order:
        unload(config, order)
        for index, (edition, paper) in enumerate(papers, 1):
            row, cached = run_paper(config, model, edition, paper, previous)
            rows.append(row)
            hits += cached
            print(f"{model} {index}/{len(papers)} cached={cached} valid={row['valid']} {row['seconds']:.1f}s", flush=True)
    unload(config, order)
    details.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), "utf-8")
    models = {}
    for model in order:
        own = [r for r in rows if r["model"] == model]
        models[model] = {"digest": config["model_digests"][model], **summarize(own, settings["papers_total"]),
                         "max_load_average": max((r["load_average"] or 0 for r in own), default=0)}
    chosen = decide(models, order, settings["max_hours_for_all_papers"], settings["min_valid_json_rate"])
    client.write_json(output / "summary.json", {
        "models": models,
        "decision": {"model": chosen, "rule": {name: settings[name] for name in
                     ("papers_total", "max_hours_for_all_papers", "min_valid_json_rate")}},
        "papers": [{"venue_edition": edition, "paper_id": paper["paper_id"]} for edition, paper in papers],
        "gold_set_overlap": 0,
        "prompt_template_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "parameters": {name: config[name] for name in ("temperature", "seed", "num_ctx", "num_predict")} | {"think": False},
        "machine": {"cpu": sysctl("machdep.cpu.brand_string"), "ram_gb": int(sysctl("hw.memsize")) // 1024 ** 3},
        "last_run": {"calls": len(rows), "cache_hits": hits},
    })
    print(json.dumps({"decision": chosen, "cache_hits": f"{hits}/{len(rows)}", "models": models}, indent=2))


if __name__ == "__main__":
    main()
