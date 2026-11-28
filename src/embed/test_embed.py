import csv
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import scipy.sparse as sp

from .embed import fastrp, load_config, nearest, read_graph, run

CLUSTERS = ("a", "b")
LINKS = {"task": "STUDIES_TASK", "method": "USES_METHOD", "dataset": "EVALUATED_ON"}


def fixture(directory, shuffle_seed=None):
    nodes, edges = [], []
    for c in CLUSTERS:
        topics = [(f"{kind}:{c}{i}", kind.capitalize()) for kind in LINKS for i in (1, 2)]
        nodes += topics
        for p in range(8):
            paper = f"paper:{c}{p}"
            nodes += [(paper, "Paper"), (f"author:{c}{p}", "Author")]
            edges.append((f"author:{c}{p}", paper, "AUTHORED"))
            edges.append((f"author:{c}{(p + 1) % 8}", paper, "AUTHORED"))
            for offset in (0, 1, 2):
                topic = topics[(p + offset) % len(topics)][0]
                edges.append((paper, topic, LINKS[topic.split(":")[0]]))
    nodes += [("task:orphan", "Task"), ("task:z_island", "Task"), ("paper:z_island", "Paper")]
    edges.append(("paper:z_island", "task:z_island", "STUDIES_TASK"))
    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(nodes)
        random.Random(shuffle_seed).shuffle(edges)
    for name, header, rows in (
        ("nodes.csv", ["id", "label", "validation_status"], [(*n, "accepted") for n in nodes]),
        ("edges.csv", ["src", "dst", "type", "validation_status"], [(*e, "accepted") for e in edges]),
    ):
        with (directory / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)


def rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


class FixedDraw:
    def __init__(self, values):
        self.values = values

    def random(self, shape):
        assert shape == self.values.shape
        return self.values


class FastRPTest(unittest.TestCase):
    def test_hand_computed_path_graph(self):
        adjacency = sp.csr_matrix(np.array([[0, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 0]], dtype=float))
        draw = np.full((4, 4), 0.5)
        draw[0, 0], draw[1, 1], draw[2, 2], draw[3, 3] = 0.1, 0.1, 0.9, 0.1
        r = 2**0.5
        n1 = np.array([[0, 2, 0, 0], [r, 0, -r, 0], [0, 2, 0, 0], [0, 0, 0, 0]])
        n2 = np.array([[r, 0, -r, 0], [0, 2, 0, 0], [r, 0, -r, 0], [0, 0, 0, 0]])
        with mock.patch("numpy.random.default_rng", return_value=FixedDraw(draw)):
            for weights, expected in (([1, 0], n1), ([0, 1], n2), ([0, 0, 1, 3], n1 + 3 * n2)):
                np.testing.assert_allclose(fastrp(adjacency, 4, weights, -0.5, 0), expected, atol=1e-12)


class NearestTest(unittest.TestCase):
    def test_ties_by_id_floor_and_short_lists(self):
        vectors = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
        self.assertEqual(
            nearest(["c", "b", "a", "x", "y"], vectors, 5, 0.02),
            [
                ("c", "a", 1, "1.000000"),
                ("c", "b", 2, "1.000000"),
                ("b", "a", 1, "1.000000"),
                ("b", "c", 2, "1.000000"),
                ("a", "b", 1, "1.000000"),
                ("a", "c", 2, "1.000000"),
            ],
        )


class EmbedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.outs = []
        for i, shuffle in enumerate((None, 7)):
            data = base / f"in{i}"
            data.mkdir()
            fixture(data, shuffle)
            out = base / f"out{i}"
            run(load_config(), data, out)
            cls.outs.append(out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_deterministic_and_independent_of_row_order(self):
        for name in ("similar_topics.csv", "topic_umap.csv"):
            self.assertEqual((self.outs[0] / name).read_bytes(), (self.outs[1] / name).read_bytes())

    def test_similar_topics_schema(self):
        header, data = rows(self.outs[0] / "similar_topics.csv")
        self.assertEqual(header, ["topic_id", "similar_topic_id", "rank", "cosine"])
        by_topic = {}
        for r in data:
            by_topic.setdefault(r["topic_id"], []).append(r)
        self.assertEqual(len(by_topic), 12)
        self.assertNotIn("task:orphan", by_topic)
        self.assertNotIn("task:z_island", by_topic)
        self.assertNotIn("task:z_island", [r["similar_topic_id"] for r in data])
        for topic, group in by_topic.items():
            self.assertEqual([int(r["rank"]) for r in group], [1, 2, 3, 4, 5])
            scores = [float(r["cosine"]) for r in group]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertTrue(all(-1 <= s <= 1 for s in scores))
            self.assertNotIn(topic, [r["similar_topic_id"] for r in group])

    def test_neighbours_stay_in_cluster(self):
        _, data = rows(self.outs[0] / "similar_topics.csv")
        for r in data:
            self.assertEqual(r["topic_id"].split(":")[1][0], r["similar_topic_id"].split(":")[1][0], r)

    def test_umap_schema(self):
        header, data = rows(self.outs[0] / "topic_umap.csv")
        self.assertEqual(header, ["topic_id", "x", "y", "n_papers"])
        _, similar = rows(self.outs[0] / "similar_topics.csv")
        self.assertEqual([r["topic_id"] for r in data], sorted({r["topic_id"] for r in similar} | {"task:z_island"}))
        for r in data:
            float(r["x"]), float(r["y"])
        papers = {r["topic_id"]: int(r["n_papers"]) for r in data}
        self.assertEqual(papers["task:z_island"], 1)
        self.assertEqual(papers["task:a1"], 4)

    def test_cosine_is_mean_over_fixed_seeds(self):
        config = load_config()
        data = Path(self.tmp.name) / "in0"
        ids, _, adjacency = read_graph(data, config)
        _, similar = rows(self.outs[0] / "similar_topics.csv")
        cosines = {}
        for seed in range(config["seed"], config["seed"] + config["seed_count"]):
            v = fastrp(adjacency, config["dimension"], config["iteration_weights"], config["normalization_beta"], seed)
            for r in similar:
                a, b = v[ids.index(r["topic_id"])], v[ids.index(r["similar_topic_id"])]
                cosines.setdefault((r["topic_id"], r["similar_topic_id"]), []).append(a @ b / np.linalg.norm(a) / np.linalg.norm(b))
        self.assertGreater(config["seed_count"], 1)
        for r in similar:
            self.assertAlmostEqual(float(r["cosine"]), float(np.mean(cosines[r["topic_id"], r["similar_topic_id"]])), places=5)


if __name__ == "__main__":
    unittest.main()
