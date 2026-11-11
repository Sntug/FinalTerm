import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

SEED = 42
DPI = 200
LABEL_COLORS = {"Paper": "#4c78a8", "Author": "#f58518", "Institution": "#54a24b", "Method": "#b279a2", "Dataset": "#e45756", "Task": "#222222", "Country": "#9d755d"}


def short(s, n=28):
    return s if len(s) <= n else s[: n - 1] + "…"


def canonical(sub, directed=False):
    c = nx.DiGraph() if directed else nx.Graph()
    c.add_nodes_from(sorted(sub))
    c.add_edges_from(sorted((u, v, dict(d)) for u, v, d in sub.edges(data=True)))
    return c


def save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def coauthor_degree(dist, path):
    ks = sorted(int(k) for k in dist if int(k) > 0)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.loglog(ks, [dist[str(k)] for k in ks], "o", color="#4c78a8")
    ax.set_xlabel("degree k (distinct coauthors)")
    ax.set_ylabel("number of authors")
    ax.set_title("Coauthor network degree distribution (log-log, degree > 0)")
    ax.grid(True, which="both", alpha=0.3)
    save(fig, path)


def coauthor_lcc(lcc, node_comm, g, path):
    pos = nx.spring_layout(lcc, seed=SEED, weight=None, k=1.5 / max(len(lcc), 1) ** 0.5, iterations=100)
    cmap = plt.get_cmap("tab20")
    fig, ax = plt.subplots(figsize=(12, 10))
    nx.draw_networkx_edges(lcc, pos, ax=ax, alpha=0.25, width=0.5)
    nx.draw_networkx_nodes(lcc, pos, ax=ax, node_size=[12 + 4 * lcc.degree(n) for n in lcc], node_color=[cmap(node_comm[n] % 20) for n in lcc])
    top = sorted(lcc, key=lambda n: (-lcc.degree(n, weight="weight"), n))[:10]
    nx.draw_networkx_labels(lcc, pos, labels={n: g.nodes[n]["name"] for n in top}, ax=ax, font_size=8, font_weight="bold")
    ax.set_title(f"Largest coauthor component ({len(lcc)} authors), colored by Louvain community; top-10 by strength labeled")
    ax.axis("off")
    save(fig, path)


def citation_pr(d, pr, top_pr, g, path):
    keep = set(top_pr[:15])
    for n in list(keep):
        keep |= set(d.predecessors(n)) | set(d.successors(n))
    sub = canonical(d.subgraph(keep), directed=True)
    pos = nx.spring_layout(canonical(sub), seed=SEED, k=1.2 / max(len(sub), 1) ** 0.5, iterations=100)
    colors = ["#e45756" if g.nodes[n]["conference"] == "ICCV" else "#4c78a8" for n in sub]
    fig, ax = plt.subplots(figsize=(13, 10))
    nx.draw_networkx_edges(sub, pos, ax=ax, arrows=True, alpha=0.5, width=0.8, arrowsize=10)
    nx.draw_networkx_nodes(sub, pos, ax=ax, node_color=colors, node_size=[60 + 40000 * pr[n] for n in sub])
    nx.draw_networkx_labels(sub, pos, labels={n: short(g.nodes[n]["name"], 32) for n in top_pr[:15] if n in sub}, ax=ax, font_size=7)
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color="#4c78a8", label="CVPR"), Line2D([], [], marker="o", ls="", color="#e45756", label="ICCV")], loc="lower left")
    ax.set_title("Citation network: top-15 PageRank papers and their neighbours (arrow = cites)")
    ax.axis("off")
    save(fig, path)


def institutions(h, top, g, path):
    sub = canonical(h.subgraph(top))
    pos = nx.spring_layout(sub, seed=SEED, weight="weight", k=1.5 / max(len(sub), 1) ** 0.5, iterations=100)
    fig, ax = plt.subplots(figsize=(13, 10))
    nx.draw_networkx_edges(sub, pos, ax=ax, alpha=0.4, width=[0.5 + 1.5 * d["weight"] for _, _, d in sub.edges(data=True)])
    nx.draw_networkx_nodes(sub, pos, ax=ax, node_color="#54a24b", node_size=[80 + 30 * h.degree(n, weight="weight") for n in sub])
    nx.draw_networkx_labels(sub, pos, labels={n: short(g.nodes[n]["name"], 26) for n in sub}, ax=ax, font_size=7)
    ax.set_title("Institution collaboration: top-30 institutions by strength (edge width = shared papers)")
    ax.axis("off")
    save(fig, path)


def case(sub, nodes, edges, g, title, path):
    h = nx.Graph()
    h.add_nodes_from(sorted(nodes))
    h.add_edges_from((r[1], r[2]) for r in edges)
    pos = nx.spring_layout(h, seed=SEED, k=1.6 / max(len(h), 1) ** 0.5, iterations=150)
    fig, ax = plt.subplots(figsize=(14, 11))
    nx.draw_networkx_edges(h, pos, ax=ax, alpha=0.3, width=0.7)
    nx.draw_networkx_nodes(h, pos, ax=ax, node_color=[LABEL_COLORS[g.nodes[n]["label"]] for n in h], node_size=120)
    lab = {n: short(g.nodes[n]["name"], 24) for n in h if g.nodes[n]["label"] in ("Task", "Method", "Dataset", "Institution")}
    nx.draw_networkx_labels(h, pos, labels=lab, ax=ax, font_size=7)
    present = sorted({g.nodes[n]["label"] for n in h})
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color=LABEL_COLORS[l], label=l) for l in present], loc="lower left")
    ax.set_title(f"Case study: {title} ({len(h)} nodes, {h.number_of_edges()} edges)")
    ax.axis("off")
    save(fig, path)


def nlp_bars(tasks, methods, path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    for ax, rows, title, color in ((axes[0], tasks, "Papers per Task", "#4c78a8"), (axes[1], methods[:15], "Papers per Method (top 15)", "#b279a2")):
        ax.barh([r[1] for r in rows][::-1], [r[2] for r in rows][::-1], color=color)
        ax.set_title(title)
        ax.set_xlabel("number of papers")
    save(fig, path)
