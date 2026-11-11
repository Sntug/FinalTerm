import argparse
import csv
import json
from pathlib import Path

from . import analyze as A
from . import figures as F
from .load import ROOT, load

OUT = ROOT / "outputs/b6"
QUERIES = ROOT / "queries"
DEMOS = ["b6_case_study", "b6_top_cited", "b6_method_usage", "b6_cross_conference_citations", "b6_country_collaboration"]


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def cypher_demo():
    from neo4j import GraphDatabase
    from src.graph.load_neo4j import credentials
    uri, user, password = credentials()
    out = {}
    with GraphDatabase.driver(uri, auth=(user, password)) as driver, driver.session(database="neo4j") as session:
        for name in DEMOS:
            query = (QUERIES / f"{name}.cypher").read_text(encoding="utf-8").strip().rstrip(";")
            out[name + ".cypher"] = len(list(session.run(query)))
    return out


def run(source="neo4j", out=OUT, figures=True):
    out = Path(out)
    g, loadinfo = load(source)
    cm, ct, cx = A.coauthor(g)
    zm, zt, zx = A.citation(g)
    pc, inst_country = A.paper_countries(g)
    im, it, ix = A.institutions(g, pc, inst_country)
    nm, nt = A.nlp(g)
    gm, gt, _ = A.group_citation(g, pc)
    sm, st, sx = A.case_study(g)
    metrics = {"source": source, "load_check": loadinfo, "coauthor": cm, "citation": zm, "institution": im, "nlp": nm,
               "group_citation": gm, "case_study": sm, "seed": A.SEED}
    metrics["cypher_demo"] = cypher_demo() if source == "neo4j" else "skipped"
    for name, (h, rows) in {**ct, **zt, **it, **nt, **gt}.items():
        write_csv(out / "tables" / f"{name}.csv", h, rows)
    for name, (h, rows) in st.items():
        write_csv(out / "case_study" / f"{name}.csv", h, rows)
    if figures:
        fd = out / "figures"
        fd.mkdir(parents=True, exist_ok=True)
        F.coauthor_degree(cm["degree_distribution"], fd / "a_coauthor_degree_loglog.png")
        F.coauthor_lcc(cx["lcc"], cx["node_comm"], g, fd / "b_coauthor_lcc_communities.png")
        F.citation_pr(zx["digraph"], zx["pr"], zx["top_pr"], g, fd / "c_citation_pagerank.png")
        F.institutions(ix["graph"], ix["top_strength"], g, fd / "d_institution_collaboration_top30.png")
        F.case(sx["sub"], sx["nodes"], sx["edges"], g, sm["task"], fd / "e_case_study.png")
        F.nlp_bars(nm["tasks_papers"], nm["methods_papers"], fd / "f_task_method_counts.png")
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["neo4j", "csv"], default="neo4j")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args()
    run(a.source, a.out, not a.no_figures)
