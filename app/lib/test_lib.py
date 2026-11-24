import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import load_table
from lib.data import query_path, table_path
from lib.subgraph import subgraph_html
from lib.theme import THEME

NODES = [
    {"id": "p1", "label": "Paper", "name": "Alpha Paper", "cvf_url": "https://example.org/p1"},
    {"id": "a1", "label": "Author", "name": "Ada Author"},
]
EDGES = [{"source": "a1", "target": "p1", "type": "AUTHORED"}]


class LibTest(unittest.TestCase):
    def test_query_name_rejects_paths(self):
        for bad in ("../x", "a/b", "a\\b", "", "x.cypher"):
            with self.assertRaises(ValueError):
                query_path(bad)
        self.assertTrue(query_path("count_by_type").exists())

    def test_load_table_registry(self):
        self.assertTrue(str(table_path("communities")).endswith("outputs/trend/sna/communities.csv"))
        with self.assertRaises(KeyError):
            load_table("nope")
        with self.assertRaises(FileNotFoundError) as cm:
            load_table("topic_leaders")
        self.assertIn("not available yet", str(cm.exception))

    def test_render_subgraph_html(self):
        html = subgraph_html(NODES + EDGES)
        for s in ("Alpha Paper", "Ada Author", "AUTHORED", "https://example.org/p1", THEME["label_colors"]["Paper"], '"arrows": "to"', "network.on('click'"):
            self.assertIn(s, html)

    def test_subgraph_dedupes_edges_and_sets_height(self):
        html = subgraph_html(NODES + EDGES + EDGES, height=600)
        self.assertEqual(html.count('"label": "AUTHORED"'), 1)
        self.assertIn("height: 580px", html)


if __name__ == "__main__":
    unittest.main()
