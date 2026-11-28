import argparse
import csv
import json
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/b_embed.json"


def load_config(path=CONFIG):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_accepted(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if r["validation_status"] == "accepted"]


def read_graph(directory, config):
    labels = {r["id"]: r["label"] for r in read_accepted(directory / "nodes.csv") if r["label"] in config["node_labels"]}
    ids = sorted(labels)
    index = {node: i for i, node in enumerate(ids)}
    pairs = set()
    for r in read_accepted(directory / "edges.csv"):
        if r["type"] in config["edge_types"]:
            if r["src"] not in index or r["dst"] not in index:
                raise ValueError(f"{r['type']} edge endpoint missing from nodes.csv: {r['src']} -> {r['dst']}")
            a, b = index[r["src"]], index[r["dst"]]
            pairs.add((min(a, b), max(a, b)))
    if not pairs:
        raise ValueError(f"No edges of types {config['edge_types']} in {directory}")
    row, col = np.array(sorted(pairs)).T
    half = sp.coo_matrix((np.ones(len(row)), (row, col)), shape=(len(ids), len(ids)))
    return ids, labels, (half + half.T).tocsr()


def fastrp(adjacency, dimension, weights, beta, seed):
    n = adjacency.shape[0]
    degree = np.asarray(adjacency.sum(axis=1)).ravel()
    linked = degree > 0
    inverse = np.zeros(n)
    inverse[linked] = 1 / degree[linked]
    scale = np.zeros(n)
    scale[linked] = (degree[linked] / degree.sum()) ** beta
    transition = sp.diags(inverse) @ adjacency
    s = np.sqrt(n)
    draw = np.random.default_rng(seed).random((n, dimension))
    projection = np.sqrt(s) * ((draw < 1 / (2 * s)).astype(float) - (draw > 1 - 1 / (2 * s)))
    current = scale[:, None] * projection
    total = np.zeros((n, dimension))
    for weight in weights:
        current = transition @ current
        total += weight * current
    return total


def normalize(vectors):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return np.divide(vectors, norms, out=np.zeros_like(vectors), where=norms > 0)


def nearest(topics, vectors, top_k, min_cosine):
    unit = normalize(vectors)
    cosine = np.clip(unit @ unit.T, -1, 1).round(6)
    rows = []
    for i, topic in enumerate(topics):
        ranked = sorted((j for j in range(len(topics)) if j != i and cosine[i, j] >= min_cosine), key=lambda j: (-cosine[i, j], topics[j]))
        rows += [(topic, topics[j], rank, f"{cosine[i, j]:.6f}") for rank, j in enumerate(ranked[:top_k], 1)]
    return rows


def project_2d(vectors, config):
    import umap

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=min(config["umap_neighbors"], len(vectors) - 1),
        min_dist=config["umap_min_dist"],
        metric="cosine",
        random_state=config["seed"],
        n_jobs=1,
    )
    return reducer.fit_transform(vectors)


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def run(config, input_dir, output_dir):
    ids, labels, adjacency = read_graph(Path(input_dir), config)
    degree = np.diff(adjacency.indptr)
    all_topics = [i for i, node in enumerate(ids) if labels[node] in config["topic_labels"]]
    kept = [i for i in all_topics if degree[i] > 0]
    if len(kept) < 3:
        raise ValueError(f"Need at least 3 connected topics, found {len(kept)}")
    topics = [ids[i] for i in kept]
    seeds = range(config["seed"], config["seed"] + config["seed_count"])
    vectors = np.hstack(
        [normalize(fastrp(adjacency, config["dimension"], config["iteration_weights"], config["normalization_beta"], seed)[kept]) for seed in seeds]
    )
    output_dir = Path(output_dir)
    similar = nearest(topics, vectors, config["top_k"], config["min_cosine"])
    write_csv(output_dir / "similar_topics.csv", ["topic_id", "similar_topic_id", "rank", "cosine"], similar)
    coordinates = project_2d(vectors, config)
    write_csv(
        output_dir / "topic_umap.csv",
        ["topic_id", "x", "y", "n_papers"],
        [(t, f"{x:.6f}", f"{y:.6f}", degree[i]) for t, i, (x, y) in zip(topics, kept, coordinates)],
    )
    return {
        "nodes": len(ids),
        "edges": adjacency.nnz // 2,
        "topics": len(topics),
        "topics_without_edges": sorted(ids[i] for i in all_topics if degree[i] == 0),
        "topics_without_neighbours": sorted(set(topics) - {r[0] for r in similar}),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m src.embed.embed")
    parser.add_argument("--config", default=CONFIG)
    parser.add_argument("--input")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    input_dir = ROOT / (args.input or config["input_dir"])
    output_dir = ROOT / (args.out or config["output_dir"])
    print(json.dumps({"input": str(input_dir), "output": str(output_dir), **run(config, input_dir, output_dir)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
