import json
import sys
import time
from pathlib import Path

from src.collect.cache import HTTPCache, OpenAlexCache, SourceFailure
from src.collect.common import json_bytes, publish
from src.collect.cvf import parse_detail
from src.collect.openalex import collect_work
from .select_iccv2025 import LOCK, RAW_DIR, ROOT

N = 20
OUT = "outputs/b_iccv2025/pilot_summary.json"
CONFIG = {"raw_dir": RAW_DIR, "retries": 2, "openalex_delay_seconds": 1.0, "timeout_seconds": 30, "max_retry_wait_seconds": 30}


def pct(n, d):
    return {"numerator": n, "denominator": d, "percent": round(100 * n / d, 1) if d else None}


def run(root=ROOT, offline=False):
    root = Path(root).resolve()
    lock = json.loads((root / LOCK).read_text("utf-8"))
    http = HTTPCache(root, RAW_DIR, offline=offline, delay=1.0)
    oa = OpenAlexCache(root, CONFIG, offline=offline)
    rows, t0 = [], time.monotonic()
    for item in lock["papers"][:N]:
        row = {"paper_id": item["paper_id"], "selection_rank": item["selection_rank"], "cvf_parse": "ok", "cvf_error": None,
               "abstract_cvf": False, "doi": None, "openalex_status": None, "openalex_error": None, "work_id": None,
               "n_authorships": 0, "n_authorships_with_institution": 0, "has_affiliation": False, "n_references": 0}
        try:
            body, _ = http.get(item["cvf_url"])
            paper = parse_detail(body, item["cvf_url"], "ICCV", 2025)
        except Exception as exc:
            row["cvf_parse"], row["cvf_error"] = "failed", f"{type(exc).__name__}: {exc}"
            rows.append(row)
            continue
        row["abstract_cvf"], row["doi"] = bool(paper["abstract"]), paper["doi"]
        paper.update(paper_id=item["paper_id"], conference="ICCV", conference_year=2025)
        try:
            work, _, audit = collect_work(oa, paper)
            row["openalex_status"], row["work_id"] = audit["status"], audit["work_id"]
            if work:
                auths = work.get("authorships") or []
                row["n_authorships"] = len(auths)
                row["n_authorships_with_institution"] = sum(bool(a.get("institutions")) for a in auths)
                row["has_affiliation"] = row["n_authorships_with_institution"] > 0
                row["n_references"] = len(work.get("referenced_works") or [])
        except (SourceFailure, OSError, RuntimeError, ValueError) as exc:
            row["openalex_status"], row["openalex_error"] = "error", f"{type(exc).__name__}: {exc}"
        rows.append(row)
    total = len(rows)
    parsed = [r for r in rows if r["cvf_parse"] == "ok"]
    matched = [r for r in rows if r["openalex_status"] == "matched"]
    summary = {"conference": "ICCV", "conference_year": 2025, "sample": f"selection_rank 1..{N}", "papers": total,
               "cvf_parse_ok": pct(len(parsed), total),
               "abstract_cvf": pct(sum(r["abstract_cvf"] for r in parsed), total),
               "openalex_status_counts": {s: sum(r["openalex_status"] == s for r in rows) for s in ("matched", "not_found", "needs_review", "error")},
               "openalex_matched": pct(len(matched), total),
               "papers_with_affiliation": pct(sum(r["has_affiliation"] for r in matched), len(matched)),
               "authorships_with_institution": pct(sum(r["n_authorships_with_institution"] for r in matched), sum(r["n_authorships"] for r in matched)),
               "references_nonempty": pct(sum(r["n_references"] > 0 for r in matched), len(matched)),
               "network_requests": {"cvf": http.network_requests, "openalex": oa.network_requests},
               "elapsed_seconds": round(time.monotonic() - t0, 1), "rows": rows}
    publish({root / OUT: json_bytes(summary)})
    return summary


if __name__ == "__main__":
    s = run(offline="--offline" in sys.argv)
    print(json.dumps({k: v for k, v in s.items() if k != "rows"}, ensure_ascii=False, indent=1))
