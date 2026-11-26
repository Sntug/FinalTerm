import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import numpy as np
from scipy.sparse.csgraph import dijkstra

from .__main__ import write_csv
from .load import ROOT, build, content_hash, read_snapshot

CONFIG = ROOT / "config/trend_sna.json"
CHUNK = 500


def r6(x):
    return round(float(x), 6)


def ordered_graph(g, label, edge_type, weight="weight"):
    h = nx.Graph()
    h.add_nodes_from(sorted(n for n, d in g.nodes(data=True) if d["label"] == label))
    h.add_weighted_edges_from(sorted(
        (min(u, v), max(u, v), d[weight]) for u, v, d in g.edges(data=True) if d["type"] == edge_type))
    return h


def coauthor_graph(g, weight="weight"):
    return ordered_graph(g, "Author", "COAUTHORED_WITH", weight)


def components(c):
    return sorted(nx.connected_components(c), key=lambda s: (-len(s), min(s)))


def numbered(c):
    ids = sorted(c)
    index = {n: i for i, n in enumerate(ids)}
    h = nx.Graph()
    h.add_nodes_from(range(len(ids)))
    h.add_weighted_edges_from(sorted(
        (min(index[u], index[v]), max(index[u], index[v]), d.get("weight", 1)) for u, v, d in c.edges(data=True)))
    return h, ids


def pair_histogram(c):
    nodes = sorted(c)
    counts = np.zeros(len(nodes), dtype=np.int64)
    if len(nodes) > 1:
        matrix = nx.to_scipy_sparse_array(c, nodelist=nodes, weight=None, format="csr")
        matrix.indices, matrix.indptr = matrix.indices.astype(np.int32), matrix.indptr.astype(np.int32)
        for i in range(0, len(nodes), CHUNK):
            d = dijkstra(matrix, directed=False, unweighted=True, indices=np.arange(i, min(i + CHUNK, len(nodes))))
            counts += np.bincount(d[np.isfinite(d)].astype(np.int64), minlength=len(nodes))
    return Counter({h: int(counts[h]) // 2 for h in range(1, len(nodes)) if counts[h]})


def mean_distance(histogram):
    pairs = sum(histogram.values())
    return sum(h * n for h, n in histogram.items()) / pairs if pairs else None


def rounded(x):
    return None if x is None else r6(x)


def distances(c):
    comps = components(c)
    lcc, total = Counter(), Counter()
    for i, nodes in enumerate(comps):
        h = pair_histogram(c.subgraph(nodes))
        total += h
        if i == 0:
            lcc = h
    n = c.number_of_nodes()
    all_pairs = n * (n - 1) // 2
    reachable = sum(total.values())
    return {
        "l_lcc": rounded(mean_distance(lcc)),
        "l_reachable": rounded(mean_distance(total)),
        "reachable_share": r6(reachable / all_pairs) if all_pairs else 0.0,
        "reachable_pairs": reachable,
        "total_pairs": all_pairs,
        "lcc_diameter": max(lcc, default=0),
        "histogram_lcc": {str(h): lcc[h] for h in sorted(lcc)},
        "histogram_reachable": {str(h): total[h] for h in sorted(total)},
    }


def communities(c, seed, resolution):
    comps = components(c)
    lcc, ids = numbered(c.subgraph(comps[0]))
    found = nx.community.louvain_communities(lcc, weight="weight", resolution=resolution, seed=seed)
    q = nx.community.modularity(lcc, found, weight="weight", resolution=resolution)
    member = {}
    for prefix, groups in (("L", [{ids[i] for i in s} for s in found]), ("C", [s for s in comps[1:] if len(s) > 1])):
        for number, group in enumerate(sorted(groups, key=lambda s: (-len(s), min(s))), 1):
            member.update({a: f"{prefix}{number:03d}" for a in group})
    return member, q


def pagerank(c, alpha):
    h, ids = numbered(c)
    scores = nx.pagerank(h, alpha=alpha, weight="weight", tol=1e-12, max_iter=1000)
    return {ids[i]: v for i, v in scores.items()}


def by_score(scores):
    return sorted(scores, key=lambda n: (-round(scores[n], 10), n))


def groups_of(member):
    groups = defaultdict(list)
    for a in sorted(member):
        groups[member[a]].append(a)
    return dict(sorted(groups.items()))


def core_authors(c, member, alpha):
    core, internal = {}, {}
    for cid, authors in groups_of(member).items():
        scores = pagerank(c.subgraph(authors), alpha)
        internal.update(scores)
        core[cid] = by_score(scores)[0]
    return core, internal


def core_numbers(c):
    return nx.core_number(c)


def paper_authors(g):
    teams = defaultdict(set)
    for a, p, d in g.edges(data=True):
        if d["type"] == "AUTHORED":
            teams[p].add(a)
    return teams


def edition(paper):
    return f"{paper['conference']}{paper['conference_year']}"


def group_ranking(g, member, core, periods):
    papers, active = defaultdict(set), defaultdict(set)
    found = {edition(d) for _, d in g.nodes(data=True) if d["label"] == "Paper"}
    if found - set(periods):
        raise ValueError(f"Snapshot has editions missing from the config periods: {sorted(found - set(periods))}")
    for p, team in paper_authors(g).items():
        period = edition(g.nodes[p])
        for a in team:
            if a in member:
                papers[period, member[a]].add(p)
                active[period, member[a]].add(a)
    keys = sorted(papers, key=lambda k: (k[0], -len(papers[k]), -len(active[k]), k[1]))
    return [[period, cid, len(papers[period, cid]), len(active[period, cid]), core[cid]] for period, cid in keys]


def reference_networks(lcc, n, swaps_per_edge, seed):
    base, ids = numbered(lcc)
    runs = []
    for i in range(n):
        h = base.copy()
        swaps = nx.connected_double_edge_swap(h, nswap=swaps_per_edge * h.number_of_edges(), seed=seed + i)
        runs.append((nx.relabel_nodes(h, dict(enumerate(ids))), swaps))
    return runs


def conclusion(sigma, path_ratio, reachable_share, lcc_share, max_path_ratio, min_reachable_share):
    in_lcc = sigma is not None and sigma > 1 and path_ratio <= max_path_ratio
    whole = in_lcc and reachable_share >= min_reachable_share
    verdict = {True: "small_world_signs", False: "insufficient_evidence"}
    words = {True: "có dấu hiệu thế giới nhỏ", False: "chưa đủ bằng chứng về thế giới nhỏ"}
    sigma_text = "không xác định" if sigma is None else f"{sigma:.2f}"
    ratio_text = "không xác định" if path_ratio is None else f"{path_ratio:.2f}"
    return {
        "lcc": verdict[in_lcc],
        "whole_network": verdict[whole],
        "rule": f"LCC: sigma > 1 và L/L_rand <= {max_path_ratio}; toàn mạng: thêm tỷ lệ cặp liên thông >= {min_reachable_share}",
        "text": (f"Trong LCC ({lcc_share:.1%} số tác giả): {words[in_lcc]} (sigma = {sigma_text}, L/L_rand = {ratio_text}). "
                 f"Toàn mạng: {words[whole]} (chỉ {reachable_share:.1%} số cặp tác giả có đường đi)."),
    }


def small_world(c, dist, cfg):
    comps = components(c)
    lcc = c.subgraph(comps[0])
    clustering = nx.average_clustering(lcc)
    runs = [{"l": r6(mean_distance(pair_histogram(h))), "c": r6(nx.average_clustering(h)), "successful_swaps": swaps}
            for h, swaps in reference_networks(lcc, cfg["reference_networks"], cfg["swaps_per_edge"], cfg["seed"])]
    l_rand = sum(r["l"] for r in runs) / len(runs)
    c_rand = sum(r["c"] for r in runs) / len(runs)
    path_ratio = dist["l_lcc"] / l_rand if l_rand else None
    sigma = (clustering / c_rand) / path_ratio if c_rand and path_ratio else None
    share = len(comps[0]) / c.number_of_nodes()
    return {
        "scope": "largest_component",
        "method": "connected degree-preserving double edge swap, unweighted",
        "networks": len(runs),
        "attempted_swaps_per_network": cfg["swaps_per_edge"] * lcc.number_of_edges(),
        "clustering_lcc": r6(clustering),
        "l_rand": {"mean": r6(l_rand), "min": min(r["l"] for r in runs), "max": max(r["l"] for r in runs)},
        "c_rand": {"mean": r6(c_rand), "min": min(r["c"] for r in runs), "max": max(r["c"] for r in runs)},
        "path_ratio": rounded(path_ratio),
        "sigma": rounded(sigma),
        "runs": runs,
        "conclusion": conclusion(sigma, path_ratio, dist["reachable_share"], share, **cfg["small_world"]),
    }


def ranked_table(g, h, label_keys, alpha, papers):
    scores = pagerank(h, alpha)
    degree, strength = dict(h.degree()), dict(h.degree(weight="weight"))
    return [[n, g.nodes[n]["name"], *[g.nodes[n].get(k, "") for k in label_keys], f"{scores[n]:.10f}", rank,
             degree[n], strength[n], len(papers.get(n, ()))] for rank, n in enumerate(by_score(scores), 1)]


def institution_papers(g):
    papers = defaultdict(set)
    for _, i, d in g.edges(data=True):
        if d["type"] == "AFFILIATED_WITH":
            papers[i] |= set(d["paper_ids"])
    return papers


def coverage(g):
    authored = set(paper_authors(g))
    affiliated = set().union(*institution_papers(g).values())
    rows = defaultdict(Counter)
    for p, d in g.nodes(data=True):
        if d["label"] == "Paper":
            row = rows[edition(d)]
            row["papers"] += 1
            row["with_resolved_author"] += p in authored
            row["with_affiliation"] += p in affiliated
    return {period: dict(rows[period]) for period in sorted(rows)}


def cites(g):
    pairs = [(u, v) for u, v, d in g.edges(data=True) if d["type"] == "CITES"]
    n = sum(1 for _, d in g.nodes(data=True) if d["label"] == "Paper")
    return {"edges": len(pairs), "papers": n,
            "share_citing_inside": r6(len({u for u, _ in pairs}) / n),
            "share_cited_inside": r6(len({v for _, v in pairs}) / n)}


def analyze(g, cfg):
    alpha = cfg["pagerank_alpha"]
    c = coauthor_graph(g, cfg["weight"])
    inst = ordered_graph(g, "Institution", "COLLABORATED_WITH", cfg["weight"])
    comps = components(c)
    member, q = communities(c, cfg["seed"], cfg["louvain_resolution"])
    core, internal = core_authors(c, member, alpha)
    numbers = core_numbers(c)
    k_max = max(numbers.values())
    main = sorted(a for a in c if numbers[a] == k_max)
    teams = paper_authors(g)
    papers_of = defaultdict(set)
    for p, team in teams.items():
        for a in team:
            papers_of[a].add(p)
    ranking = group_ranking(g, member, core, cfg["periods"])
    sizes = {cid: len(authors) for cid, authors in groups_of(member).items()}
    lcc_sizes = [s for cid, s in sizes.items() if cid.startswith("L")]
    small_sizes = [s for cid, s in sizes.items() if cid.startswith("C")]
    dist = distances(c)
    tables = {
        "communities.csv": (["author_id", "community_id"], [[a, member[a]] for a in sorted(member)]),
        "pagerank_author.csv": (["author_id", "name", "pagerank", "rank", "degree", "strength", "n_papers"],
                                ranked_table(g, c, (), alpha, papers_of)),
        "pagerank_institution.csv": (["institution_id", "name", "country_code", "pagerank", "rank", "degree", "strength", "n_papers"],
                                     ranked_table(g, inst, ("country_code",), alpha, institution_papers(g))),
        "kcore.csv": (["author_id", "name", "core_number", "in_main_core", "community_id", "community_pagerank", "is_community_core"],
                      [[a, g.nodes[a]["name"], numbers[a], int(numbers[a] == k_max), member.get(a, ""),
                        f"{internal[a]:.10f}" if a in internal else "", int(core.get(member.get(a)) == a)]
                       for a in sorted(c, key=lambda a: (-numbers[a], member.get(a, ""), a))]),
        "group_ranking.csv": (["venue_edition", "community_id", "n_papers", "n_active_authors", "core_author_id"], ranking),
    }
    present = sorted({r[0] for r in ranking})
    summary = {
        "periods": {"configured": cfg["periods"], "with_data": present,
                    "without_data": [p for p in cfg["periods"] if p not in present]},
        "coauthor": {"nodes": c.number_of_nodes(), "edges": c.number_of_edges(), "components": len(comps),
                     "isolated_authors": sum(1 for s in comps if len(s) == 1), "lcc_nodes": len(comps[0]),
                     "lcc_edges": c.subgraph(comps[0]).number_of_edges(), "lcc_share": r6(len(comps[0]) / c.number_of_nodes()),
                     "clustering_all_nodes": r6(nx.average_clustering(c))},
        "distances": dist,
        "small_world": small_world(c, dist, cfg),
        "louvain": {"scope": "largest_component", "seed": cfg["seed"], "resolution": cfg["louvain_resolution"],
                    "modularity": r6(q), "communities": len(lcc_sizes), "sizes": lcc_sizes},
        "small_components": {"groups": len(small_sizes), "authors": sum(small_sizes), "sizes": small_sizes},
        "kcore": {"k_max": k_max, "main_core_size": len(main), "main_core_authors": main},
        "pagerank": {"alpha": alpha, "weight": cfg["weight"],
                     "author_scope": "all authors, including isolated",
                     "institution_scope": "all institutions, including isolated",
                     "institution_nodes": inst.number_of_nodes(), "institution_edges": inst.number_of_edges(),
                     "institution_isolated": nx.number_of_isolates(inst)},
        "coverage": coverage(g),
        "cites": cites(g),
    }
    return tables, summary


def load_snapshot(path):
    project_id = json.loads((path / "snapshot_manifest.json").read_text(encoding="utf-8"))["project_id"]
    manifest, nodes, rels = read_snapshot(path, project_id)
    info = {"path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix(),
            "project_id": project_id, "snapshot_id": manifest["snapshot_id"], "content_hash": content_hash(nodes, rels)}
    return build(nodes, rels), info


def run(cfg, out):
    g, info = load_snapshot(ROOT / cfg["snapshot"])
    tables, summary = analyze(g, cfg)
    out = Path(out)
    for name, (header, rows) in tables.items():
        write_csv(out / name, header, rows)
    summary = {"snapshot": info, "config": cfg, "networkx": nx.__version__, **summary}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--snapshot")
    ap.add_argument("--out")
    a = ap.parse_args()
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    if a.snapshot:
        cfg["snapshot"] = a.snapshot
    s = run(cfg, a.out or ROOT / cfg["out"])
    print(json.dumps({"louvain": {k: s["louvain"][k] for k in ("modularity", "communities")},
                      "distances": {k: s["distances"][k] for k in ("l_lcc", "l_reachable", "reachable_share")},
                      "conclusion": s["small_world"]["conclusion"]["text"]}, ensure_ascii=False, indent=1))
