import csv
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from src.clean.text import canonical_json, sha256
from src.collect.cache import HTTPCache, source_record
from src.collect.common import json_bytes, now_utc, publish
from src.collect.cvf import CVFHTML, rank_urls

ROOT = Path(__file__).resolve().parents[2]
SEED, TARGET = 20261103, 350
LISTING_URL = "https://openaccess.thecvf.com/ICCV2025?day=all"
RAW_DIR = "data/raw/iccv2025"
LOCK = "config/b_iccv2025_350_selection.json"
REGISTRY = "data/processed/iccv2025/input_registry.csv"
FIELDS = ["paper_id", "cvf_url", "owner", "conference", "conference_year", "doi", "source_record_id"]
DETAIL = re.compile(r"/content/ICCV2025/html/[^/]+_paper\.html")


def canonical(url):
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or parts.netloc != "openaccess.thecvf.com" or parts.query or not DETAIL.fullmatch(unquote(parts.path)):
        raise ValueError(url)
    return "https://openaccess.thecvf.com" + parts.path


def paper_id(url):
    return "cvf:ICCV2025:" + unquote(urlsplit(url).path.split("/")[-1]).removesuffix("_paper.html")


def classify(body):
    links = CVFHTML(body.decode("utf-8-sig")).links
    seen, excluded = set(), []
    for link in links:
        url = urljoin("https://openaccess.thecvf.com/", link)
        if not urlsplit(url).path.startswith("/content/ICCV2025/html/"):
            continue
        try:
            c = canonical(url)
        except ValueError:
            excluded.append({"url": url, "reason": "non_paper_detail_url"})
            continue
        if c in seen:
            excluded.append({"url": c, "reason": "duplicate_canonical_url"})
        seen.add(c)
    return len(links), seen, excluded


def listing(root, offline):
    cache = HTTPCache(root, RAW_DIR, offline=offline, delay=1.0)
    body, meta = cache.get(LISTING_URL)
    return body, meta, cache.network_requests


def prepare(root=ROOT, offline=False):
    root = Path(root).resolve()
    lock_path = root / LOCK
    if lock_path.exists():
        return json.loads(lock_path.read_text("utf-8"))
    body, meta, _ = listing(root, offline)
    rec = source_record(meta, None, "listing")
    total_links, urls, excluded = classify(body)
    ranked = rank_urls(sorted(urls), SEED)
    assert len(ranked) >= TARGET
    papers = [{"paper_id": paper_id(u), "cvf_url": u, "selection_rank": i, "ranking_position": i, "source_record_id": ""}
              for i, u in enumerate(ranked[:TARGET], 1)]
    stream = io.StringIO(newline="")
    w = csv.DictWriter(stream, FIELDS, lineterminator="\n")
    w.writeheader()
    for p in papers:
        w.writerow({**{k: p[k] for k in ("paper_id", "cvf_url", "source_record_id")}, "owner": "B", "conference": "ICCV", "conference_year": 2025, "doi": ""})
    registry = stream.getvalue().encode("utf-8-sig")
    lock = {"owner": "B", "conference": "ICCV", "conference_year": 2025, "seed": SEED, "target_count": TARGET,
            "locked_at": now_utc(),
            "selection_algorithm": "pure rule: sha256(seed + newline + canonical_url) ascending, then URL; no preserved pilot",
            "candidate_count": len(ranked), "candidate_ranking_sha256": sha256(canonical_json(ranked).encode()),
            "listing_source_record_id": rec["source_record_id"], "listing_content_sha256": meta["content_sha256"],
            "listing_raw_path": meta["raw_path"], "registry_input": REGISTRY, "registry_sha256": sha256(registry),
            "source_snapshot_id": "selection:" + sha256(canonical_json(papers).encode()),
            "listing_total_links": total_links, "listing_main_links": len(urls) + len(excluded),
            "excluded_candidates": excluded, "papers": papers}
    publish({root / REGISTRY: registry, lock_path: json_bytes(lock)})
    return lock


if __name__ == "__main__":
    lock = prepare()
    print(json.dumps({k: lock[k] for k in ("candidate_count", "registry_sha256", "listing_total_links", "listing_main_links")}
                     | {"excluded": len(lock["excluded_candidates"]), "first3": [p["paper_id"] for p in lock["papers"][:3]]}, ensure_ascii=False), file=sys.stdout)
