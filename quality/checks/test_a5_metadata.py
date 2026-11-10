"""Offline A5 source/identity safety, immutable replay and B exporter compatibility."""
from copy import deepcopy
import gzip
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from src.collect.common import REPO_ROOT, json_bytes
from src.collect.pilot import run as collect
from src.collect.cache import openalex_source
from src.collect.openalex import enrich
from src.clean.resolution import resolve
from src.clean.text import identifier, sha256, canonical_json, text_record
from src.clean.verify import validate_integrity
from src.nlp.validation import read_manifest
from src.metadata.audit import crosscheck, lookup_plan
from src.metadata.pipeline import run, load, exporter_input
from src.metadata.sources import SupplementalCache, arxiv_metadata
from src.metadata.verify import verify
from src.graph.export_graph import build
from test_a2_support import temporary_workspace
from test_a2_collector import setup
from test_a4_nlp import write_snapshot

STAMP = "2026-11-10T00:00:00Z"


def fixture(root, conference="CVPR", missing_doi=False, institution_offset=0):
    setup(root, conference=conference, enabled=False)
    result = collect(root, "config/fixture.json", offline=True)
    a2, original = read_manifest(root, result["manifest"])
    paper = original["papers.jsonl"][0]
    inst = lambda i: dict(id=f"https://openalex.org/I{i}", display_name=f"Example Institute {i}", country_code="VN", ror=None)
    authors = [dict(raw_author_name=a["name"], author=dict(id=f"https://openalex.org/A{i}", display_name=a["name"], orcid=None),
                    institutions=[inst(i + institution_offset)], raw_affiliation_strings=[], affiliations=[]) for i, a in enumerate(paper["authors"], 1)]
    work = dict(id="https://openalex.org/W123", display_name=paper["title"], publication_year=paper["conference_year"],
                locations=[dict(source={"display_name": conference}, landing_page_url=paper["cvf_url"])],
                authorships=authors, doi=None if missing_doi else "https://doi.org/10.1234/test", cited_by_count=0,
                referenced_works=[], abstract_inverted_index=None)
    body = json_bytes(work)
    raw = root / "data/raw/work.json.gz"
    raw.write_bytes(gzip.compress(body, mtime=0))
    meta = dict(url="https://api.openalex.org/works/W123", fetched_at=STAMP, http_status=200,
                content_sha256=sha256(body), raw_path="data/raw/work.json.gz", content_type="application/json", etag=None, last_modified=None)
    source = openalex_source(meta, paper["paper_id"], "work_detail")
    original["source_records.jsonl"].append(source)
    enrich(original, paper, work, [source], {"status": "matched"})
    original["paper_registry.csv"][0]["doi"] = paper["doi"]
    bodies = {s["source_record_id"]: gzip.decompress((root / s["raw_path"]).read_bytes()) for s in original["source_records.jsonl"]}
    data = resolve(original, bodies, a2["snapshot_id"], STAMP)
    corpus = conference.lower() + str(paper["conference_year"])
    directory = "data/processed/" + corpus + "/a3"
    m = write_snapshot(root, directory, data)
    cfg = json.loads((REPO_ROOT / "config/a_cvpr2024_a5.json").read_text())
    cfg.update(input_manifest=directory + "/snapshot_manifest.json", processed_dir="data/processed/" + corpus + "/a5",
               raw_dir="data/raw/" + corpus + "/a5", conference=conference, conference_year=paper["conference_year"], target_count=1)
    (root / "config/a5.json").write_bytes(json_bytes(cfg))
    return cfg, m, data, bodies


def arxiv_body(title="A &amp; B", names=("Nguyễn, Hùng", "Smith, Jane"), aid="2401.12345v2"):
    return (f'<html><meta name="citation_title" content="{title}"><meta name="citation_arxiv_id" content="{aid}">'
            + ''.join(f'<meta name="citation_author" content="{n}">' for n in names)
            + '<meta name="citation_date" content="2023/01/01"></html>').encode()


def observation(data, bodies, source="Crossref", value=None):
    paper = data["papers.jsonl"][0]
    if source == "Crossref":
        message = dict(DOI="10.1234/new", title=[paper["title"]], type="proceedings-article",
                       **{"container-title": [paper["conference"]], "published": {"date-parts": [[paper["conference_year"]]]}},
                       author=[{"given": a["name"].split()[0], "family": " ".join(a["name"].split()[1:])} for a in paper["authors"]])
        if value:
            message.update(value)
        body = json_bytes({"message": message})
        url = "https://api.crossref.org/works/10.1234%2Fnew"
    else:
        body, url = value or arxiv_body(), "https://arxiv.org/abs/2401.12345"
    sid = identifier("source:" + source.lower(), url, sha256(body))
    record = dict(schema_version="2.0.0", source_record_id=sid, paper_id=paper["paper_id"], source=source, source_kind="fixture",
                  source_id=url, source_version=None, url=url, fetched_at=STAMP, http_status=200, content_sha256=sha256(body),
                  content_type="application/json" if source == "Crossref" else "text/html", etag=None, last_modified=None, raw_path="data/raw/supplement.gz")
    bodies[sid] = body
    return dict(paper_id=paper["paper_id"], source=source, url=url, source_record=record, status="fetched", reason="", network_requests=0)


class SafetyTest(unittest.TestCase):
    def test_duplicate_doi_keeps_locked_papers_and_queues_conflict(self):
        with temporary_workspace() as root:
            _, m, data, bodies = fixture(root)
            p = deepcopy(data["papers.jsonl"][0])
            old_pid, old_sid = p["paper_id"], p["representative_source_record_id"]
            p["paper_id"] += "_alternate"
            p["cvf_url"] = p["cvf_url"].replace("_paper.html", "_alternate_paper.html")
            source = deepcopy(next(s for s in data["source_records.jsonl"] if s["source_record_id"] == old_sid))
            raw = bodies[old_sid].replace(b"</head>", b'<meta name="citation_doi" content="10.1234/test"></head>')
            source.update(paper_id=p["paper_id"], url=p["cvf_url"], source_id=p["cvf_url"], content_sha256=sha256(raw))
            source["source_record_id"] = identifier("source:cvf", source["url"], source["content_sha256"])
            bodies[source["source_record_id"]] = raw
            data["source_records.jsonl"].append(source)
            p.update(representative_source_record_id=source["source_record_id"], openalex_id=None, openalex_status="needs_review")
            for field in ("title", "abstract"):
                old_text = next(t for t in data["text_versions.jsonl"] if t["text_version_id"] == p[field + "_text_version_id"])
                new_text = text_record(p["paper_id"], source["source_record_id"], old_text["field_path"], p[field], old_text["parser_version"], source["fetched_at"])
                data["text_versions.jsonl"].append(new_text)
                p[field + "_text_version_id"] = new_text["text_version_id"]
            for a in p["authors"]:
                row = deepcopy(next(r for r in data["authorships.csv"] if r["authorship_id"] == a["authorship_id"]))
                a["authorship_id"] = identifier("authorship", p["paper_id"], str(a["author_order"]))
                row.update(authorship_id=a["authorship_id"], paper_id=p["paper_id"], source_record_id=source["source_record_id"],
                           author_id=None, institution_id=None, identity_status="unresolved", affiliation_status="not_collected",
                           identity_source_record_id=None, affiliation_source_record_id=None, affiliation_raw=None, decision_ids=[])
                data["authorships.csv"].append(row)
            registry = deepcopy(data["paper_registry.csv"][0])
            registry.update(paper_id=p["paper_id"], cvf_url=p["cvf_url"], source_record_id=source["source_record_id"], selection_rank=2)
            data["paper_registry.csv"].append(registry)
            data["papers.jsonl"].append(p)
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [])
            validate_integrity(audit.data)
            self.assertEqual(len(audit.data["papers.jsonl"]), 2)
            self.assertTrue(any(c["field_name"] == "identifier_collision" and c["result"] == "conflict" for c in audit.comparisons.values()))
            self.assertEqual(audit.data["merge_log.jsonl"], data["merge_log.jsonl"])

    def test_exact_conference_doi_update_has_reversible_provenance(self):
        with temporary_workspace() as root:
            cfg, m, data, bodies = fixture(root, missing_doi=True)
            before = deepcopy(data)
            obs = observation(data, bodies)
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [obs])
            self.assertEqual(audit.data["papers.jsonl"][0]["doi"], "10.1234/new")
            self.assertEqual(audit.data["papers.jsonl"][0]["paper_id"], data["papers.jsonl"][0]["paper_id"])
            self.assertEqual(len(audit.data["papers.jsonl"]), 1)
            self.assertEqual(audit.data["authorships.csv"], data["authorships.csv"])
            decision = audit.data["merge_log.jsonl"][-1]
            self.assertTrue(decision["evidence_ids"])
            self.assertEqual({c["table"] for c in decision["changes"]}, {"papers.jsonl", "paper_registry.csv", "field_provenance.csv", "alias_map.csv"})
            self.assertEqual(data, before)
            # B's existing builder reads the changed metadata without stale IDs.
            write_snapshot(root, "data/processed/old_papers/s1", data)
            write_snapshot(root, "data/processed/new_papers/s1", audit.data)
            write_snapshot(root, "data/processed/new_metadata", audit.data)
            baseline = dict(project_id="mxh_cv_700", inputs=[dict(name="old", snapshots_dir="data/processed/old_papers", a3_dir=cfg["input_manifest"].rsplit("/", 1)[0])])
            changed = dict(project_id="mxh_cv_700", inputs=[dict(name="new", snapshots_dir="data/processed/new_papers", a3_dir="data/processed/new_metadata")])
            old_nodes, old_edges, *_ = build(baseline, root)
            new_nodes, new_edges, *_ = build(changed, root)
            self.assertEqual(next(n for n in new_nodes if n["label"] == "Paper")["properties_json"]["doi"], "10.1234/new")
            self.assertEqual([(e["src"], e["type"], e["dst"], e["weight"]) for e in old_edges], [(e["src"], e["type"], e["dst"], e["weight"]) for e in new_edges])

    def test_near_title_wrong_authors_preprint_doi_never_updates(self):
        for change in ({"title": ["A related title"]}, {"author": [{"given": "Other", "family": "Person"}]},
                       {"type": "posted-content"}, {"published": {"date-parts": [[2023]]}}, {"DOI": "10.1234/wrong"}):
            with self.subTest(change=change), temporary_workspace() as root:
                _, m, data, bodies = fixture(root, missing_doi=True)
                obs = observation(data, bodies, value=change)
                audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [obs])
                self.assertIsNone(audit.data["papers.jsonl"][0]["doi"])
                self.assertTrue(any(c["result"] == "unresolved" for c in audit.comparisons.values()))
                self.assertEqual(audit.data["merge_log.jsonl"], data["merge_log.jsonl"])

    def test_arxiv_same_paper_and_conference_date_byline_preserved(self):
        with temporary_workspace() as root:
            _, m, data, bodies = fixture(root)
            data["papers.jsonl"][0]["arxiv_url"] = "https://arxiv.org/abs/2401.12345"
            obs = observation(data, bodies, source="arXiv")
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [obs])
            c = next(c for c in audit.comparisons.values() if c["field_name"] == "arxiv_metadata")
            self.assertEqual(c["result"], "matched")
            self.assertEqual(len(audit.data["papers.jsonl"]), 1)
            self.assertEqual(audit.data["papers.jsonl"][0]["publication_date"], data["papers.jsonl"][0]["publication_date"])
            self.assertEqual(audit.data["authorships.csv"], data["authorships.csv"])

    def test_changed_preprint_authors_are_reviewed_not_unioned(self):
        with temporary_workspace() as root:
            _, m, data, bodies = fixture(root)
            data["papers.jsonl"][0]["arxiv_url"] = "https://arxiv.org/abs/2401.12345"
            obs = observation(data, bodies, source="arXiv", value=arxiv_body(names=("New, Person",)))
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [obs])
            self.assertTrue(any(c["result"] == "version_difference" for c in audit.comparisons.values()))
            self.assertEqual(audit.data["authorships.csv"], data["authorships.csv"])

    def test_lookup_preserves_explicit_preprint_version(self):
        with temporary_workspace() as root:
            cfg, _, data, bodies = fixture(root, missing_doi=True)
            data["papers.jsonl"][0]["arxiv_url"] = "https://arxiv.org/abs/2401.12345v1"
            self.assertEqual(lookup_plan(data, bodies, cfg)[0]["url"], "https://arxiv.org/abs/2401.12345v1")
            self.assertIsNone(arxiv_metadata(arxiv_body(aid="2401.12345"))["version"])
            self.assertEqual(arxiv_metadata(arxiv_body(aid="2401.12345v2"))["version"], "2401.12345v2")

    def test_wrong_or_unknown_preprint_revision_is_not_verified(self):
        for declared, expected in (("2401.12345v2", "conflict"), ("2401.12345", "unverified")):
            with self.subTest(declared=declared), temporary_workspace() as root:
                _, m, data, bodies = fixture(root)
                data["papers.jsonl"][0]["arxiv_url"] = "https://arxiv.org/abs/2401.12345v1"
                obs = observation(data, bodies, source="arXiv", value=arxiv_body(aid=declared))
                audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [obs])
                c = next(c for c in audit.comparisons.values() if c["field_name"] == "arxiv_metadata")
                self.assertEqual(c["result"], expected)

    def test_ambiguous_names_distinct_ids_never_merge(self):
        with temporary_workspace() as root:
            _, m, data, bodies = fixture(root)
            data["authorships.csv"][1]["author_name"] = data["authorships.csv"][0]["author_name"]
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [])
            self.assertTrue(any(c["field_name"] == "homonym_distinct_ids" for c in audit.comparisons.values()))
            self.assertEqual(audit.data["authorships.csv"], data["authorships.csv"])

    def test_multiple_affiliations_and_changed_employers_are_paper_scoped(self):
        with temporary_workspace() as root:
            _, m, data, bodies = fixture(root)
            sid = next(s["source_record_id"] for s in data["source_records.jsonl"] if s["source"] == "OpenAlex")
            work = json.loads(bodies[sid])
            work["authorships"][0]["institutions"].append(dict(id="https://openalex.org/I99", display_name="Another University", ror=None))
            bodies[sid] = json_bytes(work)
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [])
            self.assertEqual(audit.data["authorships.csv"], data["authorships.csv"])
            self.assertTrue(any(c["field_name"] == "paper_affiliations" and c["result"] == "unresolved" for c in audit.comparisons.values()))

    def test_institution_alias_same_id_does_not_change_or_create_node(self):
        with temporary_workspace() as root:
            _, m, data, bodies = fixture(root)
            sid = next(s["source_record_id"] for s in data["source_records.jsonl"] if s["source"] == "OpenAlex")
            work = json.loads(bodies[sid])
            work["authorships"][0]["institutions"][0]["display_name"] = "Alternate Institute Name"
            bodies[sid] = json_bytes(work)
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [])
            self.assertEqual(audit.data["nodes.csv"], data["nodes.csv"])
            self.assertTrue(any(c["field_name"] == "institution_identity" and c["result"] == "matched" for c in audit.comparisons.values()))

    def test_invalid_institution_ror_is_reviewed(self):
        with temporary_workspace() as root:
            _, m, data, bodies = fixture(root)
            sid = next(s["source_record_id"] for s in data["source_records.jsonl"] if s["source"] == "OpenAlex")
            work = json.loads(bodies[sid])
            work["authorships"][0]["institutions"][0]["ror"] = "https://ror.org/invalid"
            bodies[sid] = json_bytes(work)
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [])
            self.assertTrue(any(c["field_name"] == "institution_identity" and c["result"] == "conflict" for c in audit.comparisons.values()))
            self.assertEqual(audit.data["nodes.csv"], data["nodes.csv"])

    def test_same_author_different_years_keeps_each_papers_institution(self):
        with temporary_workspace() as first, temporary_workspace() as second:
            _, m1, d1, b1 = fixture(first, "CVPR", institution_offset=0)
            _, m2, d2, b2 = fixture(second, "ICCV", institution_offset=100)
            a1 = crosscheck(d1, b1, m1["snapshot_id"], STAMP, [])
            a2 = crosscheck(d2, b2, m2["snapshot_id"], STAMP, [])
            row1, row2 = a1.data["authorships.csv"][0], a2.data["authorships.csv"][0]
            self.assertEqual(row1["author_id"], row2["author_id"])
            self.assertNotEqual(row1["institution_id"], row2["institution_id"])
            self.assertEqual(a1.data["authorships.csv"], d1["authorships.csv"])
            self.assertEqual(a2.data["authorships.csv"], d2["authorships.csv"])

    def test_unavailable_lookup_does_not_fabricate_source_or_resolve_review(self):
        with temporary_workspace() as root:
            _, m, data, bodies = fixture(root)
            item = dict(paper_id=data["papers.jsonl"][0]["paper_id"], source="arXiv", url="https://arxiv.org/abs/2401.12345",
                        status="unavailable", reason="HTTP_403", source_record=None, network_requests=1)
            audit = crosscheck(data, bodies, m["snapshot_id"], STAMP, [item])
            self.assertEqual(audit.data["source_records.jsonl"], data["source_records.jsonl"])
            self.assertTrue(any(c["result"] == "unavailable" for c in audit.comparisons.values()))
            self.assertTrue(all(r["review_status"] == "open" for r in audit.data["needs_review.csv"]))


class CacheTest(unittest.TestCase):
    def test_source_cache_reuses_raw_and_no_duplicate_source(self):
        with temporary_workspace() as root:
            cfg, _, data, _ = fixture(root)
            item = dict(paper_id=data["papers.jsonl"][0]["paper_id"], source="arXiv", url="https://arxiv.org/abs/2401.12345")
            response = MagicMock()
            response.__enter__.return_value = response
            response.status = 200
            response.geturl.return_value = item["url"]
            response.read.return_value = arxiv_body()
            response.headers = {"Content-Type": "text/html"}
            with patch("src.metadata.sources.urlopen", return_value=response) as request:
                first = SupplementalCache(root, cfg, offline=False).fetch(item)
                second = SupplementalCache(root, cfg, offline=True).fetch(item)
                self.assertEqual(first, second)
                self.assertEqual(request.call_count, 1)
            path = root / first["source_record"]["raw_path"]
            path.write_bytes(gzip.compress(b"changed", mtime=0))
            with self.assertRaisesRegex(ValueError, "hash/status"):
                SupplementalCache(root, cfg).fetch(item)

    def test_429_checkpoint_prevents_repeated_requests(self):
        with temporary_workspace() as root:
            cfg, _, data, _ = fixture(root)
            item = dict(paper_id=data["papers.jsonl"][0]["paper_id"], source="arXiv", url="https://arxiv.org/abs/2401.12345")
            error = HTTPError(item["url"], 429, "limit", {}, None)
            with patch("src.metadata.sources.urlopen", side_effect=error) as request:
                cache = SupplementalCache(root, cfg, offline=False)
                self.assertEqual(cache.fetch(item)["status"], "unavailable")
                self.assertEqual(cache.fetch(item)["status"], "unavailable")
                self.assertEqual(request.call_count, 1)

    def test_offline_cache_miss_is_unverified_and_url_allowlist(self):
        with temporary_workspace() as root:
            cfg, _, data, _ = fixture(root)
            cache = SupplementalCache(root, cfg)
            request = dict(paper_id=data["papers.jsonl"][0]["paper_id"], source="arXiv", url="https://arxiv.org/abs/2401.12345")
            self.assertEqual(cache.fetch(request)["status"], "unverified")
            for url in ("https://evil.example/abs/2401.12345", "https://arxiv.org/abs/2401.12345?token=secret"):
                with self.assertRaises(ValueError):
                    cache.fetch({**request, "url": url})


class IntegrationTest(unittest.TestCase):
    def test_contract_replay_idempotency_and_b_exporter_in_memory(self):
        with temporary_workspace() as root, patch("src.metadata.sources.urlopen", side_effect=AssertionError("network forbidden")):
            cfg, _, data, _ = fixture(root)
            original_bytes = {(root / s["raw_path"]): (root / s["raw_path"]).read_bytes() for s in data["source_records.jsonl"]}
            first = run(root, "config/a5.json")
            self.assertEqual(first, run(root, "config/a5.json"))
            self.assertTrue(verify(root, "config/a5.json")["passed"])
            self.assertFalse(first["graph_ready"])
            old = dict(name="old", a3_dir=cfg["input_manifest"].rsplit("/", 1)[0], snapshots_dir="data/processed/old_papers")
            write_snapshot(root, old["snapshots_dir"] + "/s1", data)
            graph = dict(project_id="mxh_cv_700", inputs=[old])
            n1, e1, *_ = build(graph, root)
            graph["inputs"] = [exporter_input(cfg)]
            n2, e2, *_ = build(graph, root)
            self.assertEqual(n1, n2)
            self.assertEqual([(e["src"], e["type"], e["dst"], e["weight"]) for e in e1], [(e["src"], e["type"], e["dst"], e["weight"]) for e in e2])
            self.assertEqual(original_bytes, {p: p.read_bytes() for p in original_bytes})
            self.assertFalse((root / "graph").exists())

    def test_bad_raw_or_table_hash_fails_before_publication(self):
        with temporary_workspace() as root:
            cfg, _, data, _ = fixture(root)
            path = root / data["source_records.jsonl"][0]["raw_path"]
            path.write_bytes(gzip.compress(b"corrupt", mtime=0))
            with self.assertRaisesRegex(ValueError, "hash/identity"):
                run(root, "config/a5.json")
            self.assertFalse((root / cfg["processed_dir"]).exists())

    def test_iccv_config_and_output_scope(self):
        with temporary_workspace() as root:
            cfg, _, _, _ = fixture(root, conference="ICCV")
            self.assertEqual(run(root, "config/a5.json")["papers_reviewed"], 1)
            cfg["processed_dir"] = "data/processed/iccv2023/a3/nested"
            (root / "config/a5.json").write_bytes(json_bytes(cfg))
            with self.assertRaisesRegex(ValueError, "overlaps"):
                load(root, "config/a5.json")

    def test_comparison_and_manifest_tampering_rejected(self):
        with temporary_workspace() as root:
            cfg, _, _, _ = fixture(root)
            run(root, "config/a5.json")
            path = root / cfg["processed_dir"] / "metadata_comparison.csv"
            path.write_bytes(path.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "differs from replay"):
                verify(root, "config/a5.json")
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                run(root, "config/a5.json")


if __name__ == "__main__":
    unittest.main()
