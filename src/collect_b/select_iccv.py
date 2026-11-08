"""B2: deterministic 350-paper ICCV 2023 selection (locked pilot minus excluded + SHA-256 rank, minus config/b_iccv2023_excluded.json)."""
import csv, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED, TOTAL = "20261103", 350
FIELDS = ["paper_id", "doi", "cvf_url", "conference", "conference_year", "owner", "status"]


def select(root=ROOT):
    pilot = json.loads((root / "data/raw/iccv2023/pilot_papers.json").read_text("utf-8"))
    catalog = json.loads((root / "data/raw/iccv2023/catalog/ICCV2023_catalog.json").read_text("utf-8"))
    urls = {p["cvf_url"] for p in pilot}
    assert len(urls) == len(pilot) == 30
    excl = {e["paper_id"] for e in json.loads((root / "config/b_iccv2023_excluded.json").read_text("utf-8"))}
    pilot = [p for p in pilot if p["paper_id"] not in excl]  # excluded pilot papers are replaced by SHA-ranked ones
    rest = sorted((p for p in catalog if p["cvf_url"] not in urls and p["paper_id"] not in excl),
                  key=lambda p: (hashlib.sha256((SEED + "\n" + p["cvf_url"]).encode()).hexdigest(), p["cvf_url"]))
    chosen = pilot + rest[:TOTAL - len(pilot)]
    assert len({p["paper_id"] for p in chosen}) == len({p["cvf_url"] for p in chosen}) == TOTAL
    return chosen


def write_csv(path, papers):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS, lineterminator="\n"); w.writeheader()
        for p in papers:
            w.writerow({"paper_id": p["paper_id"], "doi": "", "cvf_url": p["cvf_url"], "conference": "ICCV",
                        "conference_year": 2023, "owner": "B", "status": "selected"})


if __name__ == "__main__":
    papers = select()
    write_csv(ROOT / "data/processed/iccv2023/input_registry.csv", papers)
    print(len(papers), "papers written", file=sys.stderr)
