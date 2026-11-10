"""A6 read-only audit orchestration and bounded review artifacts."""
import importlib.util
import gzip
import json
from collections import Counter
from pathlib import Path

from src.collect.common import REPO_ROOT, within, publish, json_bytes, atomic_json
from src.collect.contract import contract
from src.clean.text import sha256, canonical_json
from src.nlp.validation import read_manifest, verify_graph_contract
from .checks import Findings, ISSUE_FIELDS, corpus_checks, graph_checks, identity_risks
from .sampling import EDGE_FIELDS, NODE_FIELDS, samples, csv_bytes, decode_csv, form_fingerprint, human_summary

DEFAULT_CONFIG = "config/a6_audit.json"
CODE_VERSION = "a6-audit-1.0.0"
EDGE_FILE, NODE_FILE = "a6_edge_audit_sample.csv", "a6_node_audit_sample.csv"


def neo4j_counts(root, manifest):
    if importlib.util.find_spec("neo4j") is None:
        return dict(status="not_run", reason="Neo4j Python driver is not installed; CSV/contract checks still run offline")
    from neo4j import GraphDatabase
    from src.graph.load_neo4j import credentials
    try:
        uri, user, password = credentials()
        with GraphDatabase.driver(uri, auth=(user, password), connection_timeout=3, max_connection_pool_size=1) as driver:
            with driver.session(default_access_mode="READ") as session:
                records = session.run("MATCH (n {project_id:$p}) RETURN labels(n) AS labels, count(n) AS count, collect(DISTINCT n.snapshot_id) AS snapshots", p=manifest["project_id"]).data()
                rels = session.run("MATCH (a {project_id:$p})-[r]->(b {project_id:$p}) RETURN type(r) AS type, count(r) AS count", p=manifest["project_id"]).data()
        labels = Counter()
        versions = set()
        for row in records:
            versions.update(row["snapshots"])
            for label in row["labels"]:
                labels[label] += row["count"]
        if versions != {manifest["snapshot_id"]}:
            return dict(status="blocked", reason="Neo4j project is empty or tagged with another snapshot; counts are not comparable", snapshot_ids=sorted(versions))
        types = {r["type"]: r["count"] for r in rels}
        same = dict(labels) == manifest["counts_by_label"] and types == manifest["counts_by_type"]
        return dict(status="passed" if same else "failed", reason="Read-only MATCH counts for the exact CSV snapshot", counts_by_label=dict(labels), counts_by_type=types)
    except Exception as exc:
        # Do not include driver messages/URIs that could expose connection secrets.
        return dict(status="blocked", reason="Neo4j credentials/connectivity/read unavailable: " + type(exc).__name__)


def import_reviews(datasets, graph, findings):
    evidence = {e["evidence_id"]: e for data in [*datasets, graph] for e in data.get("evidence.jsonl", [])}
    seen = set()
    for data in [*datasets, graph]:
        for r in data.get("needs_review.csv", []):
            if r["review_id"] in seen or r["review_status"] != "open":
                continue
            seen.add(r["review_id"])
            owner = "B" if r["entity_type"] == "Method" else r["assigned_to"] if r["assigned_to"] in ("A", "B") else "A|B"
            category = "affiliation" if r["entity_type"] == "Institution" or "affiliation" in (r["field_name"] or "") else "nlp_relation" if r["entity_type"] in ("Task", "Dataset", "Method") else "identity"
            findings.add("existing_review", owner, r["review_id"] + ": " + r["reason"], kind="known_review", severity="P2", category=category,
                papers=[r["paper_id"]] if r["paper_id"] else [], entities=([r["entity_id"]] if r["entity_id"] else []) + r["candidate_ids"],
                evidence=r["evidence_ids"], sources=[evidence[e]["source_record_id"] for e in r["evidence_ids"] if e in evidence and evidence[e]["source_record_id"]],
                action="Review the original needs_review row and source. Do not auto-resolve based on a different source or count this as a confirmed error.")


def load_config(root, path):
    cfg = json.loads(within(root, path).read_text(encoding="utf-8"))
    if set(cfg) != {"seed", "edges_per_type", "node_count", "cross_reviews_per_person", "output_dir", "graph_manifest", "nlp_config", "corpora"}:
        raise ValueError("Unexpected A6 config keys")
    if any(type(cfg[k]) is not int or cfg[k] < 0 for k in ("seed", "edges_per_type", "node_count", "cross_reviews_per_person")) or cfg["edges_per_type"] == 0 or cfg["node_count"] == 0:
        raise ValueError("A6 sampling requires positive sizes and a fixed integer seed")
    if not within(root, cfg["output_dir"]).is_relative_to(within(root, "outputs")):
        raise ValueError("A6 output must be a separate outputs directory")
    if len(cfg["corpora"]) != 2 or {c["owner"] for c in cfg["corpora"]} != {"A", "B"}:
        raise ValueError("Expected one A and one B corpus")
    return cfg


def run(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    cfg = load_config(root, config_path)
    findings, checks, bindings = Findings(), [], {}
    def check(name, owner, callback, *, required=True):
        try:
            before = sum(r["finding_kind"] == "error" for r in findings.rows.values())
            value = callback()
            errors = sum(r["finding_kind"] == "error" for r in findings.rows.values()) - before
            details = value
            if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], dict) and "snapshot_id" in value[0]:
                details = dict(snapshot_id=value[0]["snapshot_id"], tables_checked=len(value[1]),
                               table_counts={key: len(rows) for key, rows in value[1].items()})
            checks.append(dict(check_id=name, status="failed" if errors else "passed", required=required, details=details))
            return value
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            reason = type(exc).__name__ + ": " + str(exc)
            checks.append(dict(check_id=name, status="blocked" if isinstance(exc, OSError) else "failed", required=required, details=reason))
            findings.add(name, owner, reason, category="missing_evidence", action="Supply/repair the configured snapshot or source and rerun; this check is not a pass.")
            return None
    def load(path):
        m, d = read_manifest(root, path, contract()["files"])
        for f in m["files"]:
            bindings[f["path"]] = f["sha256"]
        bindings[path] = sha256(within(root, path).read_bytes())
        return m, d
    corpora, datasets = {}, []
    for scope in cfg["corpora"]:
        owner = scope["owner"]
        loaded = check("load_corpus_" + owner, owner, lambda s=scope: load(s["manifest"]))
        if loaded:
            m, d = loaded
            datasets.append(d)
            def inspect(d=d, scope=scope):
                bodies = {}
                for s in d["source_records.jsonl"]:
                    raw = within(root, s["raw_path"])
                    if not raw.is_relative_to(within(root, "data/raw")):
                        raise ValueError("Raw source path is outside data/raw")
                    body = gzip.decompress(raw.read_bytes())
                    if sha256(body) != s["content_sha256"]:
                        raise ValueError("Raw source hash mismatch: " + s["source_record_id"])
                    bindings[s["raw_path"]] = sha256(raw.read_bytes())
                    bodies[s["source_record_id"]] = body
                return corpus_checks(d, scope, findings, bodies)
            stats = check("corpus_checks_" + owner, owner, inspect)
            if stats:
                corpora[owner] = stats
            check("contract_corpus_" + owner, owner, lambda m=m: verify_graph_contract(root, m))
            from src.clean.verify import verify as clean_verify
            check("clean_replay_" + owner, owner, lambda s=scope: clean_verify(root, s["clean_config"]))
            if scope.get("metadata_config"):
                from src.metadata.verify import verify as metadata_verify
                check("metadata_replay_" + owner, owner, lambda s=scope: metadata_verify(root, s["metadata_config"]))
    loaded = check("load_graph", "B", lambda: load(cfg["graph_manifest"]))
    graph_stats, risks, edge_rows, node_rows, sampling = {}, {}, [], [], {}
    graph_manifest = None
    if loaded:
        graph_manifest, graph = loaded
        check("contract_graph", "B", lambda: verify_graph_contract(root, graph_manifest))
        from src.nlp.verify import verify as nlp_verify
        check("nlp_replay", "A|B", lambda: nlp_verify(root, cfg["nlp_config"]))
        graph_stats = check("independent_graph_checks", "B", lambda: graph_checks(graph, graph_manifest, findings)) or {}
        all_ids = [{p["paper_id"] for p in d["papers.jsonl"]} for d in datasets]
        if len(all_ids) == 2:
            overlap = all_ids[0] & all_ids[1]
            if overlap:
                findings.add("cross_corpus_paper_overlap", "A|B", "Paper core IDs occur in both corpora", papers=overlap, category="identity")
            graph_ids = {p["paper_id"] for p in graph["papers.jsonl"] if p["scope"] == "core"}
            if graph_ids != all_ids[0] | all_ids[1]:
                findings.add("graph_corpus_membership", "B", "Graph Paper membership differs from the two audited corpora", papers=graph_ids.symmetric_difference(all_ids[0] | all_ids[1]), category="identity")
            for d in datasets:
                gp = {p["paper_id"]: p for p in graph["papers.jsonl"]}
                ga = {tuple(a[k] for k in ("authorship_id", "institution_id")): a for a in graph["authorships.csv"]}
                if any(gp.get(p["paper_id"]) != p for p in d["papers.jsonl"]) or any(ga.get((a["authorship_id"], a["institution_id"])) != a for a in d["authorships.csv"]):
                    findings.add("graph_metadata_stage_drift", "A|B", "Graph uses earlier canonical metadata than the selected audit corpus; rebind/rebuild before judging this as the latest graph", category="time_or_version")
        risks = identity_risks(datasets, graph, findings)
        import_reviews(datasets, graph, findings)
        # Do not sample a graph with failed schema/contract checks or confirmed structural errors.
        graph_trusted = all(c["status"] == "passed" for c in checks if c["check_id"] in ("load_graph", "contract_graph", "independent_graph_checks")) and not any(i["finding_kind"] == "error" for i in findings.rows.values())
        if graph_trusted and len(datasets) == 2:
            edge_rows, node_rows, sampling = samples(graph, graph_manifest, list(findings.rows.values()), risks, cfg)
        else:
            checks.append(dict(check_id="audit_sampling", status="blocked", required=True, details="Complete trusted corpus/graph inputs are required before sampling"))
        neo = neo4j_counts(root, graph_manifest)
        checks.append(dict(check_id="neo4j_counts", status=neo["status"], required=False, details=neo))
    else:
        graph = {}
        import_reviews(datasets, {}, findings)
        checks.append(dict(check_id="audit_sampling", status="blocked", required=True, details="Graph snapshot is unavailable"))
        checks.append(dict(check_id="neo4j_counts", status="not_run", required=False, details="No trusted graph snapshot to compare"))
    issues = sorted(findings.rows.values(), key=lambda r: (r["severity"], r["finding_kind"], r["issue_id"]))
    auto = dict(code_version=CODE_VERSION, seed=cfg["seed"], graph_snapshot_id=graph_manifest["snapshot_id"] if graph_manifest else None,
        checks=checks, corpora=corpora, graph=graph_stats, sampling=sampling,
        issue_counts_by_kind=dict(Counter(r["finding_kind"] for r in issues)), issue_counts_by_owner=dict(Counter(r["owner"] for r in issues)),
        issue_counts_by_check=dict(Counter(r["check_id"] for r in issues)), confirmed_errors=sum(r["finding_kind"] == "error" for r in issues),
        checks_execution_complete=all(c["status"] in ("passed", "failed") for c in checks if c["required"]),
        automatic_checks_passed=all(c["status"] == "passed" for c in checks if c["required"]) and not any(r["finding_kind"] == "error" for r in issues),
        fixes_applied=[], data_modified=False, human_verdicts_generated=False)
    edge_body, node_body = csv_bytes(EDGE_FIELDS, edge_rows), csv_bytes(NODE_FIELDS, node_rows)
    auto_body = json_bytes(auto)
    run_manifest = dict(code_version=CODE_VERSION, graph_snapshot_id=auto["graph_snapshot_id"], seed=cfg["seed"],
        input_files_sha256=bindings, config_sha256=sha256(within(root, config_path).read_bytes()),
        automatic_report_sha256=sha256(auto_body), edge_form_fingerprint=form_fingerprint(decode_csv(edge_body)), node_form_fingerprint=form_fingerprint(decode_csv(node_body)),
        primary_rows=sampling.get("unique_edges", 0), cross_rows=sampling.get("cross_review_rows", 0), node_rows=len(node_rows))
    human = human_summary(decode_csv(edge_body), decode_csv(node_body))
    human["ready_for_a7"] = False
    out = within(root, cfg["output_dir"])
    files = {out / "a6_review_issues.csv": csv_bytes(ISSUE_FIELDS, issues), out / EDGE_FILE: edge_body, out / NODE_FILE: node_body,
             out / "a6_automatic_report.json": auto_body, out / "a6_run_manifest.json": json_bytes(run_manifest),
             out / "a6_human_summary.json": json_bytes(human), out / "a6_review_summary.md": markdown(auto, human).encode("utf-8")}
    publish(files)
    return dict(automatic_checks_passed=auto["automatic_checks_passed"], checks_execution_complete=auto["checks_execution_complete"],
                confirmed_errors=auto["confirmed_errors"], issue_counts_by_kind=auto["issue_counts_by_kind"], corpora=corpora, graph=graph_stats,
                sampling=sampling, human_audit_complete=False, ready_for_a7=False, output_dir=cfg["output_dir"])


def markdown(auto, human):
    lines = ["# A6 — Review dữ liệu và kiểm tra chất lượng", "", f"Graph snapshot: `{auto['graph_snapshot_id']}`; seed `{auto['seed']}`.", "",
             "## Kiểm tra tự động", "", f"Required checks passed: {auto['automatic_checks_passed']}; execution complete: {auto['checks_execution_complete']}.", ""]
    for owner, s in auto["corpora"].items():
        lines.append(f"- {owner}: {s['valid_core_papers']}/{s['target']} Paper core hợp lệ; {s['distinct_authorships']} lượt authorship; {s['unresolved_authorships']} thiếu Author ID; {s['missing_institution_authorships']} thiếu Institution ID.")
    graph = auto["graph"]
    lines += [f"- Graph: {graph.get('nodes', 0)} node, {graph.get('edges', 0)} cạnh; {graph.get('nlp_edges', 0)} cạnh NLP, {graph.get('nlp_evidence_checked', 0)} evidence NLP được kiểm tra binding/offset.",
              f"- Finding kinds: `{canonical_json(auto['issue_counts_by_kind'])}`; confirmed automatic errors: {auto['confirmed_errors']}.",
              "- Known reviews và review risks chưa phải lỗi ngữ nghĩa đã được xác nhận. Không tự sửa B4/B5 hoặc dữ liệu nguồn; xem a6_review_issues.csv để lọc owner/severity/check_id.",
              f"- Phân loại issue: `{canonical_json(auto['issue_counts_by_check'])}`.", "", "| Kiểm tra | Trạng thái |", "|---|---|"]
    lines += [f"| {c['check_id']} | {c['status']} |" for c in auto["checks"]]
    for c in auto["checks"]:
        if c["status"] != "passed":
            detail = c["details"].get("reason", canonical_json(c["details"])) if isinstance(c["details"], dict) else c["details"]
            lines += ["", f"{c['check_id']}: {detail}."]
    rate = "chưa có kết quả chấm" if human['primary']['conservative_precision'] is None else f"{100 * human['primary']['conservative_precision']:.2f}% ({human['primary']['correct']}/{human['primary']['graded']})"
    lines += ["", "## Mẫu và chấm độc lập", "", f"Primary/cross/node rows: {human['primary']['total']}/{human['cross']['total']}/{human['nodes']['total']}.",
              f"Primary A/B: `{canonical_json(auto['sampling'].get('primary_by_reviewer', {}))}`. Chi tiết phân tầng:", "", "| Quan hệ | Cạnh trong graph | Mẫu primary |", "|---|---:|---:|"]
    lines += [f"| {typ} | {stratum['available']} | {stratum['sampled']} |" for typ, stratum in auto['sampling'].get('strata', {}).items()]
    lines += ["", f"Đã chấm primary: {human['primary']['graded']}; còn pending: {human['primary']['pending']}. Conservative precision: {rate}.",
              f"Cross disagreements: {len(human['cross_disagreements'])}; node pending: {human['nodes']['pending']}.",
              "Unverifiable được tính là chưa đúng; pending_review không nằm trong mẫu số đã chấm. Cross rows không nhân đôi mẫu số precision primary. Không suy độ chính xác toàn graph >90% từ mẫu thử.", "", "## Bàn giao", "",
              "Mở a6_edge_audit_sample.csv và a6_node_audit_sample.csv bằng Excel/CSV editor. Lọc assigned_reviewer A/B, review_phase primary/cross; chỉ sửa review_status, error_group, review_notes, reviewer_name và reviewed_at (ISO 8601 có timezone).",
              "review_status: correct / incorrect / unverifiable / pending_review. error_group: identity / affiliation / nlp_relation / citation / missing_evidence / time_or_version / other. Incorrect/unverifiable cần lý do; mọi dòng đã chấm cần tên người và thời điểm thật. Không sửa ID, assignment, evidence hoặc thêm/xóa dòng.",
              "evidence_json trên phiếu cạnh chứa tối đa 3 bản ghi nguyên văn để phù hợp CSV/Excel; evidence_ids vẫn giữ toàn bộ. Đọc evidence.jsonl được manifest graph tham chiếu để kiểm tra tất cả nguồn, đặc biệt cạnh có nhiều Paper hỗ trợ.",
              "Chạy `python -m src.audit summarize --config config/a6_audit.json` để tổng hợp sau khi A/B chấm. Lệnh này chỉ cập nhật báo cáo dẫn xuất, giữ nguyên phiếu chấm. Rerun `run` từ chối ghi đè phiếu đã sửa; snapshot/rule/config mới phải dùng output_dir mới.",
              "", f"A6 tự động hoàn tất: {auto['checks_execution_complete']}; human audit hoàn tất: {human['human_audit_complete']}.",
              "A7 chỉ sẵn sàng sau khi các kiểm tra bắt buộc qua, A/B chấm và đọc chéo đủ, xử lý các kết quả incorrect/unverifiable/bất đồng và xác minh lại lỗi đã sửa. Hiện chưa tuyên bố đạt precision hoặc nghiệm thu toàn graph."]
    return "\n".join(lines) + "\n"


def summarize(root=REPO_ROOT, config_path=DEFAULT_CONFIG):
    root = Path(root).resolve()
    cfg = load_config(root, config_path)
    out = within(root, cfg["output_dir"])
    manifest = json.loads((out / "a6_run_manifest.json").read_text(encoding="utf-8"))
    if manifest["code_version"] != CODE_VERSION:
        raise ValueError("Audit code version changed; create a new audit run")
    if sha256(within(root, config_path).read_bytes()) != manifest["config_sha256"]:
        raise ValueError("Audit config changed; create a new audit run")
    for name, digest in manifest["input_files_sha256"].items():
        if sha256(within(root, name).read_bytes()) != digest:
            raise ValueError("Audited input changed: " + name)
    auto_body = (out / "a6_automatic_report.json").read_bytes()
    if sha256(auto_body) != manifest["automatic_report_sha256"]:
        raise ValueError("Automatic report changed")
    edges, nodes = [decode_csv((out / name).read_bytes()) for name in (EDGE_FILE, NODE_FILE)]
    if form_fingerprint(edges) != manifest["edge_form_fingerprint"] or form_fingerprint(nodes) != manifest["node_form_fingerprint"]:
        raise ValueError("Immutable audit fields or sample membership changed")
    human = human_summary(edges, nodes)
    auto = json.loads(auto_body)
    human["ready_for_a7"] = auto["automatic_checks_passed"] and human["human_findings_clear"]
    atomic_json(out / "a6_human_summary.json", human)
    (out / "a6_review_summary.md").write_bytes(markdown(auto, human).encode("utf-8"))
    return human
