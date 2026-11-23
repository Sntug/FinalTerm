import csv, glob, hashlib, json
from pathlib import Path

from src.collect.cvf import parse_listing, rank_urls

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/b_iccv2023"
SEED, TOP, EDITION = 20261103, 350, "ICCV2023"


def write(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    raw = ROOT / "data/raw/iccv2023"
    html = (raw / "catalog/ICCV2023_all_papers.html").read_bytes()
    listing = set(parse_listing(html, "ICCV", 2023))
    catalog = {p["cvf_url"] for p in json.loads((raw / "catalog/ICCV2023_catalog.json").read_text("utf-8"))}
    ranked = rank_urls(list(listing), SEED)
    rule = ranked[:TOP]
    rank = {u: i + 1 for i, u in enumerate(ranked)}
    with (ROOT / "data/processed/iccv2023/input_registry.csv").open(encoding="utf-8") as f:
        actual = [r["cvf_url"] for r in csv.DictReader(f)]
    pilot = json.loads((raw / "pilot_papers.json").read_text("utf-8"))
    pilot_urls = {p["cvf_url"] for p in pilot}
    excluded = {e["paper_id"] for e in json.loads((ROOT / "config/b_iccv2023_excluded.json").read_text("utf-8"))}
    pid_of = lambda u: "cvf:ICCV2023:" + u.rsplit("/", 1)[1][:-len("_paper.html")]
    excluded_urls = {u for u in listing if pid_of(u) in excluded}

    R, A = set(rule), set(actual)
    assert len(rule) == len(R) == TOP and len(actual) == len(A) == TOP

    def reason(u):
        if u in R and u in A:
            return "rule_match"
        if u in A:
            return "pilot_preserved" if u in pilot_urls else "excluded_replacement"
        return "excluded_replacement" if u in excluded_urls else "replaced_by_pilot"

    rows = [(pid_of(u), u, u in R, u in A, rank.get(u, ""), reason(u)) for u in sorted(R | A, key=lambda u: rank.get(u, 10**9))]
    write(OUT / "selection_diff.csv", ["paper_id", "cvf_url", "in_rule_top350", "in_actual_sample", "rule_rank", "reason"], rows)

    overlap = len(R & A)
    only_rule, only_actual = len(R - A), len(A - R)
    assert overlap + only_rule == TOP and overlap + only_actual == TOP and len(rows) == overlap + only_rule + only_actual
    pilot_out = len(pilot_urls - R)
    excl_in_rule = len(excluded_urls & R)
    assert sum(r[5] == "pilot_preserved" for r in rows) == len((A - R) & pilot_urls)

    manifest = json.loads((ROOT / "data/processed/iccv2023/full/snapshot_manifest.json").read_text("utf-8"))
    papers_path = next(f["path"] for f in manifest["files"] if f["path"].endswith("papers.jsonl"))
    papers = [json.loads(l) for l in (ROOT / papers_path).open(encoding="utf-8")]
    assert len(papers) == TOP
    abstracts = sum(bool((p.get("abstract") or "").strip()) for p in papers)
    matched = sum(p.get("openalex_status") == "matched" for p in papers)
    follows = overlap == TOP

    def row(check, value, threshold, ok, note):
        return (EDITION, check, value, threshold, str(ok).lower(), note)

    lst_ok = listing == catalog
    checks = [
        row("listing_source", hashlib.sha256(html).hexdigest(), "main track only", lst_ok,
            f"cached https://openaccess.thecvf.com/ICCV2023?day=all; parse_listing main-track /content/ICCV2023/html/ == catalog json: {lst_ok} (only_listing={len(listing - catalog)}, only_catalog={len(catalog - listing)})"),
        row("candidate_count", len(listing), ">=350", len(listing) >= TOP, "distinct canonical main-track URLs after dedupe"),
        row("rule_top350_overlap", overlap, TOP, overlap == TOP, f"actual-only={only_actual}, rule-only={only_rule}"),
        row("pilot_not_in_rule_top350", pilot_out, 0, pilot_out == 0, "pilot papers (30) kept regardless of SHA rank; pilot was a 34-record web-search pool + random.sample, not rule-based"),
        row("excluded_and_replaced", excl_in_rule, 0, excl_in_rule == 0, f"papers in rule top350 removed via config/b_iccv2023_excluded.json ({len(excluded)} excluded; {len(excluded_urls & pilot_urls)} of them pilot) and replaced; rule says do not replace"),
        row("sample_follows_rule", str(follows).lower(), "true", follows, "actual registry set == pure SHA-256 rule top350"),
        row("abstract_coverage", f"{abstracts}/{TOP}", f"{TOP}/{TOP} or reported", abstracts == TOP, "non-empty abstract in full snapshot papers.jsonl"),
        row("openalex_matched", f"{matched}/{TOP}", "reported", matched == TOP, "openalex_status == matched in full snapshot papers.jsonl"),
    ]
    write(OUT / "comparability.csv", ["venue_edition", "check", "value", "threshold", "pass", "note"], checks)
    print(f"listing={len(listing)} catalog_equal={lst_ok} overlap={overlap} only_rule={only_rule} only_actual={only_actual} pilot_out={pilot_out} excl_in_rule={excl_in_rule} abstracts={abstracts} matched={matched}")


if __name__ == "__main__":
    main()
