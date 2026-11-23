import json
import unittest

from quality.checks.test_a2_support import temporary_workspace
from src.collect.common import REPO_ROOT, json_bytes, load_config, load_selection, record_bytes
from src.collect.contract import contract
from src.collect.openalex import assessment, enrich, rule_version
from src.collect.trend_selection import ranking
from src.graph.export_graph import export
from src.graph.load_neo4j import read_snapshot


class TrendSelectionTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((REPO_ROOT / "config/a_trend_project.json").read_text("utf-8"))

    def test_offline_rank_matches_locked_registries(self):
        for year in (2024, 2025, 2026):
            with self.subTest(year=year):
                cfg = load_config(REPO_ROOT, f"config/a_cvpr{year}_350.json")
                urls, listing = ranking(REPO_ROOT, cfg, self.policy)
                selection = load_selection(REPO_ROOT, cfg)
                self.assertEqual([p["cvf_url"] for p in selection["papers"]], urls[:350])
                self.assertEqual(selection["listing_source_record_id"], listing["source_record_id"])
                self.assertEqual(selection["candidate_count"], len(urls))

    def test_trend_venue_round_trip_through_graph_export_and_reader(self):
        # Metadata fixture only. No CVF detail, gold abstract or live database is needed.
        with temporary_workspace() as root:
            source = root / "corpus/snapshots/fixture"
            clean = root / "clean"
            source.mkdir(parents=True)
            clean.mkdir()
            pid = "cvf:CVPR2025:Fixture_CVPR_2025"
            venue = "venue:CVPR:2025:main"
            self.assertIn(venue, self.policy["venue_ids"])
            paper = dict(paper_id=pid, venue_id=venue, conference="CVPR", conference_year=2025,
                         owner="A", scope="core", track="main", title="Fixture", representative_source_record_id="source:cvf:fixture")
            (source / "papers.jsonl").write_bytes(record_bytes("papers.jsonl", [], [paper]))
            (source / "paper_registry.csv").write_bytes(record_bytes("paper_registry.csv", ["paper_id", "status"],
                                                                     [dict(paper_id=pid, status="cvf_verified")]))
            manifest = dict(snapshot_id="snapshot:v2:fixture", created_at="2026-01-01T00:00:00Z",
                            parser_versions=[], rule_versions={}, dictionary_versions={}, applied_decision_ids=[])
            for directory in (source, clean):
                (directory / "snapshot_manifest.json").write_bytes(json_bytes(manifest))
            for name in ("nodes.csv", "authorships.csv", "evidence.jsonl"):
                (clean / name).write_bytes(record_bytes(name, contract()["files"][name]["fields"], []))
            project = self.policy["project_id"]
            cfg = dict(project_id=project, output_dir="graph", code_version="fixture",
                       inputs=[dict(name="CVPR2025", snapshots_dir="corpus/snapshots", a3_dir="clean")])
            export(cfg, root)
            result, nodes, edges = read_snapshot(root / "graph", project)
            self.assertEqual(result["schema_version"], self.policy["schema_version"])
            self.assertEqual({(label, row["id"]) for label, row in nodes}, {("Paper", pid), ("VenueEdition", venue)})
            self.assertEqual([edge[:3] for edge in edges], [(pid, "PUBLISHED_IN", venue)])
            with self.assertRaisesRegex(ValueError, "project_id mismatch"):
                read_snapshot(root / "graph", contract()["project_id"])


class OpenAlexTrendMatchingTests(unittest.TestCase):
    def setUp(self):
        self.paper = dict(conference="CVPR", conference_year=2026, paper_id="cvf:CVPR2026:Fixture", title="A title",
                          cvf_url="https://openaccess.thecvf.com/content/CVPR2026/html/Fixture_paper.html",
                          authors=[dict(name="Alice Smith", name_raw="Smith, Alice"),
                                   dict(name="Bob Jones", name_raw="Jones, Bob")],
                          arxiv_url="https://arxiv.org/abs/2603.12345v2", doi=None, abstract="A text")
        self.work = dict(id="https://openalex.org/W1", display_name="A title", publication_year=2026,
                         authorships=[dict(raw_author_name="Smith, Alice"), dict(raw_author_name="Jones, Bob")],
                         locations=[dict(source=dict(display_name="CVPR"))])

    def test_2026_ordered_raw_names_need_independent_match(self):
        self.assertTrue(assessment(self.paper, self.work)["accepted"])
        self.assertEqual(rule_version(self.paper), "1.2.0")
        for change in (
            dict(authorships=self.work["authorships"][::-1]),
            dict(authorships=[dict(raw_author_name="Smith, Mallory"), dict(raw_author_name="Jones, Bob")]),
            dict(authorships=[dict(raw_author_name="Alice, Smith"), dict(raw_author_name="Jones, Bob")]),
            dict(locations=[dict(source=dict(display_name="CVPR Workshop"))]),
            dict(display_name="Another title"),
        ):
            with self.subTest(change=change):
                self.assertFalse(assessment(self.paper, {**self.work, **change})["accepted"])
        previous = {**self.paper, "conference_year": 2025}
        self.assertEqual(rule_version(previous), "1.1.0")
        self.assertFalse(assessment(previous, {**self.work, "publication_year": 2025})["accepted"])

    def test_arxiv_link_requires_official_identifier_and_compatible_version(self):
        for url, accepted in (
            ("https://arxiv.org/pdf/2603.12345.pdf", True),
            ("https://doi.org/10.48550/arXiv.2603.12345v2", True),
            ("https://doi.org/10.48550/arXiv.2603.12345v1", False),
            ("https://arxiv.org/abs/2603.12346v2", False),
            ("https://arxiv.org.example.org/pdf/2603.12345.pdf", False),
            ("https://example.org/10.48550/arXiv.2603.12345v2", False),
            ("https://arxiv.org/other/2603.12345v2", False),
            ("https://[invalid", False),
        ):
            work = {**self.work, "locations": [dict(landing_page_url=url)], "publication_year": 2025}
            with self.subTest(url=url):
                self.assertEqual(assessment(self.paper, work)["accepted"], accepted)
                self.assertFalse(assessment(self.paper, {**work, "publication_year": 2023})["accepted"])
        work = {**self.work, "locations": [dict(landing_page_url=self.paper["arxiv_url"])],
                "doi": "https://doi.org/10.48550/arXiv.2603.12345v1"}
        self.assertFalse(assessment(self.paper, work)["accepted"])

    def test_preprint_doi_not_assigned_to_conference_paper(self):
        work = {**self.work, "locations": [], "doi": "https://doi.org/10.48550/arXiv.2603.12345"}
        self.assertTrue(assessment(self.paper, work)["accepted"])
        records = {"field_provenance.csv": []}
        enrich(records, self.paper, work, [dict(source_record_id="source:fixture", fetched_at="2026-01-01")],
               {"status": "matched"})
        self.assertIsNone(self.paper["doi"])
        self.assertEqual(self.paper["openalex_id"], work["id"])
        self.assertEqual(records["field_provenance.csv"][0]["selection_rule"], "openalex-work-match-1.2.0")
