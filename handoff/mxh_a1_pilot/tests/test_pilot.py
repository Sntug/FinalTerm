"""Meaningful regression checks for identity, parser precision and offline safety."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.collect.__main__ import check_b_input
from src.collect.cvf import CVFHTML, HTTPCache, HTTPBlocked, parse_detail, parse_listing, rank_urls
from src.common import ORIGINAL_FIELDS, canonical_cvf_url, clean_text, digest, edge_id, evidence_id, paper_id_from_url, stable_id, write_json
from src.quality.__main__ import validate_json

CVPR = "https://openaccess.thecvf.com/content/CVPR2024/html/Test_Title_CVPR_2024_paper.html"
ICCV = "https://openaccess.thecvf.com/content/ICCV2023/html/Test_Title_ICCV_2023_paper.html"


def fixture_html(month="June", year="2024", title="A &amp; B"):
    return f'''<html><head>
    <meta name="citation_title" content="{title}">
    <meta name="citation_author" content="Nguyễn, Hùng">
    <meta name="citation_author" content="Smith, Jane">
    <meta name="citation_publication_date" content="{year}">
    <meta name="citation_conference_title" content="Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition">
    </head><body><div id="content"><div id="papertitle">{title}<dd></div>
    <div id="abstract">We study <b>images</b> &amp; shapes.</div>
    <div class="bibref pre-white-space">@InProceedings{{Test, month = {{{month}}}, year = {{2024}} }}</div>
    </div></body></html>'''.encode("utf-8")


class IdentityTests(unittest.TestCase):
    def test_B_ID_format_is_preserved(self):
        self.assertEqual(paper_id_from_url(ICCV), "cvf:ICCV2023:Test_Title_ICCV_2023")

    def test_workshop_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_cvf_url(CVPR.replace("CVPR2024/", "CVPR2024W/"))

    def test_non_CVF_host_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_cvf_url(CVPR.replace("openaccess.thecvf.com", "example.com"))

    def test_URL_fragment_does_not_create_second_paper(self):
        self.assertEqual(paper_id_from_url(CVPR + "#abstract"), paper_id_from_url(CVPR))

    def test_seed_ranking_is_independent_of_input_order_and_duplicates(self):
        other = CVPR.replace("Test_Title", "Other")
        self.assertEqual(rank_urls([CVPR, other, CVPR], 42), rank_urls([other, CVPR], 42))

    def test_authorship_id_is_per_paper_not_name(self):
        self.assertNotEqual(stable_id("authorship", CVPR, "1"), stable_id("authorship", ICCV, "1"))

    def test_NFC_and_whitespace(self):
        self.assertEqual(clean_text("  e\u0301 \n x  "), "é x")

    def test_undirected_edge_has_one_ID(self):
        self.assertEqual(edge_id("b", "COAUTHORED_WITH", "a"), edge_id("a", "COAUTHORED_WITH", "b"))

    def test_citation_direction_is_not_lost(self):
        self.assertNotEqual(edge_id("b", "CITES", "a"), edge_id("a", "CITES", "b"))

    def test_collaboration_self_loop_is_rejected(self):
        with self.assertRaises(ValueError):
            edge_id("a", "COLLABORATED_WITH", "a")

    def test_evidence_support_order_does_not_duplicate_evidence(self):
        args = ("p", "s", "abstract", "rule", "1")
        self.assertEqual(evidence_id(*args, supporting_evidence_ids=("b", "a", "a")),
                         evidence_id(*args, supporting_evidence_ids=("a", "b")))


class ParserTests(unittest.TestCase):
    def test_meta_entities_and_ordered_authors(self):
        paper = parse_detail(fixture_html(), CVPR, "CVPR", 2024)
        self.assertEqual(paper["title"], "A & B")
        self.assertEqual(paper["authors"][0], {"name": "Hùng Nguyễn", "name_raw": "Nguyễn, Hùng", "author_order": 1})
        self.assertEqual(paper["authors"][1]["author_order"], 2)
        self.assertEqual(paper["abstract"], "We study images & shapes.")

    def test_month_does_not_become_day_one(self):
        paper = parse_detail(fixture_html(), CVPR, "CVPR", 2024)
        self.assertEqual((paper["publication_date"], paper["date_precision"]), ("2024-06", "month"))

    def test_year_only_is_preserved(self):
        paper = parse_detail(fixture_html(month="unknown"), CVPR, "CVPR", 2024)
        self.assertEqual((paper["publication_date"], paper["date_precision"]), ("2024", "year"))

    def test_full_source_date_is_preserved(self):
        paper = parse_detail(fixture_html(year="2024/06/18"), CVPR, "CVPR", 2024)
        self.assertEqual((paper["publication_date"], paper["date_precision"]), ("2024-06-18", "day"))

    def test_missing_fields_stay_unknown(self):
        paper = parse_detail(fixture_html(), CVPR, "CVPR", 2024)
        for field in ("doi", "citation_count", "affiliations", "referenced_works", "openalex_id"):
            self.assertIsNone(paper[field])

    def test_wrong_year_fails(self):
        with self.assertRaises(ValueError):
            parse_detail(fixture_html(year="2023"), CVPR, "CVPR", 2024)

    def test_title_conflict_fails(self):
        body = fixture_html().replace(b'id="papertitle">A &amp; B', b'id="papertitle">Different')
        with self.assertRaises(ValueError):
            parse_detail(body, CVPR, "CVPR", 2024)

    def test_listing_excludes_workshop_and_deduplicates(self):
        workshop = CVPR.replace("CVPR2024/", "CVPR2024W/")
        body = f'<a href="{CVPR}">a</a><a href="{CVPR}">b</a><a href="{workshop}">w</a>'.encode()
        self.assertEqual(parse_listing(body, "CVPR", 2024), [CVPR])


class InputTests(unittest.TestCase):
    def row(self):
        return dict(paper_id=paper_id_from_url(ICCV), doi="", cvf_url=ICCV,
                    conference="ICCV", conference_year="2023", owner="B", status="provisional_pilot")

    def test_optional_blank_DOI_is_valid(self):
        self.assertEqual(check_b_input(ORIGINAL_FIELDS, [self.row()], 1), [])

    def test_duplicate_B_row_is_rejected(self):
        self.assertTrue(check_b_input(ORIGINAL_FIELDS, [self.row(), self.row()], 2))

    def test_ID_URL_mismatch_is_rejected(self):
        row = self.row(); row["paper_id"] = "wrong"
        self.assertTrue(check_b_input(ORIGINAL_FIELDS, [row], 1))

    def test_wrong_owner_is_rejected(self):
        row = self.row(); row["owner"] = "A"
        self.assertTrue(check_b_input(ORIGINAL_FIELDS, [row], 1))


class OfflineAndSchemaTests(unittest.TestCase):
    def test_offline_never_requests_network(self):
        with tempfile.TemporaryDirectory() as directory, patch("src.collect.cvf.urlopen") as request:
            with self.assertRaises(FileNotFoundError):
                HTTPCache(Path(directory), offline=True).get(CVPR)
            request.assert_not_called()

    def test_corrupt_cache_fails_without_refetch(self):
        with tempfile.TemporaryDirectory() as directory, patch("src.collect.cvf.urlopen") as request:
            root = Path(directory)
            raw = root / "data/raw/http/body.html.gz"; raw.parent.mkdir(parents=True)
            raw.write_bytes(gzip.compress(b"tampered"))
            write_json(root / "data/raw/http" / (digest(CVPR.encode()) + ".json"),
                       {"url": CVPR, "raw_path": "data/raw/http/body.html.gz", "content_sha256": digest(b"original")})
            with self.assertRaises(ValueError):
                HTTPCache(root).get(CVPR)
            request.assert_not_called()

    def test_403_stops_without_retries(self):
        from urllib.error import HTTPError
        with tempfile.TemporaryDirectory() as directory, patch("src.collect.cvf.urlopen", side_effect=HTTPError(CVPR,403,"Forbidden",{},None)) as request:
            with self.assertRaises(HTTPBlocked):
                HTTPCache(Path(directory), delay=0).get(CVPR)
            self.assertEqual(request.call_count, 1)

    def test_schema_checks_missing_required_and_wrong_type(self):
        schema = {"type": "object", "required": ["n"], "additionalProperties": False,
                  "properties": {"n": {"type": "integer", "minimum": 1}}}
        self.assertTrue(validate_json({}, schema))
        self.assertTrue(validate_json({"n": True}, schema))
        self.assertTrue(validate_json({"n": 0}, schema))
        self.assertTrue(validate_json({"n": 2, "extra": 1}, schema))
        self.assertEqual(validate_json({"n": 2}, schema), [])


if __name__ == "__main__":
    unittest.main()
