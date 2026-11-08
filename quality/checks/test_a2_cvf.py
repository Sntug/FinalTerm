"""A1 parser/cache regression checks adapted to the integrated module paths."""
import gzip
import json
from test_a2_support import temporary_workspace
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch
from urllib.error import HTTPError, URLError

from src.collect.cache import HTTPCache, HTTPBlocked
from src.collect.common import canonical_cvf_url, paper_id_from_url
from src.collect.cvf import parse_detail, parse_listing, rank_urls
from src.clean.text import identifier, sha256

CVPR = "https://openaccess.thecvf.com/content/CVPR2024/html/Test_Title_CVPR_2024_paper.html"
ICCV = "https://openaccess.thecvf.com/content/ICCV2023/html/Test_Title_ICCV_2023_paper.html"
RAW = "data/raw/cvpr2024"


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


class ParserTests(unittest.TestCase):
    def test_shared_ids_preserve_B_and_ignore_fragments(self):
        self.assertEqual(paper_id_from_url(ICCV), "cvf:ICCV2023:Test_Title_ICCV_2023")
        self.assertEqual(paper_id_from_url(CVPR + "#abstract"), paper_id_from_url(CVPR))

    def test_workshop_foreign_host_and_query_are_rejected(self):
        for url in (CVPR.replace("CVPR2024/", "CVPR2024W/"),
                    CVPR.replace("openaccess.thecvf.com", "example.com"), CVPR + "?different=1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonical_cvf_url(url)

    def test_listing_deduplicates_and_excludes_workshop(self):
        body = f'<a href="{CVPR}">a</a><a href="{CVPR}">b</a><a href="{CVPR.replace("CVPR2024/", "CVPR2024W/")}">w</a>'.encode()
        self.assertEqual(parse_listing(body, "CVPR", 2024), [CVPR])

    def test_seed_selection_ignores_order_and_duplicates(self):
        other = CVPR.replace("Test_Title", "Other")
        self.assertEqual(rank_urls([CVPR, other, CVPR], 42), rank_urls([other, CVPR], 42))

    def test_author_order_entities_and_unknowns_survive(self):
        paper = parse_detail(fixture_html(), CVPR, "CVPR", 2024)
        self.assertEqual(paper["title"], "A & B")
        self.assertEqual(paper["authors"][0], {"name": "Hùng Nguyễn", "name_raw": "Nguyễn, Hùng", "author_order": 1})
        self.assertEqual(paper["authors"][1]["author_order"], 2)
        self.assertEqual(paper["abstract"], "We study images & shapes.")
        for field in ("doi", "citation_count", "affiliations", "referenced_works", "openalex_id"):
            self.assertIsNone(paper[field])

    def test_date_precision_never_invents_day_one(self):
        for year, month, expected in (("2024", "June", ("2024-06", "month")),
                                      ("2024", "unknown", ("2024", "year")),
                                      ("2024/06/18", "June", ("2024-06-18", "day"))):
            paper = parse_detail(fixture_html(month=month, year=year), CVPR, "CVPR", 2024)
            self.assertEqual((paper["publication_date"], paper["date_precision"]), expected)

    def test_wrong_year_and_title_conflict_fail(self):
        bodies = [fixture_html(year="2023"),
                  fixture_html().replace(b'id="papertitle">A &amp; B', b'id="papertitle">Different')]
        for body in bodies:
            with self.assertRaises(ValueError):
                parse_detail(body, CVPR, "CVPR", 2024)

    def test_authorship_identity_does_not_merge_people_by_name(self):
        self.assertNotEqual(identifier("authorship", CVPR, "1"), identifier("authorship", ICCV, "1"))


class CacheTests(unittest.TestCase):
    def response(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = CVPR
        response.status = 200
        response.read.return_value = fixture_html()
        response.headers = {"Content-Type": "text/html"}
        return response

    def test_offline_cache_miss_never_requests_network(self):
        with temporary_workspace() as directory, patch("src.collect.cache.urlopen") as request:
            with self.assertRaises(FileNotFoundError):
                HTTPCache(Path(directory), RAW).get(CVPR)
            request.assert_not_called()

    def test_cached_second_run_resumes_without_network(self):
        with temporary_workspace() as directory:
            root = Path(directory)
            with patch("src.collect.cache.urlopen", return_value=self.response()) as request:
                first = HTTPCache(root, RAW, offline=False, delay=0).get(CVPR)
                self.assertEqual(request.call_count, 1)
            with patch("src.collect.cache.urlopen") as request:
                self.assertEqual(first, HTTPCache(root, RAW).get(CVPR))
                request.assert_not_called()

    def test_corrupt_cache_and_missing_body_do_not_refetch(self):
        with temporary_workspace() as directory:
            root = Path(directory)
            with patch("src.collect.cache.urlopen", return_value=self.response()):
                _, meta = HTTPCache(root, RAW, offline=False, delay=0).get(CVPR)
            path = root / meta["raw_path"]
            path.write_bytes(gzip.compress(b"tampered"))
            with patch("src.collect.cache.urlopen") as request:
                with self.assertRaises(ValueError):
                    HTTPCache(root, RAW, offline=False).get(CVPR)
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    HTTPCache(root, RAW, offline=False).get(CVPR)
                request.assert_not_called()

    def test_cache_path_cannot_escape_A_corpus(self):
        with temporary_workspace() as directory:
            root = Path(directory)
            with patch("src.collect.cache.urlopen", return_value=self.response()):
                _, meta = HTTPCache(root, RAW, offline=False, delay=0).get(CVPR)
            meta["raw_path"] = "data/raw/iccv2023/other.html.gz"
            (root / RAW / "http" / (sha256(CVPR.encode()) + ".json")).write_text(json.dumps(meta))
            with patch("src.collect.cache.urlopen") as request, self.assertRaises(ValueError):
                HTTPCache(root, RAW, offline=False).get(CVPR)
            request.assert_not_called()

    def test_403_and_429_stop_without_retry(self):
        for code in (403, 429):
            with temporary_workspace() as directory, patch("src.collect.cache.urlopen", side_effect=HTTPError(CVPR, code, "blocked", {}, None)) as request:
                with self.assertRaises(HTTPBlocked):
                    HTTPCache(Path(directory), RAW, offline=False, delay=0).get(CVPR)
                self.assertEqual(request.call_count, 1)

    def test_transient_errors_retry_with_backoff(self):
        failures = [HTTPError(CVPR, 503, "unavailable", {}, None), URLError("temporary"), self.response()]
        with temporary_workspace() as directory, patch("src.collect.cache.urlopen", side_effect=failures) as request, patch("src.collect.cache.time.sleep") as sleep:
            body, _ = HTTPCache(Path(directory), RAW, offline=False, delay=0).get(CVPR)
            self.assertEqual(body, fixture_html())
            self.assertEqual(request.call_count, 3)
            self.assertEqual(sleep.call_args_list, [call(1), call(2)])

    def test_retry_exhaustion_leaves_no_success_cache(self):
        with temporary_workspace() as directory, patch("src.collect.cache.urlopen", side_effect=URLError("temporary")) as request, patch("src.collect.cache.time.sleep"):
            with self.assertRaises(RuntimeError):
                HTTPCache(Path(directory), RAW, offline=False, delay=0).get(CVPR)
            self.assertEqual(request.call_count, 3)
            self.assertFalse(list(Path(directory).rglob("*.json")))


if __name__ == "__main__":
    unittest.main()
