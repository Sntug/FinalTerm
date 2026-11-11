import statistics
from collections import Counter, defaultdict
from itertools import combinations

import networkx as nx

SEED = 42
CASE_TASK = "task:object-detection"
CASE_MIN_PAPERS = 10
CASE_MAX_NODES = 80
CASE_MAX_AUTHORS = 25


def r6(x):
    return round(float(x), 6)


def top(items, key, n=15):
    return sorted(items, key=lambda x: (-key(x), x[0]))[:n]


def nodes_of(g, label):
    return [n for n, d in g.nodes(data=True) if d["label"] == label]


def edges_of(g, typ):
    return [(u, v, d) for u, v, d in g.edges(data=True) if d["type"] == typ]


def summary(values):
    v = sorted(values)
    return {"min": v[0], "max": v[-1], "mean": r6(statistics.mean(v)), "median": r6(statistics.median(v)),
            "p90": v[int(0.9 * (len(v) - 1))]}


def paper_counts(g):
    papers = defaultdict(list)
    for a, p, d in edges_of(g, "AUTHORED"):
        papers[a].append(p)
    return papers


def coauthor(g):
    authors = nodes_of(g, "Author")
    c = nx.Graph()
    c.add_nodes_from(authors)
    for u, v, d in edges_of(g, "COAUTHORED_WITH"):
        c.add_edge(u, v, weight=d["weight"])
    papers = paper_counts(g)
    deg, stren = dict(c.degree()), dict(c.degree(weight="weight"))
    isolated = sum(1 for a in authors if deg[a] == 0)
    comps = sorted(nx.connected_components(c), key=lambda s: (-len(s), min(s)))
    lcc = nx.Graph()
    lcc.add_nodes_from(sorted(comps[0]))
    lcc.add_edges_from((u, v, {"weight": w}) for u, v, w in sorted((min(u, v), max(u, v), d["weight"]) for u, v, d in c.edges(data=True) if u in comps[0]))
    comms = sorted(nx.community.louvain_communities(lcc, weight="weight", seed=SEED), key=lambda s: (-len(s), min(s)))
    node_comm = {n: i for i, s in enumerate(comms) for n in s}

    def row(a):
        mix = Counter(g.nodes[p]["conference"] for p in papers.get(a, []))
        return [a, g.nodes[a]["name"], deg[a], stren[a], len(papers.get(a, [])), "; ".join(f"{k}:{mix[k]}" for k in sorted(mix))]

    rows = [row(a) for a in authors]
    hdr = ["author_id", "name", "degree", "strength", "n_papers", "conference_mix"]
    by_deg = sorted(rows, key=lambda r: (-r[2], -r[3], r[0]))[:15]
    by_str = sorted(rows, key=lambda r: (-r[3], -r[2], r[0]))[:15]
    sizes = [len(s) for s in comms]
    metrics = {
        "nodes": c.number_of_nodes(), "edges": c.number_of_edges(), "isolated_authors": isolated,
        "components": len(comps), "components_nontrivial": sum(1 for s in comps if len(s) > 1),
        "largest_component_size": len(comps[0]), "largest_component_share": r6(len(comps[0]) / c.number_of_nodes()),
        "density": r6(nx.density(c)), "avg_clustering_all_nodes": r6(nx.average_clustering(c)),
        "avg_clustering_lcc": r6(nx.average_clustering(lcc)), "lcc_edges": lcc.number_of_edges(),
        "degree_summary": summary(deg.values()), "strength_summary": summary(stren.values()),
        "degree_distribution": {str(k): v for k, v in sorted(Counter(deg.values()).items())},
        "louvain": {"seed": SEED, "scope": "largest_component", "communities": len(comms),
                    "modularity": r6(nx.community.modularity(lcc, comms, weight="weight")), "top10_sizes": sizes[:10]},
        "top15_by_degree": [r[:2] + r[2:5] for r in by_deg], "top15_by_strength": [r[:2] + r[2:5] for r in by_str],
    }
    tables = {"coauthor_top_degree": (hdr, by_deg), "coauthor_top_strength": (hdr, by_str),
              "coauthor_louvain_community_sizes": (["community", "size"], [[i, s] for i, s in enumerate(sizes)])}
    return metrics, tables, {"graph": c, "lcc": lcc, "node_comm": node_comm, "deg": deg, "top_strength": [r[0] for r in by_str]}


def citation(g):
    papers = nodes_of(g, "Paper")
    d = nx.DiGraph()
    d.add_nodes_from(papers)
    cites = edges_of(g, "CITES")
    for u, v, _ in cites:
        d.add_edge(u, v)
    conf = lambda p: g.nodes[p]["conference"]
    pair = Counter((conf(u), conf(v)) for u, v, _ in cites)
    pr = nx.pagerank(d, alpha=0.85)
    indeg = dict(d.in_degree())
    prow = lambda p: [p, g.nodes[p]["name"], conf(p), indeg[p], d.out_degree(p), r6(pr[p])]
    hdr = ["paper_id", "title", "conference", "in_degree", "out_degree", "pagerank"]
    by_in = sorted([prow(p) for p in papers], key=lambda r: (-r[3], r[0]))[:15]
    by_pr = sorted([prow(p) for p in papers], key=lambda r: (-pr[r[0]], r[0]))[:15]
    wcc = sorted(nx.weakly_connected_components(d), key=lambda s: (-len(s), min(s)))
    n = len(papers)
    metrics = {
        "cites_edges": len(cites), "papers": n,
        "cvpr_to_iccv": pair[("CVPR", "ICCV")], "iccv_to_cvpr": pair[("ICCV", "CVPR")],
        "within_cvpr": pair[("CVPR", "CVPR")], "within_iccv": pair[("ICCV", "ICCV")],
        "weak_components": len(wcc), "weak_components_nontrivial": sum(1 for s in wcc if len(s) > 1),
        "largest_weak_component": len(wcc[0]),
        "share_zero_in": r6(sum(1 for p in papers if indeg[p] == 0) / n),
        "share_zero_out": r6(sum(1 for p in papers if d.out_degree(p) == 0) / n),
        "share_zero_in_and_out": r6(sum(1 for p in papers if indeg[p] == 0 and d.out_degree(p) == 0) / n),
        "pagerank_alpha": 0.85,
        "top15_in_degree": [r[:4] for r in by_in], "top15_pagerank": [[r[0], r[1], r[2], r[5]] for r in by_pr],
    }
    tables = {"citation_top_indegree": (hdr, by_in), "citation_top_pagerank": (hdr, by_pr)}
    return metrics, tables, {"digraph": d, "pr": pr, "top_pr": [r[0] for r in by_pr]}


def paper_countries(g):
    inst_country = {u: v for u, v, _ in edges_of(g, "BASED_IN")}
    authors_of = defaultdict(set)
    for a, p, _ in edges_of(g, "AUTHORED"):
        authors_of[p].add(a)
    aff = defaultdict(list)
    for a, i, d in edges_of(g, "AFFILIATED_WITH"):
        aff[a].append((i, set(d["paper_ids"])))
    out = {}
    for p in nodes_of(g, "Paper"):
        out[p] = sorted({inst_country[i] for a in authors_of[p] for i, pids in aff[a] if p in pids and i in inst_country})
    return out, inst_country


def institutions(g, pc, inst_country):
    insts = nodes_of(g, "Institution")
    h = nx.Graph()
    h.add_nodes_from(insts)
    for u, v, d in edges_of(g, "COLLABORATED_WITH"):
        h.add_edge(u, v, weight=d["weight"])
    deg, stren = dict(h.degree()), dict(h.degree(weight="weight"))
    name = lambda i: g.nodes[i]["name"]
    rows = [[i, name(i), inst_country.get(i, ""), deg[i], stren[i]] for i in insts]
    hdr = ["institution_id", "name", "country", "degree", "strength"]
    by_str = sorted(rows, key=lambda r: (-r[4], -r[3], r[0]))[:15]
    by_deg = sorted(rows, key=lambda r: (-r[3], -r[4], r[0]))[:15]
    pairs = []
    for u, v, d in h.edges(data=True):
        a, b = sorted((u, v))
        pairs.append([a, name(a), b, name(b), d["weight"]])
    pairs.sort(key=lambda r: (-r[4], r[0], r[2]))
    n_inst, n_paper = Counter(inst_country.values()), Counter(c for cs in pc.values() for c in cs)
    countries = sorted(nodes_of(g, "Country"))
    crow = sorted(([c, n_inst[c], n_paper[c]] for c in countries), key=lambda r: (-r[2], -r[1], r[0]))
    cpair = Counter()
    for u, v, d in edges_of(g, "COLLABORATED_WITH"):
        if u in inst_country and v in inst_country:
            cpair[tuple(sorted((inst_country[u], inst_country[v])))] += d["weight"]
    cp_rows = sorted(([a, b, w] for (a, b), w in cpair.items()), key=lambda r: (-r[2], r[0], r[1]))
    cross = [r for r in cp_rows if r[0] != r[1]]
    metrics = {
        "nodes": h.number_of_nodes(), "edges": h.number_of_edges(), "isolated_institutions": sum(1 for i in insts if deg[i] == 0),
        "top15_by_strength": [r[:1] + r[1:2] + r[3:] for r in by_str], "top15_by_degree": [r[:2] + r[3:] for r in by_deg],
        "top15_pairs": [[r[1], r[3], r[4]] for r in pairs[:15]],
        "countries": len(countries), "papers_with_country": sum(1 for cs in pc.values() if cs),
        "top_countries_by_papers": crow[:15], "top_countries_by_institutions": sorted(crow, key=lambda r: (-r[1], r[0]))[:15],
        "country_pairs_collab_domestic_weight": sum(r[2] for r in cp_rows if r[0] == r[1]),
        "country_pairs_collab_international_weight": sum(r[2] for r in cross),
        "country_pairs_international_distinct": len(cross), "top15_country_pairs_international": cross[:15],
    }
    tables = {"institution_top_strength": (hdr, by_str), "institution_top_degree": (hdr, by_deg),
              "institution_top_pairs": (["inst_1", "name_1", "inst_2", "name_2", "weight"], pairs[:15]),
              "country_summary": (["country", "n_institutions", "n_papers"], crow),
              "country_pair_collaboration": (["country_1", "country_2", "weight"], cp_rows)}
    return metrics, tables, {"graph": h, "top_strength": [r[0] for r in sorted(rows, key=lambda r: (-r[4], r[0]))[:30]]}


def nlp(g):
    out, tables, per_paper = {}, {}, defaultdict(lambda: defaultdict(set))
    for typ, label, key in (("STUDIES_TASK", "Task", "tasks"), ("USES_METHOD", "Method", "methods"), ("EVALUATED_ON", "Dataset", "datasets")):
        cnt = Counter()
        for p, x, _ in edges_of(g, typ):
            per_paper[p][key].add(x)
            cnt[x] += 1
        rows = sorted(([x, g.nodes[x]["name"], cnt[x]] for x in nodes_of(g, label)), key=lambda r: (-r[2], r[0]))
        out[f"{key}_papers"] = rows
        tables[f"nlp_{key}_papers"] = (["id", "name", "n_papers"], rows)
        out[f"{key}_with_zero_papers"] = sum(1 for r in rows if r[2] == 0)
    co = Counter((t, m) for p in per_paper.values() for t in p["tasks"] for m in p["methods"])
    corows = sorted(([t, g.nodes[t]["name"], m, g.nodes[m]["name"], c] for (t, m), c in co.items()), key=lambda r: (-r[4], r[0], r[2]))
    tables["nlp_task_method_cooccurrence"] = (["task_id", "task", "method_id", "method", "n_papers"], corows)
    out["papers_with_any_nlp_edge"] = len(per_paper)
    out["papers_with_task"] = sum(1 for p in per_paper.values() if p["tasks"])
    out["papers_with_method"] = sum(1 for p in per_paper.values() if p["methods"])
    out["papers_with_dataset"] = sum(1 for p in per_paper.values() if p["datasets"])
    out["top15_task_method_pairs"] = [[r[1], r[3], r[4]] for r in corows[:15]]
    return out, tables


def group_citation(g, pc):
    m = defaultdict(float)
    cites = edges_of(g, "CITES")
    assigned = 0
    for u, v, _ in cites:
        a, b = pc[u], pc[v]
        if not a or not b:
            continue
        assigned += 1
        w = 1.0 / (len(a) * len(b))
        for x in a:
            for y in b:
                m[(x, y)] += w
    rows = sorted(([x, y, r6(w)] for (x, y), w in m.items()), key=lambda r: (-r[2], r[0], r[1]))
    cross = [r for r in rows if r[0] != r[1]]
    metrics = {
        "rule": ("paper country set = countries of Institutions reached by BASED_IN from institutions i such that an author a with "
                 "AUTHORED(a,paper) has AFFILIATED_WITH(a,i) whose paper_ids contains the paper; each CITES edge adds total weight 1 split evenly "
                 "over |src countries| x |dst countries| pairs; edges where either paper has no country are excluded; derived analysis only, no graph edges added"),
        "cites_total": len(cites), "cites_assigned": assigned, "cites_unassigned": len(cites) - assigned,
        "matrix_total_weight": r6(sum(m.values())), "matrix_cells": len(rows),
        "papers_without_country": sum(1 for cs in pc.values() if not cs),
        "domestic_weight": r6(sum(r[2] for r in rows if r[0] == r[1])), "international_weight": r6(sum(r[2] for r in cross)),
        "top15_pairs": rows[:15], "top15_international_pairs": cross[:15],
    }
    return metrics, {"group_citation_country_matrix": (["src_country", "dst_country", "weight"], rows)}, dict(m)


def case_study(g):
    tasks = Counter(t for _, t, _ in edges_of(g, "STUDIES_TASK"))
    chosen, reason = CASE_TASK, f"{CASE_TASK} has {tasks[CASE_TASK]} papers (>= {CASE_MIN_PAPERS})"
    if tasks[CASE_TASK] < CASE_MIN_PAPERS:
        chosen = sorted(tasks, key=lambda t: (-tasks[t], t))[0]
        reason = f"{CASE_TASK} has {tasks[CASE_TASK]} papers (< {CASE_MIN_PAPERS}); fell back to the task with most papers ({tasks[chosen]})"
    print(f"case study task: {chosen} ({reason})")
    study = {p: d for p, t, d in edges_of(g, "STUDIES_TASK") if t == chosen}
    keep = {chosen} | set(study)
    for typ in ("USES_METHOD", "EVALUATED_ON"):
        keep |= {x for p, x, _ in edges_of(g, typ) if p in study}
    papers_of = paper_counts(g)
    cand = Counter(a for a, p, _ in edges_of(g, "AUTHORED") if p in study)
    ranked = sorted(cand, key=lambda a: (-cand[a], a))[:CASE_MAX_AUTHORS]
    aff = defaultdict(list)
    for a, i, d in edges_of(g, "AFFILIATED_WITH"):
        aff[a].append((i, set(d["paper_ids"])))
    insts = lambda a: {i for i, pids in aff[a] if pids & set(study)}
    chosen_authors = []
    for a in ranked:
        extra = ({a} | insts(a)) - keep
        if len(keep) + len(extra) > CASE_MAX_NODES:
            break
        keep |= extra
        chosen_authors.append(a)
    sub = g.subgraph(keep)
    types = {"STUDIES_TASK", "USES_METHOD", "EVALUATED_ON", "CITES", "AUTHORED", "AFFILIATED_WITH"}
    erows = sorted(([k, u, v, d["type"], d["weight"]] for u, v, k, d in sub.edges(keys=True, data=True)
                    if d["type"] in types and (d["type"] != "AUTHORED" or v in study) and (d["type"] != "AFFILIATED_WITH" or d["paper_ids"] and set(d["paper_ids"]) & set(study))), key=lambda r: r[0])
    kept_ids = {r[1] for r in erows} | {r[2] for r in erows}
    nrows = sorted([n, g.nodes[n]["label"], g.nodes[n]["name"]] for n in keep if n in kept_ids or n == chosen)
    cite_rows = sorted([u, g.nodes[u]["name"], v, g.nodes[v]["name"]] for u, v, k, d in sub.edges(keys=True, data=True) if d["type"] == "CITES")
    prows = sorted([p, g.nodes[p]["name"], g.nodes[p]["conference"], "; ".join(d["evidence_ids"])] for p, d in study.items())
    metrics = {"task": chosen, "reason": reason, "papers": len(study), "nodes": len(nrows), "edges": len(erows),
               "authors_kept": len(chosen_authors), "trim_rule": f"keep task, all its papers, their Method/Dataset; add authors by #papers in subset (ties by id) with their subset institutions while nodes <= {CASE_MAX_NODES}",
               "cites_inside": len(cite_rows), "nodes_by_label": dict(sorted(Counter(r[1] for r in nrows).items())),
               "cites_pairs": [[r[1], r[3]] for r in cite_rows]}
    tables = {"nodes": (["id", "label", "name"], nrows), "edges": (["edge_id", "src", "dst", "type", "weight"], erows),
              "papers": (["paper_id", "title", "conference", "studies_task_evidence_ids"], prows),
              "citations_inside": (["src_id", "src_title", "dst_id", "dst_title"], cite_rows)}
    return metrics, tables, {"sub": sub, "nodes": {r[0] for r in nrows}, "edges": erows}
