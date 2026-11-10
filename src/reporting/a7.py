"""A7 statistics and figures; reuse Contract/A6 validators, never rebuild data."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from src.collect.common import REPO_ROOT, within, json_bytes
from src.collect.contract import contract, validate_records
from src.clean.normalize import doi, arxiv, openalex
from src.clean.text import sha256, validate_nlp_evidence, canonical_json
from src.nlp.validation import read_manifest, verify_graph_contract, validate_nlp, TABLES
from src.audit.pipeline import CODE_VERSION as AUDIT_VERSION, EDGE_FILE, NODE_FILE
from src.audit.sampling import decode_csv, form_fingerprint, human_summary

VERSION = "a7-report-1.0.0"
DEFAULT_CONFIG = "config/a7_report.json"
NLP_TYPES = ("STUDIES_TASK", "EVALUATED_ON", "USES_METHOD")


def ratio(numerator, denominator):
    """Unavailable/empty populations have no percentage, rather than 0%."""
    if not 0 <= numerator <= denominator:
        raise ValueError("Invalid numerator/denominator")
    return dict(numerator=numerator, denominator=denominator,
                percent=round(100 * numerator / denominator, 2) if denominator else None,
                missing=denominator - numerator,
                missing_percent=round(100 * (denominator - numerator) / denominator, 2) if denominator else None)


def coverage_metrics(papers, groups):
    return {
        "doi": ratio(sum(doi(p["doi"]) is not None for p in papers), len(papers)),
        "abstract": ratio(sum(bool((p["abstract"] or "").strip()) for p in papers), len(papers)),
        "openalex_id": ratio(sum(openalex(p["openalex_id"], "W") is not None for p in papers), len(papers)),
        "arxiv_id": ratio(sum(arxiv(p["arxiv_url"]) is not None for p in papers), len(papers)),
        "author_id": ratio(sum(any(r["author_id"] for r in rows) for rows in groups.values()), len(groups)),
        "affiliation": ratio(sum(any(r["institution_id"] and r["affiliation_status"] == "verified" for r in rows)
                                 for rows in groups.values()), len(groups)),
    }


def corpus_metrics(data, scope):
    papers, registry = data["papers.jsonl"], data["paper_registry.csv"]
    ids = {p["paper_id"] for p in papers}
    if len(ids) != len(papers) or ids != {p["paper_id"] for p in registry} or len(ids) != len(registry):
        raise ValueError("Paper/registry membership is duplicated or inconsistent")
    if any((p["owner"], p["conference"], p["conference_year"], p["scope"], p["track"]) !=
           (scope["owner"], scope["conference"], scope["year"], "core", "main") for p in papers):
        raise ValueError("Corpus contains papers outside its assigned core/main scope")
    if any(r["status"] != "cvf_verified" for r in registry):
        raise ValueError("Registry contains an unverified core paper")
    groups = defaultdict(list)
    for a in data["authorships.csv"]:
        groups[a["authorship_id"]].append(a)
    expected = {a["authorship_id"] for p in papers for a in p["authors"]}
    if set(groups) != expected:
        raise ValueError("Authorship membership differs from the ordered paper bylines")
    authors = {a["author_id"] for a in data["authorships.csv"] if a["author_id"]}
    institutions = {a["institution_id"] for a in data["authorships.csv"] if a["institution_id"]}
    for label, found in (("Author", authors), ("Institution", institutions)):
        if found != {n["id"] for n in data["nodes.csv"] if n["label"] == label}:
            raise ValueError("Resolved corpus entities disagree with authorships: " + label)
    coverage = coverage_metrics(papers, groups)
    # Exact external identifiers cannot be silently counted as different core papers.
    collisions = {}
    for field, normalize in (("doi", doi), ("openalex_id", lambda x: openalex(x, "W")),
                             ("arxiv_url", arxiv), ("cvf_url", lambda x: x)):
        claimed = defaultdict(set)
        for p in papers:
            key = normalize(p[field])
            if key:
                claimed[key].add(p["paper_id"])
        collisions[field] = sum(len(v) > 1 for v in claimed.values())
    if any(collisions.values()):
        raise ValueError("Paper external identifiers conflict; no deduplicated total may be published")
    return dict(status="available", owner=scope["owner"], conference=scope["conference"], year=scope["year"],
        target=scope["target"], valid_core_papers=len(ids), target_met=len(ids) == scope["target"],
        reference_papers=0, distinct_authors=len(authors), distinct_institutions=len(institutions),
        distinct_authorships=len(groups), authorship_rows=len(data["authorships.csv"]), coverage=coverage,
        missing_institution_authorships=sum(not any(r["institution_id"] for r in rows) for rows in groups.values()),
        unverified_affiliation_authorships=len(groups) - coverage["affiliation"]["numerator"],
        null_institution_rows=sum(not a["institution_id"] for a in data["authorships.csv"]),
        multi_institution_authorships=sum(len({r["institution_id"] for r in rows if r["institution_id"]}) > 1 for rows in groups.values()),
        open_reviews=sum(r["review_status"] == "open" for r in data["needs_review.csv"]),
        source_records=len(data.get("source_records.jsonl", [])),
        sources_by_source=dict(sorted(Counter(r["source"] for r in data.get("source_records.jsonl", [])).items())),
        reviews_by_status=dict(sorted(Counter(r["review_status"] for r in data["needs_review.csv"]).items())),
        canonical_decisions=dict(sorted(Counter(r["action"] for r in data["merge_log.jsonl"]).items())),
        duplicate_identifier_groups=collisions)


def combined_metrics(datasets, graph):
    """Only aggregate a verified graph matching every selected corpus, using ID sets."""
    paper_sets = [{p["paper_id"] for p in d["papers.jsonl"]} for d in datasets]
    union = set().union(*paper_sets)
    if sum(map(len, paper_sets)) != len(union):
        raise ValueError("Core Paper membership overlaps between corpora")
    gp = {p["paper_id"]: p for p in graph["papers.jsonl"]}
    if set(gp) != union:
        return dict(status="PENDING_B", reason="Graph Paper membership differs from the selected corpora")
    for d in datasets:
        if any(gp[p["paper_id"]] != p for p in d["papers.jsonl"]):
            return dict(status="PENDING_B", reason="Graph metadata must be rebound to the selected corpus snapshot")
    actual = {canonical_json(a) for a in graph["authorships.csv"]}
    expected = {canonical_json(a) for d in datasets for a in d["authorships.csv"]}
    if actual != expected:
        return dict(status="PENDING_B", reason="Graph authorships differ from the selected corpus snapshots")
    # Reject scalar identity disagreements and cross-corpus DOI/Work/arXiv collisions.
    props = defaultdict(set)
    for d in datasets:
        for n in d["nodes.csv"]:
            for f in ("openalex_id", "orcid", "ror", "country_code"):
                if n["properties_json"].get(f):
                    props[(n["id"], f)].add(n["properties_json"][f])
    if any(len(v) > 1 for v in props.values()):
        return dict(status="PENDING_B", reason="Conflicting scalar identifiers on shared canonical nodes")
    for field, normalizer in (("doi", doi), ("openalex_id", lambda x: openalex(x, "W")), ("arxiv_url", arxiv)):
        claims = defaultdict(set)
        for p in gp.values():
            if key := normalizer(p[field]):
                claims[key].add(p["paper_id"])
        if any(len(v) > 1 for v in claims.values()):
            raise ValueError("Cross-corpus Paper identifier collision: " + field)
    labels = Counter(n["label"] for n in graph["nodes.csv"])
    shared = {}
    for label in ("Author", "Institution"):
        sets = [{n["id"] for n in d["nodes.csv"] if n["label"] == label} for d in datasets]
        merged = set().union(*sets)
        if merged != {n["id"] for n in graph["nodes.csv"] if n["label"] == label}:
            raise ValueError("Graph entity union differs from the resolved corpus IDs")
        shared[label] = sum(map(len, sets)) - len(merged)
    groups = defaultdict(list)
    for a in graph["authorships.csv"]:
        groups[a["authorship_id"]].append(a)
    return dict(status="available", core_papers=len(union), reference_papers=0,
        distinct_authors=labels["Author"], distinct_institutions=labels["Institution"],
        distinct_authorships=len(groups), coverage=coverage_metrics(list(gp.values()), groups),
        shared_canonical_ids=shared, identity_semantics_fully_reviewed=False)


def audit_metrics(root, config_path):
    """Read A6 receipts/forms without invoking its writer or inventing human votes."""
    cfg = json.loads(within(root, config_path).read_text(encoding="utf-8"))
    out = within(root, cfg["output_dir"])
    if not (out / "a6_run_manifest.json").exists():
        return dict(status="PENDING_B", reason="A6 audit receipts/forms are unavailable")
    run = json.loads((out / "a6_run_manifest.json").read_text(encoding="utf-8"))
    if run["code_version"] != AUDIT_VERSION or run["config_sha256"] != sha256(within(root, config_path).read_bytes()):
        return dict(status="stale", reason="A6 config/code changed; retain the earlier audit separately")
    for name, digest in run["input_files_sha256"].items():
        if not within(root, name).exists() or sha256(within(root, name).read_bytes()) != digest:
            return dict(status="stale", reason="A6 input changed: " + name)
    body = (out / "a6_automatic_report.json").read_bytes()
    if sha256(body) != run["automatic_report_sha256"]:
        raise ValueError("A6 automatic report fingerprint mismatch")
    edges, nodes = [decode_csv((out / name).read_bytes()) for name in (EDGE_FILE, NODE_FILE)]
    if (form_fingerprint(edges), form_fingerprint(nodes)) != (run["edge_form_fingerprint"], run["node_form_fingerprint"]):
        raise ValueError("A6 immutable form fields/sample membership changed")
    auto, human = json.loads(body), human_summary(edges, nodes)
    issues = decode_csv((out / "a6_review_issues.csv").read_bytes())
    if dict(Counter(r["check_id"] for r in issues)) != auto["issue_counts_by_check"]:
        raise ValueError("A6 issue counts no longer match the automatic report")
    return dict(status="available", graph_snapshot_id=run["graph_snapshot_id"],
        automatic_checks_passed=auto["automatic_checks_passed"], confirmed_errors=auto["confirmed_errors"],
        issue_counts_by_check=auto["issue_counts_by_check"], issue_counts_by_kind=auto["issue_counts_by_kind"],
        corpora=auto["corpora"], graph=auto["graph"], human=human,
        neo4j=next(c["details"] for c in auto["checks"] if c["check_id"] == "neo4j_counts"))


def examples(graph, nlp):
    """Select traceable A examples; all displayed quotes are short source excerpts."""
    evs = {e["evidence_id"]: e for e in nlp["evidence.jsonl"]}
    texts = {t["text_version_id"]: t for t in graph["text_versions.jsonl"]}
    candidates = []
    for typ in NLP_TYPES[:2]:
        choices = [(e, evs[e["evidence_ids"][0]]) for e in nlp["edges.csv"] if e["type"] == typ
                   and evs[e["evidence_ids"][0]]["owner"] == "A"]
        if choices:
            e, v = min(choices, key=lambda item: (len(item[1]["evidence_text"]), item[0]["edge_id"]))
            candidates.append((typ, e["dst"], "accepted", e["edge_id"], v))
    for reason in ("prior_work_or_baseline", "training_or_mixed_roles"):
        choices = [r for r in nlp["needs_review.csv"] if r["entity_type"] == "Dataset" and r["reason"] == reason
                   and r["review_status"] == "rejected" and r["assigned_to"] == "A"]
        if choices:
            # Prefer an explicit pretraining mention to a mixed train/evaluate clause.
            r = min(choices, key=lambda r: (reason == "training_or_mixed_roles" and
                "pretrain" not in evs[r["evidence_ids"][0]]["evidence_text"].lower(),
                len(evs[r["evidence_ids"][0]]["evidence_text"]), r["review_id"]))
            candidates.append((reason, r["candidate_ids"][0], "rejected_by_rule", r["review_id"], evs[r["evidence_ids"][0]]))
    result = []
    names = {n["id"]: n["name"] for n in nlp["nodes.csv"]}
    for kind, entity, decision, record, e in candidates:
        validate_nlp_evidence(e, texts[e["text_version_id"]])
        words = e["evidence_text"].split()
        # Quote the pretraining portion, not an unrelated first half of the sentence.
        start = next((max(0, i - 2) for i, w in enumerate(words) if "pretrain" in w.lower()), 0) if kind == "training_or_mixed_roles" else 0
        excerpt = " ".join(words[start:start + 18])
        result.append(dict(kind=kind, entity_id=entity, entity_name=names.get(entity, entity), decision=decision, record_id=record,
            evidence_id=e["evidence_id"], paper_id=e["paper_id"], source_url=e["source_url"],
            text_version_id=e["text_version_id"], start_char=e["start_char"], end_char=e["end_char"],
            rule_id=e["rule_id"], rule_version=e["rule_version"], field_path=e["field_path"],
            excerpt=excerpt, excerpt_is_partial=start > 0 or len(words) > 18))
    return result


def collect(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    cfg = json.loads(within(root, config_path).read_text(encoding="utf-8"))
    bindings = {}
    def read_json(path):
        p = within(root, path)
        bindings[path] = sha256(p.read_bytes())
        return json.loads(p.read_text(encoding="utf-8"))
    def load(path, tables):
        m, d = read_manifest(root, path, tables)
        bindings[path] = sha256(within(root, path).read_bytes())
        for f in m["files"]:
            bindings[f["path"]] = f["sha256"]
        for name, rows in d.items():
            validate_records(name, rows)
        return m, d
    bindings[config_path] = sha256(within(root, config_path).read_bytes())
    for path in ("src/reporting/a7.py", "src/nlp/rules.py", "src/audit/sampling.py", "config/requirements_a7.txt", "config/contracts/v2/data_contract.json"):
        bindings[path] = sha256(within(root, path).read_bytes())
    stats, datasets, validation = {}, {}, {}
    for scope in cfg["corpora"]:
        owner = scope["owner"]
        if not within(root, scope["manifest"]).exists() and not scope["required"]:
            stats[owner] = dict(status="PENDING_B", owner=owner, conference=scope["conference"], year=scope["year"])
            continue
        m, data = load(scope["manifest"], contract()["files"])
        validation[owner] = verify_graph_contract(root, m)
        stats[owner] = corpus_metrics(data, scope)
        stats[owner].update(snapshot_id=m["snapshot_id"], manifest=scope["manifest"])
        clean_cfg = read_json(scope["clean_config"])
        clean = read_json(clean_cfg["processed_dir"] + "/cleaning_summary.json")
        # Verify historical cleaning counters against the selected canonical tables.
        clean_manifest = read_json(clean_cfg["processed_dir"] + "/snapshot_manifest.json")
        if clean["snapshot_id"] != clean_manifest["snapshot_id"] or any(clean[k] != stats[owner][k] for k in
                ("valid_core_papers", "distinct_authorships")):
            raise ValueError("Cleaning summary differs from its bound corpus")
        input_manifest, input_data = load(clean_cfg["input_manifest"], contract()["files"])
        if clean["source_snapshot_id"] != input_manifest["snapshot_id"] or clean["input_papers"] != len(input_data["papers.jsonl"]) or clean["output_papers"] != len(data["papers.jsonl"]):
            raise ValueError("Cleaning input/output counters differ from actual source records")
        stats[owner]["cleaning"] = {k: clean[k] for k in ("input_papers", "output_papers", "duplicate_papers_removed", "dropped_papers", "papers_with_identifier_conflicts", "decision_counts")}
        datasets[owner] = data
    graph, gm = None, None
    if within(root, cfg["graph_manifest"]).exists():
        gm, graph = load(cfg["graph_manifest"], contract()["files"])
        if gm["graph_ready"] is not True:
            raise ValueError("Configured graph is not graph_ready")
        validation["graph"] = verify_graph_contract(root, gm)
    combined = combined_metrics(list(datasets.values()), graph) if graph and len(datasets) == len(cfg["corpora"]) else dict(status="PENDING_B", reason="Complete corpus/graph inputs are not available")
    graph_stats = dict(status="available", snapshot_id=gm["snapshot_id"], manifest=cfg["graph_manifest"],
        nodes=len(graph["nodes.csv"]), edges=len(graph["edges.csv"]),
        counts_by_label=dict(sorted(Counter(n["label"] for n in graph["nodes.csv"]).items())),
        counts_by_type=dict(sorted(Counter(e["type"] for e in graph["edges.csv"]).items())),
        open_reviews=sum(r["review_status"] == "open" for r in graph["needs_review.csv"])) if graph else dict(status="PENDING_B")
    nlp_cfg = read_json(cfg["nlp_config"])
    dictionary = read_json(nlp_cfg["dictionary"])
    nlp_stats = dict(status="PENDING_B", dictionary_version=dictionary["version"],
                     dictionary_sizes={label: len(dictionary[key]) for label, key in (("Task", "tasks"), ("Dataset", "datasets"))})
    example_rows = []
    nlp_path = nlp_cfg["output_dir"] + "/snapshot_manifest.json"
    if graph and within(root, nlp_path).exists():
        nm, nlp = load(nlp_path, TABLES)
        dictionaries = {"a4-cv": dictionary}
        if nlp_cfg.get("method_dictionary"):
            dictionaries["b5-method"] = read_json(nlp_cfg["method_dictionary"])
        versions = {k: d["version"] + ":" + sha256(canonical_json(d).encode()) for k, d in dictionaries.items()}
        if versions != nm["dictionary_versions"]:
            raise ValueError("Configured dictionaries differ from the NLP snapshot")
        validate_nlp(nlp, graph)
        if all(within(root, p).exists() for p in nlp_cfg["input_manifests"]):
            from src.nlp.verify import verify as verify_nlp
            validation["nlp_replay"] = verify_nlp(root, cfg["nlp_config"])
        ge = {e["edge_id"]: e for e in graph["edges.csv"]}
        if any(ge.get(e["edge_id"]) != e for e in nlp["edges.csv"]):
            raise ValueError("NLP edges differ from the configured graph")
        paper_map = {p["paper_id"]: p for p in graph["papers.jsonl"]}
        nlp_stats.update(status="available", snapshot_id=nm["snapshot_id"], manifest=nlp_path,
                         dictionary_versions=nm["dictionary_versions"], runtime=nm["parser_versions"], by_corpus={})
        for scope in cfg["corpora"]:
            es = [e for e in nlp["edges.csv"] if paper_map[e["src"]]["owner"] == scope["owner"]]
            nlp_stats["by_corpus"][scope["owner"]] = {
                typ: dict(edges=sum(e["type"] == typ for e in es),
                    unique_entities=len({e["dst"] for e in es if e["type"] == typ}),
                    papers=len({e["src"] for e in es if e["type"] == typ})) for typ in NLP_TYPES}
        nlp_stats["counts_by_type"] = dict(sorted(Counter(e["type"] for e in nlp["edges.csv"]).items()))
        nlp_stats["counts_by_label"] = dict(sorted(Counter(n["label"] for n in nlp["nodes.csv"]).items()))
        a4_reviews = [r for r in nlp["needs_review.csv"] if r["entity_type"] in ("Task", "Dataset")]
        nlp_stats["task_dataset_reviews_by_status"] = dict(Counter(r["review_status"] for r in a4_reviews))
        example_rows = examples(graph, nlp)
    audit = audit_metrics(root, cfg["audit_config"])
    audit_cfg = read_json(cfg["audit_config"])
    for name in ("a6_run_manifest.json", "a6_automatic_report.json", "a6_review_issues.csv", EDGE_FILE, NODE_FILE):
        path = audit_cfg["output_dir"] + "/" + name
        if within(root, path).exists():
            bindings[path] = sha256(within(root, path).read_bytes())
    if audit["status"] == "available":
        if not gm or audit["graph_snapshot_id"] != gm["snapshot_id"] or any(
                audit["corpora"].get(o, {}).get(k) != stats[o][k] for o in datasets
                for k in ("valid_core_papers", "distinct_authorships", "missing_institution_authorships", "open_reviews")):
            audit = dict(status="stale", reason="A6 must be rerun on the newly selected corpus/graph snapshots")
    return dict(code_version=VERSION, config=config_path, corpora=stats, combined=combined,
        graph=graph_stats, nlp=nlp_stats, examples=example_rows, audit=audit,
        validation=validation, input_files_sha256=dict(sorted(bindings.items())),
        pending_b=["PENDING_B: B6 NetworkX, phân tích cấu trúc và case study (ngoài phạm vi A7)",
                   "PENDING_B: B7 chấm/đọc chéo, phân xử audit cùng A; hoàn thiện phần báo cáo B",
                   "PENDING_B: chốt snapshot/Neo4j và báo cáo nhóm ở A8/B8"])


def rate(v):
    return "—" if v["percent"] is None else f"{v['numerator']}/{v['denominator']} ({v['percent']:.2f}%)"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|", *[
        "| " + " | ".join(str(v).replace("|", "/").replace("\n", " ") for v in row) + " |" for row in rows]])


def report_blocks(m):
    corpora = m["corpora"]
    def value(owner, key):
        s = corpora[owner]
        return s[key] if s["status"] == "available" else "PENDING_B"
    owners = list(corpora)
    names = [f"{s['conference']} {s['year']} ({o})" for o, s in corpora.items()]
    blocks = {}
    blocks["corpora"] = table(["Chỉ tiêu (đơn vị)", *names], [[label, *[value(o, key) for o in owners]] for key, label in (
        ("valid_core_papers", "Paper core hợp lệ (bài)"), ("distinct_authors", "Author có ID duy nhất (nút)"),
        ("distinct_institutions", "Institution có ID duy nhất (nút)"), ("distinct_authorships", "Lượt đứng tên (authorship_id)"),
        ("authorship_rows", "Dòng authorship × affiliation"), ("open_reviews", "needs_review đang mở (hồ sơ)"))])
    blocks["coverage"] = table(["Trường thiếu / mẫu số", *names], [[label, *[
        rate(ratio(corpora[o]["coverage"][key]["missing"], corpora[o]["coverage"][key]["denominator"]))
        if corpora[o]["status"] == "available" else "PENDING_B" for o in owners]] for key, label in (
            ("doi", "Thiếu DOI / Paper"), ("abstract", "Thiếu abstract / Paper"), ("openalex_id", "Thiếu OpenAlex Work ID / Paper"),
            ("arxiv_id", "Thiếu liên kết arXiv hợp lệ / Paper"), ("author_id", "Thiếu Author ID / lượt đứng tên"),
            ("affiliation", "Chưa có Institution xác minh / lượt đứng tên"))])
    blocks["dedup"] = table(["Phép đếm khử trùng", *names], [[label, *[
        corpora[o]["cleaning"][key] if corpora[o]["status"] == "available" else "PENDING_B" for o in owners]] for key, label in (
            ("duplicate_papers_removed", "Paper trùng bị loại ở A3"), ("papers_with_identifier_conflicts", "Paper xung đột định danh ở A3"))])
    c = m["combined"]
    blocks["combined"] = (f"Graph đã đối chiếu membership và canonical metadata có **{c['core_papers']} Paper core, {c['distinct_authors']} Author, "
        f"{c['distinct_institutions']} Institution và {c['distinct_authorships']} lượt đứng tên**. Không có Paper reference được nhập. "
        f"Hai corpus dùng chung {c['shared_canonical_ids']['Author']} Author ID và {c['shared_canonical_ids']['Institution']} Institution ID. "
        "Đây là số ID trong snapshot, chưa phải chứng nhận mọi danh tính đã được con người phân giải đúng.") if c["status"] == "available" else "**PENDING_B:** " + c["reason"] + ". Chưa công bố tổng toàn nhóm."
    n = m["nlp"]
    blocks["nlp"] = "PENDING_B: chưa có bảng NLP được kiểm tra binding với graph."
    if n["status"] == "available":
        rows = []
        for typ, label in (("STUDIES_TASK", "Task"), ("EVALUATED_ON", "Dataset")):
            rows.append([typ, *[f"{n['by_corpus'][o][typ]['edges']} cạnh; {n['by_corpus'][o][typ]['unique_entities']} {label}; {n['by_corpus'][o][typ]['papers']} bài" for o in owners],
                         f"{n['counts_by_type'].get(typ, 0)} cạnh; {n['counts_by_label'].get(label, 0)} {label}"])
        blocks["nlp"] = table(["Quan hệ", *names, "Union ID trong graph"], rows) + (
            f"\n\nTừ điển `{n['dictionary_version']}` gồm {n['dictionary_sizes']['Task']} Task và {n['dictionary_sizes']['Dataset']} Dataset. "
            f"Review riêng Task/Dataset: {n['task_dataset_reviews_by_status'].get('open', 0)} mở, "
            f"{n['task_dataset_reviews_by_status'].get('rejected', 0)} bị luật loại; không tính các hồ sơ này thành cạnh accepted.")
    rows = []
    for i, e in enumerate(m["examples"], 1):
        quote = ("… " if e["kind"] == "training_or_mixed_roles" else "") + e["excerpt"] + (" …" if e["excerpt_is_partial"] else "")
        decision = "Nhận " + e["kind"] if e["decision"] == "accepted" else "Loại: " + (
            "baseline/nghiên cứu trước" if e["kind"] == "prior_work_or_baseline" else "training/pretraining")
        rows.append([i, f"[{e['entity_name']}]({e['source_url']})", quote,
            f"{decision}; {e['rule_id']} v{e['rule_version']}; [{e['start_char']},{e['end_char']})"])
    blocks["examples"] = table(["Ví dụ", "Đối tượng / nguồn CVF", "Trích đoạn nguyên văn", "Quyết định máy / offset cả câu"], rows) if rows else "PENDING_B: chưa có evidence để minh họa."
    g = m["graph"]
    blocks["graph"] = "PENDING_B: chưa có graph contract hợp lệ."
    if g["status"] == "available":
        blocks["graph"] = f"Snapshot CSV đã qua Contract v2: **{g['nodes']} node, {g['edges']} cạnh duy nhất**, {len(g['counts_by_label'])} nhãn node, {len(g['counts_by_type'])} loại quan hệ. "
        if c["status"] != "available":
            blocks["graph"] += "**Graph này chưa khớp dữ liệu corpus mới; số dưới chỉ mô tả snapshot cũ, chưa phải tổng nhóm mới.** "
        blocks["graph"] += "\n\n" + table(["Nhãn node", "Số nút", "Quan hệ", "Số cạnh"], [
            [*(list(g["counts_by_label"].items())[i] if i < len(g["counts_by_label"]) else ("", "")),
             *(list(g["counts_by_type"].items())[i] if i < len(g["counts_by_type"]) else ("", ""))]
            for i in range(max(len(g["counts_by_label"]), len(g["counts_by_type"])))])
    a = m["audit"]
    blocks["quality"] = f"A6: **{a['status']}**. " + a.get("reason", "")
    if a["status"] == "available":
        h = a["human"]
        blocks["quality"] = table(["Nhóm phát hiện A6", "Số hồ sơ", "Cách diễn giải"], [
            ["Review mở đã có (dedupe review_id)", a["issue_counts_by_kind"].get("known_review", 0), "Chưa giải quyết; không đồng nghĩa lỗi đã xác nhận"],
            ["CITES: evidence chưa chỉ đúng reference field", a["issue_counts_by_check"].get("citation_evidence_specificity", 0), "Cần B tăng độ cụ thể bằng chứng; chưa kết luận trích dẫn sai"],
            ["Tên chuẩn hóa trùng nhưng ID khác", a["issue_counts_by_check"].get("homonym", 0), "Có thể là người/tổ chức khác nhau"],
            ["Alias định danh dùng cho nhiều canonical ID", a["issue_counts_by_check"].get("shared_identifier", 0), "Giữ cách ly alias; A/B phân xử"],
            ["Ngữ cảnh NLP cần đọc lại", a["issue_counts_by_check"].get("nlp_context_risk", 0), "Cảnh báo, chưa tự sửa cạnh"],
            ["Lỗi tự động được xác nhận trong phạm vi checks", a["confirmed_errors"], "Không phải phép đo độ chính xác ngữ nghĩa"]])
        blocks["quality"] += (f"\n\nKiểm tra máy bắt buộc qua: `{a['automatic_checks_passed']}`. "
            f"Mẫu primary đã chấm {h['primary']['graded']}/{h['primary']['total']}; đọc chéo {h['cross']['graded']}/{h['cross']['total']}; "
            f"node rủi ro {h['nodes']['graded']}/{h['nodes']['total']}. "
            + ("Precision **chưa xác định** (`null`), không công bố >90%." if h['primary']['conservative_precision'] is None else
               f"Precision bảo thủ của primary đã chấm: {100*h['primary']['conservative_precision']:.2f}% ({h['primary']['correct']}/{h['primary']['graded']}), chưa suy rộng toàn graph.")
            + f" Neo4j live: `{a['neo4j']['status']}`; trạng thái này tách khỏi kiểm tra CSV/offline.")
    blocks["bindings"] = table(["Phạm vi", "Manifest / SHA-256 snapshot (12 ký tự đầu)"], [[o, f"[Manifest {s['conference']}](../{s['manifest']}); `{s['snapshot_id'].rsplit(':', 1)[-1][:12]}`"]
        if s["status"] == "available" else [o, "PENDING_B"] for o, s in corpora.items()] +
        ([["Graph B5", f"[Manifest graph](../{g['manifest']}); `{g['snapshot_id'].rsplit(':', 1)[-1][:12]}`"]] if g["status"] == "available" else []))
    blocks["pending"] = "\n".join("- " + s for s in m["pending_b"])
    return blocks


def render_report(text, metrics):
    """Only replace machine blocks; preserve the report's human-written prose."""
    for key, body in report_blocks(metrics).items():
        body = "\n".join(line.rstrip() for line in body.splitlines())
        pattern = re.compile(r"(<!-- A7:" + key + r":BEGIN -->).*?(<!-- A7:" + key + r":END -->)", re.S)
        if len(pattern.findall(text)) != 1:
            raise ValueError("Missing/duplicate report marker: " + key)
        text = pattern.sub(lambda match: match[1] + "\n\n" + body + "\n\n" + match[2], text)
    return text


def figures(metrics, folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.hashsalt": VERSION})
    available = [(o, s) for o, s in metrics["corpora"].items() if s["status"] == "available"]
    if not available:
        raise ValueError("No verified corpus for figures")
    fig, axes = plt.subplots(1, len(available), figsize=(10.4, 4.1), squeeze=False, layout="constrained")
    keys = ["doi", "abstract", "openalex_id", "arxiv_id", "author_id", "affiliation"]
    labels = ["DOI / bài", "Abstract / bài", "OpenAlex ID / bài", "arXiv ID / bài", "Author ID / lượt đứng tên", "Affiliation / lượt đứng tên"]
    for ax, (_, s) in zip(axes[0], available):
        values = [s["coverage"][key]["percent"] for key in keys]
        ax.barh(range(len(keys)), values, color="#226A87", label="Có / đã resolve")
        ax.barh(range(len(keys)), [100 - v for v in values], left=values, color="#DBE4E8", label="Thiếu / chưa resolve")
        for i, key in enumerate(keys):
            v = s["coverage"][key]
            ax.text(2, i, f"{v['numerator']}/{v['denominator']} · {v['percent']:.1f}%", va="center", color="white", fontsize=9)
        ax.set(yticks=range(len(keys)), yticklabels=labels, xlim=(0, 100), xlabel="Tỷ lệ (%)", title=f"{s['conference']} {s['year']}")
        ax.invert_yaxis()
        ax.spines[["top", "right"]].set_visible(False)
    fig.legend(*axes[0, 0].get_legend_handles_labels(), loc="outside lower center", ncol=2, frameon=False)
    save_figure(fig, folder / "metadata_coverage", plt)
    fig, ax = plt.subplots(figsize=(8.2, 3.5), layout="constrained")
    nlp = metrics["nlp"]
    if nlp["status"] == "available":
        width = 0.7 / len(available)
        for i, (o, s) in enumerate(available):
            vals = [nlp["by_corpus"][o][typ]["edges"] for typ in NLP_TYPES[:2]]
            bars = ax.bar([x - .35 + width / 2 + width * i for x in range(2)], vals, width,
                          color=["#226A87", "#D98630"][i % 2], label=f"{s['conference']} {s['year']}")
            ax.bar_label(bars, padding=3)
        ax.set(xticks=range(2), xticklabels=NLP_TYPES[:2], ylabel="Số cạnh accepted duy nhất", ylim=(0, max(1, max(
            nlp['by_corpus'][o][t]['edges'] for o, _ in available for t in NLP_TYPES[:2])) * 1.2))
        ax.legend(frameon=False)
    else:
        ax.text(.5, .5, "PENDING_B: chưa có NLP được kiểm tra", ha="center", transform=ax.transAxes)
        ax.set_axis_off()
    ax.spines[["top", "right"]].set_visible(False)
    save_figure(fig, folder / "nlp_relations", plt)


def save_figure(fig, stem, plt):
    # Fixed metadata and SVG salt make reruns stable within the pinned runtime.
    fig.savefig(stem.with_suffix(".png"), dpi=300, metadata={"Software": VERSION})
    fig.savefig(stem.with_suffix(".svg"), metadata={"Date": None, "Creator": VERSION})
    plt.close(fig)


def run(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    cfg = json.loads(within(root, config_path).read_text(encoding="utf-8"))
    out, report = within(root, cfg["output_dir"]), within(root, cfg["report"])
    if not out.is_relative_to(within(root, "outputs")) or not report.is_relative_to(within(root, "report")):
        raise ValueError("Reporting may only write under outputs/ and report/")
    m = collect(root, config_path)
    body = render_report(report.read_text(encoding="utf-8"), m).encode("utf-8")
    folder = out / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    figures(m, folder)
    (out / "metrics.json").write_bytes(json_bytes(m))
    report.write_bytes(body)
    return dict(status="completed", corpora={o: s.get("valid_core_papers", "PENDING_B") for o, s in m["corpora"].items()},
                combined=m["combined"], report=cfg["report"], metrics=cfg["output_dir"] + "/metrics.json")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=REPO_ROOT)
    p.add_argument("--config", default=DEFAULT_CONFIG)
    args = p.parse_args()
    try:
        result = run(args.root, args.config)
    except (ValueError, OSError, KeyError) as exc:
        p.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
