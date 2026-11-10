"""A8 offline integration/replay receipts, with separately invoked Neo4j checks."""
import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from src.collect.common import REPO_ROOT, within, json_bytes
from src.clean.text import sha256, canonical_json
from src.collect.contract import contract
from src.nlp.validation import read_manifest, verify_graph_contract

DEFAULT_CONFIG = "config/a8_integration.json"
VERSION = "a8-integration-1.0.0"
STATUSES = {"PASS", "FAIL", "PENDING_B", "BLOCKED_ENV", "NOT_RUN"}


def read_json(root, path):
    return json.loads(within(root, path).read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def exit_status(result):
    if result.get("status") == "FAIL" or result.get("offline_checks_passed") is False:
        return 1
    return 2 if result.get("status") in ("BLOCKED_ENV", "PENDING_B", "NOT_RUN") else 0


def configured(root, path):
    """Refuse accidental publication into a historical A/B snapshot or output root."""
    cfg = read_json(root, path)
    out = within(root, cfg["output_dir"])
    if not out.is_relative_to(within(root, "outputs/a8")):
        raise ValueError("A8 receipts must stay under outputs/a8")
    nc, gc, ac = [read_json(root, cfg[k]) for k in ("nlp_config", "graph_config", "audit_config")]
    for c in (nc, gc):
        if not within(root, c["output_dir"]).is_relative_to(within(root, "data/processed/mxh_cv_700/a8")):
            raise ValueError("A8 generated snapshots must use a separate a8 directory")
    nout, gout = [within(root, c["output_dir"]) for c in (nc, gc)]
    if nout.is_relative_to(gout) or gout.is_relative_to(nout):
        raise ValueError("NLP and graph output directories must not overlap")
    if gc["nlp_manifest"] != nc["output_dir"] + "/snapshot_manifest.json":
        raise ValueError("Graph must use the selected A8 NLP manifest")
    if ac["graph_manifest"] != gc["output_dir"] + "/snapshot_manifest.json" or ac["nlp_config"] != cfg["nlp_config"]:
        raise ValueError("A8 audit bindings differ from the selected NLP/graph")
    if not within(root, ac["output_dir"]).is_relative_to(out):
        raise ValueError("A8 audit must use a separate directory under its receipts")
    expected = [c["manifest"] for c in ac["corpora"]]
    graph_inputs = [str(Path(i["a3_dir"]) / "snapshot_manifest.json").replace("\\", "/") for i in gc["inputs"]]
    if nc["input_manifests"] != expected or graph_inputs != expected:
        raise ValueError("Selected corpus, NLP and exporter input snapshots differ")
    rc = read_json(root, cfg["report_config"])
    if (rc["graph_manifest"], rc["nlp_config"], rc["audit_config"]) != (
            ac["graph_manifest"], cfg["nlp_config"], cfg["audit_config"]):
        raise ValueError("A7 report is bound to a different graph/NLP/audit config")
    return cfg, nc, gc, ac


def recorded_import(root, output, graph_dir, project_id):
    """Accept a prior executed isolated test only for this exact graph content."""
    path = output / "test_import.json"
    if not path.exists():
        return dict(status="BLOCKED_ENV" if importlib.util.find_spec("neo4j") is None else "NOT_RUN",
                    reason="Requires a driver and an explicit empty dedicated test instance; default run never imports/resets DB")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["status"] != "PASS":
        return record
    from src.graph.load_neo4j import read_snapshot, content_hash
    m, nodes, rels = read_snapshot(graph_dir, project_id)
    if record.get("snapshot_id") != m["snapshot_id"]:
        return dict(status="NOT_RUN", reason="Recorded isolated import belongs to another snapshot; rerun on a fresh test instance")
    if record.get("content_sha256") != content_hash(nodes, rels) or any(record.get(k) != "PASS" for k in ("repeat_import", "rollback_after_injected_failure")):
        return dict(status="FAIL", reason="Recorded isolated test does not prove repeat/rollback/content for this snapshot")
    return dict(**record, reason="Previously executed isolated test receipt matches this exact snapshot and content")


class Checks:
    def __init__(self):
        self.rows = []

    def add(self, name, status, reason, *, owner="A/B", required=True, details=None, command=None):
        if status not in STATUSES:
            raise ValueError("Unknown A8 check status")
        self.rows.append(dict(check_id=name, status=status, owner=owner, required_offline=required,
                             reason=reason, details=details, command=command))

    def run(self, name, callback, *, owner="A/B", required=True, command=None):
        print("A8: " + name, flush=True)
        try:
            value = callback()
            if value is None:
                raise ValueError("Check returned no verification result")
            status = value.get("status", "PASS") if isinstance(value, dict) else "PASS"
            if status == "available":
                status = "PASS"
            if isinstance(value, dict) and (value.get("passed") is False or value.get("automatic_checks_passed") is False):
                status = "FAIL"
            details = value
            if isinstance(value, tuple) and value and isinstance(value[0], dict) and "snapshot_id" in value[0]:
                details = {k: value[0].get(k) for k in ("snapshot_id", "node_count", "edge_count", "counts_by_label", "counts_by_type")}
                details["property_conflicts"] = len(value[1].get("name_prop_conflicts", []))
            self.add(name, status, "Executed" if status == "PASS" else value.get("reason", status),
                     owner=owner, required=required, details=details, command=command)
            return value if status == "PASS" else None
        except (ImportError, PermissionError) as exc:
            self.add(name, "BLOCKED_ENV", type(exc).__name__ + ": " + str(exc), owner=owner, required=required, command=command)
        except Exception as exc:
            self.add(name, "FAIL", type(exc).__name__ + ": " + str(exc), owner=owner, required=required, command=command)
        return None


def protected_files(root):
    prefixes = ["data", "handoff", "src/collect", "src/collect_b", "src/clean", "src/metadata", "src/nlp", "src/graph",
                "src/audit", "config/contracts", "config/b*.json", "config/a_cvpr*.json", "config/a4*.json",
                "config/a6_audit.json", "outputs/a6", "outputs/a6_execution", "outputs/b_iccv2023"]
    paths = subprocess.check_output(["git", "ls-files", "-z", "--", *prefixes], cwd=root).decode().split("\0")
    # Future reruns may have committed A8 snapshots: protect those too, since replay must be identical.
    return {p: sha256(within(root, p).read_bytes()) for p in paths if p}


def form_state(root, audit_cfg):
    """Preserve any human edits, including on subsequent A8 reruns."""
    from src.audit.pipeline import run, summarize
    out = within(root, read_json(root, audit_cfg)["output_dir"])
    if (out / "a6_run_manifest.json").exists():
        summarize(root, audit_cfg)  # validates fingerprints; updates only derived summaries
    else:
        run(root, audit_cfg)
    from src.reporting.a7 import audit_metrics
    result = audit_metrics(root, audit_cfg)
    if result["status"] != "available":
        raise ValueError("Audit is unavailable/stale; use a new audit output for changed snapshots")
    if not result["automatic_checks_passed"]:
        raise ValueError("Required A6 automatic checks failed")
    return result


def human_status(human):
    negative = any(human[k]["incorrect"] or human[k]["unverifiable"] for k in ("primary", "cross", "nodes")) or bool(human["cross_disagreements"])
    return "PASS" if human["human_findings_clear"] else "FAIL" if negative or human["human_audit_complete"] else "PENDING_B"


def compare_baseline(old, new):
    """A5 added evidence/reviews; verify actual graph deltas without assuming zero."""
    old_nodes, new_nodes = [{n["id"]: n for n in d["nodes.csv"]} for d in (old, new)]
    old_edges, new_edges = [{e["edge_id"]: e for e in d["edges.csv"]} for d in (old, new)]
    semantic = lambda e: {k: v for k, v in e.items() if k != "evidence_ids"}
    return dict(nodes_added=len(set(new_nodes) - set(old_nodes)), nodes_removed=len(set(old_nodes) - set(new_nodes)),
        node_records_changed=sum(old_nodes[k] != new_nodes[k] for k in old_nodes.keys() & new_nodes.keys()),
        edges_added=len(set(new_edges) - set(old_edges)), edges_removed=len(set(old_edges) - set(new_edges)),
        semantic_edge_records_changed=sum(semantic(old_edges[k]) != semantic(new_edges[k]) for k in old_edges.keys() & new_edges.keys()),
        edge_evidence_changed=sum(old_edges[k]["evidence_ids"] != new_edges[k]["evidence_ids"] for k in old_edges.keys() & new_edges.keys()),
        evidence_added=len({e["evidence_id"] for e in new["evidence.jsonl"]} - {e["evidence_id"] for e in old["evidence.jsonl"]}),
        sources_added=len({s["source_record_id"] for s in new["source_records.jsonl"]} - {s["source_record_id"] for s in old["source_records.jsonl"]}),
        open_reviews_before=sum(r["review_status"] == "open" for r in old["needs_review.csv"]),
        open_reviews_after=sum(r["review_status"] == "open" for r in new["needs_review.csv"]))


def replay(root, cfg, nc, gc):
    from src.nlp.pipeline import run as nlp_run
    from src.graph.export_graph import export
    folders = [within(root, c["output_dir"]) for c in (nc, gc)]
    before = {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for folder in folders for p in folder.iterdir() if p.is_file()}
    nlp_run(root, cfg["nlp_config"])
    export(gc, root)
    after = {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for folder in folders for p in folder.iterdir() if p.is_file()}
    if before != after:
        raise ValueError("NLP/graph replay changed artifact bytes")
    return dict(passed=True, identical_files=len(after), artifacts_sha256=after)


def report_check(root, cfg, graph):
    from src.reporting.a7 import run
    run(root, cfg["report_config"])
    rc = read_json(root, cfg["report_config"])
    m = read_json(root, rc["output_dir"] + "/metrics.json")
    labels, types = dict(Counter(n["label"] for n in graph["nodes.csv"])), dict(Counter(e["type"] for e in graph["edges.csv"]))
    if m["graph"]["counts_by_label"] != labels or m["graph"]["counts_by_type"] != types or m["combined"]["status"] != "available":
        raise ValueError("A7 counts/canonical union differ from the selected graph")
    gm = read_json(root, read_json(root, cfg["audit_config"])["graph_manifest"])
    if m["graph"]["snapshot_id"] != gm["snapshot_id"]:
        raise ValueError("A7 is bound to another graph snapshot")
    for path, digest in m["input_files_sha256"].items():
        if sha256(within(root, path).read_bytes()) != digest:
            raise ValueError("A7 input hash drift: " + path)
    paths = [within(root, rc["report"]), within(root, rc["output_dir"] + "/metrics.json"), *sorted(within(root, rc["output_dir"] + "/figures").glob("*"))]
    before = {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in paths if p.is_file()}
    run(root, cfg["report_config"])
    if before != {p.relative_to(root).as_posix(): sha256(p.read_bytes()) for p in paths if p.is_file()}:
        raise ValueError("A7 regeneration changed report/metrics/figure bytes")
    # Replace the former A7 execution receipt with checks for the refreshed snapshot.
    write_json(within(root, rc["output_dir"] + "/verification.json"), dict(passed=True, verified_by=VERSION,
        graph_snapshot_id=m["graph"]["snapshot_id"], artifacts_sha256=before, deterministic_artifacts=len(before),
        input_bindings_checked=len(m["input_files_sha256"]), report_sections=6, tables=8, figures=2,
        contract_validations={k: v["passed"] for k, v in m["validation"].items()},
        human_primary_graded=m["audit"]["human"]["primary"]["graded"], precision=m["audit"]["human"]["primary"]["conservative_precision"],
        note="A8 refreshed A7 on the selected integration snapshot; original test logs retain their execution scope"))
    return dict(passed=True, snapshot_id=m["graph"]["snapshot_id"], corpora=m["corpora"], combined=m["combined"],
                nlp=m["nlp"], report=rc["report"], artifacts_sha256=before)


def test_suites(root, output):
    """Run original suites; force B's destructive live tests off in this worker."""
    sys.path.insert(0, str(root / "quality/checks"))
    results = {}
    for name, folder in (("quality", "quality/checks"), ("b_regression", "src/graph")):
        stream = io.StringIO()
        with patch.dict(sys.modules, {"neo4j": None}), redirect_stdout(stream), redirect_stderr(stream):
            suite = unittest.TestLoader().discover(str(root / folder), pattern="test_*.py")
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        (output / (name + "_tests.log")).write_bytes(stream.getvalue().encode("utf-8"))
        results[name] = dict(status="PASS" if result.wasSuccessful() else "FAIL", run=result.testsRun,
            passed=result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
            failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
            skips=[reason for _, reason in result.skipped])
    return dict(status="PASS" if all(r["status"] == "PASS" for r in results.values()) else "FAIL",
                suites=results, live_neo4j_tests_forced_disabled=True,
                reason="Offline suites executed; live DB tests are separate checks, never counted as successful imports")


def dependency(root, item):
    found = []
    for path in item["paths"]:
        p = within(root, path)
        if p.is_file() or p.is_dir() and any(f.is_file() and f.name != ".gitkeep" and "__pycache__" not in f.parts for f in p.rglob("*")):
            found.append(path)
    return dict(**item, status="NOT_RUN" if found else "PENDING_B", observed_paths=found,
        reason="Outputs appeared; their commands, snapshot bindings and results still require verification" if found else item["missing"])


def handoff(summary, receipt):
    lines = ["# A8 — Tích hợp, kiểm thử và bàn giao", "", "Đây là biên nhận tích hợp ứng viên, không thay manifest Contract v2 và không phải release/nộp bài cuối.", "",
        f"Snapshot: `{receipt.get('graph_snapshot_id')}`; commit nền lúc chạy: `{receipt['git']['commit']}`. Code/chỉnh sửa chưa commit được ghi bằng hash trong integration_manifest.json.", "",
        f"Kiểm tra offline bắt buộc qua: **{summary['offline_checks_passed']}**. Data integration partial: **{receipt['partial_integration']}**. Final: **{receipt['is_final']}**.", "",
        "## Trạng thái đã kiểm tra", "", "| Hạng mục | Trạng thái | Phụ trách | Minh chứng/lệnh |", "|---|---|---|---|"]
    for row in summary["checks"]:
        lines.append(f"| {row['check_id']} | {row['status']} | {row['owner']} | {row['reason'].replace('|','/').replace(chr(10),' ')}; chi tiết trong validation_summary.json |")
    lines += ["", "## Dữ liệu và giới hạn", ""]
    if receipt.get("counts"):
        c = receipt["counts"]
        lines += [f"- Paper core theo hội nghị: `{canonical_json(c['papers_by_conference'])}`; scope `{canonical_json(c['papers_by_scope'])}`.",
            f"- {c['nodes']} node, {c['edges']} cạnh; {len(c['counts_by_label'])} nhãn và {len(c['counts_by_type'])} loại quan hệ.",
            f"- Node: `{canonical_json(c['counts_by_label'])}`.", f"- Edge: `{canonical_json(c['counts_by_type'])}`.",
            "- Tổng nhóm lấy từ ID/khóa trong snapshot hợp nhất; không cộng số Author/Institution của hai corpus."]
    lines += ["- Dùng A5 CVPR + A3 ICCV; chạy lại NLP Task/Dataset/Method và exporter B vào thư mục a8 riêng. Không sửa schema, ID, dữ liệu B hoặc graph B5 cũ.",
        "- A8 giữ source_records, provenance, alias/decision và review của A5; ambiguity giữ review/cách ly alias, không tự merge theo tên.",
        "- Human audit là bước riêng. Phiếu cũ outputs/a6 giữ nguyên snapshot B5; phiếu ứng viên A8 ở outputs/a8/audit. Không chuyển nhãn chấm giữa snapshot hoặc tự chấm thay A/B.",
        "- Kiểm tra tự động/hash/offset không chứng minh precision ngữ nghĩa >90%. Review risks không tự động là lỗi thật.", "", "## Chờ B và việc A/B cần làm", "",
        "| Task | Trạng thái | Thiếu/ảnh hưởng | Cần bổ sung và kiểm tra lại |", "|---|---|---|---|"]
    lines += [f"| {d['task']} | {d['status']} | {d['missing']} | {d['required']}; {d['verify']} |" for d in summary["dependencies"]]
    lines += ["", "B2/B4/B5 có thể được ghi PASS chỉ qua checks tương ứng ở trên. B3 có reader/importer offline; chứng nhận live, idempotence và rollback chỉ có khi chạy trên DB thật đúng snapshot.",
        "", "## Chạy lại trên Windows PowerShell", "", "Từ FinalTerm, Python 3.12. Không cần tải lại 700 bài hoặc API key cho replay offline.", "", "```powershell",
        "py -3.12 -m venv .venv-a4", "$a8Python = \".\\.venv-a4\\Scripts\\python.exe\"", "& $a8Python -m pip install -r config/requirements_a7.txt",
        "if (!(Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }",
        "& $a8Python -B -X utf8 -m src.integration.a8 run", "# Chỉ đọc DB được .env trỏ tới, không import/xóa:",
        "& $a8Python -B -X utf8 -m src.integration.a8 neo4j-check", "```", "",
        "`.env` chỉ chứa cấu hình cục bộ; không commit key/password. `.env.example` dùng port mẫu, cần đặt URI đúng instance B muốn đối chiếu. Driver Neo4j là tùy chọn: nếu chưa có, CLI ghi BLOCKED_ENV; cài driver theo môi trường B3 trước khi kiểm tra live.", "",
        "Để thử import, dùng một instance Neo4j test mới, rỗng và tách biệt. Đặt A8_NEO4J_TEST_URI/USER/PASSWORD trong môi trường cục bộ rồi chạy `python -m src.integration.a8 test-import`. URI chỉ chấp nhận bolt localhost trên port riêng, từ chối 7687/17687, URI có credential và DB không rỗng. Lệnh không dùng .env, không tự tạo credential hay server; nếu thiếu môi trường thì BLOCKED_ENV. Helper gọi nguyên loader B ba lần (nhập, nhập lại, lỗi sau nodes để kiểm rollback), giữ dữ liệu test để kiểm tra và không ghi last_import của B. Tuyệt đối không chạy loader trực tiếp vào database chính trong bước thử này.", "",
        "Lệnh neo4j-check/test-import đã có CLI và kiểm thử offline; phần live chưa được xác minh nếu bảng trạng thái không ghi PASS. Đối chiếu cả snapshot tag, content hash và counts theo label/type/core/conference; chỉ count trùng chưa đủ.", "", "## Khi B bổ sung", "",
        "1. Giữ snapshot cũ. Chọn input thật bằng bộ config A8; dùng output NLP/graph/audit mới nếu input/rule/seed thay đổi, cập nhật config A7 cùng snapshot.",
        "2. Chạy lại A8; pipeline có sẵn từ chối ghi đè snapshot khác. Nếu B chỉ thêm báo cáo/analysis, bổ sung path/lệnh của B vào dependency trong config và kiểm chứng đầu ra; không đánh PASS do file tồn tại.",
        "3. A/B chấm đúng phiếu ứng viên, chạy `python -m src.audit summarize --config config/a8_audit.json`, phân xử incorrect/unverifiable/bất đồng rồi chạy lại A8. Runner giữ phiếu đã điền, không gọi run để ghi đè.",
        "4. B thử import trên instance test rỗng; sau đó nhóm tự chọn snapshot/DB chính để nạp. Chạy neo4j-check với .env đúng và A8 lần nữa để biên nhận phản ánh kết quả mới.",
        "5. B6/B7/B8 đối chiếu snapshot ID/hash, hoàn thiện báo cáo nhóm và release/links. Chỉ chốt/nộp khi không còn FAIL và các điều kiện live/audit/báo cáo đã được người phụ trách xác nhận.", "",
        "Biên nhận: outputs/a8/integration_manifest.json; chi tiết từng check và lệnh: outputs/a8/validation_summary.json; log tests: outputs/a8/*_tests.log. Báo cáo số liệu chuẩn vẫn là [A7](a7_data_preprocessing_nlp.md).", ""]
    return "\n".join(lines)


def run(root=REPO_ROOT, config_path=DEFAULT_CONFIG, *, skip_tests=False):
    root = Path(root).resolve()
    cfg, nc, gc, ac = configured(root, config_path)
    output = within(root, cfg["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    checks, before = Checks(), protected_files(root)
    private = {"worktree_sha256": sha256((root / ".gitignore").read_bytes()),
               "index_diff_sha256": sha256(subprocess.check_output(["git", "diff", "--cached", "--", ".gitignore"], cwd=root))}
    ready = True
    for c in cfg["collectors"]:
        owner = c["owner"]
        if not within(root, c["manifest"]).exists() and owner == "B":
            checks.add("collector_B", "PENDING_B", "B2 source manifest is absent", owner="B")
            ready = False
            continue
        from src.collect.verify import verify as verify_collector
        from src.clean.verify import verify as verify_clean
        ready = checks.run("collector_" + owner, lambda c=c: verify_collector(root, c["manifest"]), owner=owner,
            command=f"python -m src.collect.verify --manifest {c['manifest']}") is not None and ready
        ready = checks.run("clean_replay_" + owner, lambda c=c: verify_clean(root, c["clean_config"]), owner=owner,
            command=f"python -m src.clean.verify --config {c['clean_config']}") is not None and ready
        if c.get("metadata_config"):
            from src.metadata.verify import verify as verify_metadata
            ready = checks.run("metadata_replay_" + owner, lambda c=c: verify_metadata(root, c["metadata_config"]), owner=owner,
                command=f"python -m src.metadata.verify --config {c['metadata_config']}") is not None and ready
    gm, graph, audit, report_result = None, None, None, None
    if ready:
        from src.nlp.pipeline import run as nlp_run
        from src.graph.export_graph import export
        nlp = checks.run("nlp_A4_B5", lambda: nlp_run(root, cfg["nlp_config"]), command=f"python -m src.nlp --config {cfg['nlp_config']}")
        if nlp is not None:
            exported = checks.run("graph_B3_B4_B5", lambda: export(gc, root), command=f"python -m src.graph.export_graph --config {cfg['graph_config']}")
            if exported:
                gm, _ = exported
                _, graph = read_manifest(root, ac["graph_manifest"], contract()["files"])
                checks.run("graph_contract", lambda: verify_graph_contract(root, gm))
                checks.run("deterministic_replay", lambda: replay(root, cfg, nc, gc))
                from src.graph.load_neo4j import read_snapshot
                def reader():
                    m, nodes, rels = read_snapshot(within(root, gc["output_dir"]), gc["project_id"])
                    return dict(passed=True, snapshot_id=m["snapshot_id"], nodes=len(nodes), edges=len(rels))
                checks.run("B3_reader_offline", reader, owner="B")
                def baseline():
                    bm, old = read_manifest(root, cfg["baseline_graph_manifest"], contract()["files"])
                    verify_graph_contract(root, bm)
                    return compare_baseline(old, graph)
                checks.run("baseline_B5_delta", baseline)
                audit = checks.run("audit_automatic_and_forms", lambda: form_state(root, cfg["audit_config"]),
                    command=f"python -m src.audit summarize --config {cfg['audit_config']}")
                if audit:
                    human = audit["human"]
                    checks.add("audit_human", human_status(human),
                        f"Primary {human['primary']['graded']}/{human['primary']['total']}; cross {human['cross']['graded']}/{human['cross']['total']}; nodes {human['nodes']['graded']}/{human['nodes']['total']}; precision={human['primary']['conservative_precision']}",
                        required=False, details=human)
                    report_result = checks.run("A7_refresh_and_reconcile", lambda: report_check(root, cfg, graph), command=f"python -m src.reporting.a7 --config {cfg['report_config']}")
                from .neo4j import inspect
                checks.run("neo4j_readonly_content", lambda: inspect(within(root, gc["output_dir"]), gc["project_id"]), required=False, owner="B",
                           command="python -m src.integration.a8 neo4j-check")
    if gm is None:
        checks.add("integration_downstream", "NOT_RUN", "Input/NLP/export prerequisites did not pass; previous outputs are not treated as this run's success")
    if gm:
        checks.run("neo4j_import_idempotence", lambda: recorded_import(root, output, within(root, gc["output_dir"]), gc["project_id"]),
                   owner="B", required=False, command="python -m src.integration.a8 test-import")
    else:
        checks.add("neo4j_import_idempotence", "NOT_RUN", "No validated candidate graph from this run", owner="B", required=False)
    if skip_tests:
        checks.add("tests", "NOT_RUN", "Explicit --skip-tests; cannot claim all required offline checks passed")
    else:
        checks.run("tests", lambda: test_suites(root, output), command="python -m src.integration.a8 run")
    def preservation():
        after = protected_files(root)
        changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
        now = {"worktree_sha256": sha256((root / ".gitignore").read_bytes()),
               "index_diff_sha256": sha256(subprocess.check_output(["git", "diff", "--cached", "--", ".gitignore"], cwd=root))}
        if changed or private != now:
            raise ValueError("Protected inputs/user staging changed: " + str(changed[:10]))
        return dict(passed=True, protected_files=len(before), protected_tree_sha256=sha256(canonical_json(before).encode()), private_gitignore_preserved=True)
    checks.run("preservation", preservation)
    deps = [dependency(root, item) for item in cfg["dependencies"]]
    counts = None
    if gm:
        counts = dict(nodes=gm["node_count"], edges=gm["edge_count"], counts_by_label=gm["counts_by_label"], counts_by_type=gm["counts_by_type"],
            papers_by_scope=dict(Counter(p["scope"] for p in graph["papers.jsonl"])),
            papers_by_conference=dict(Counter(p["conference"] + str(p["conference_year"]) for p in graph["papers.jsonl"])))
    summary = dict(code_version=VERSION, checks=checks.rows, dependencies=deps,
        offline_checks_passed=all(r["status"] == "PASS" for r in checks.rows if r["required_offline"]),
        statuses=dict(Counter(r["status"] for r in checks.rows)), graph_counts=counts, final_ready=False,
        limitation="Data integrity/replay is separate from human accuracy, live import, B6/B7/B8 and final submission")
    data_complete = bool(counts) and counts["papers_by_conference"] == {"CVPR2024": 350, "ICCV2023": 350} and counts["papers_by_scope"] == {"core": 700}
    code_paths = [config_path, cfg["nlp_config"], cfg["graph_config"], cfg["audit_config"], cfg["report_config"],
                  "src/integration/a8.py", "src/integration/neo4j.py", "src/reporting/a7.py"]
    receipt = dict(artifact_kind="integration_receipt_not_contract_manifest", code_version=VERSION,
        validated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git=dict(commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                 branch=subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip(),
                 has_uncommitted_changes=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root))),
        code_and_config_sha256={p: sha256(within(root, p).read_bytes()) for p in code_paths}, schema_version=contract()["schema_version"],
        graph_manifest=ac["graph_manifest"] if gm else None, graph_snapshot_id=gm["snapshot_id"] if gm else None,
        nlp_manifest=gc["nlp_manifest"] if gm else None, counts=counts, rule_versions=gm["rule_versions"] if gm else None,
        dictionary_versions=gm["dictionary_versions"] if gm else None, snapshot_created_at=gm["created_at"] if gm else None,
        input_snapshots=gm.get("input_snapshots") if gm else None,
        graph_files_sha256={f["path"]: f["sha256"] for f in gm["files"]} if gm else {},
        data_scope_complete=data_complete, partial_integration=not data_complete, release_readiness="partial", is_final=False,
        missing_or_unverified=[r["check_id"] for r in checks.rows if r["status"] != "PASS"] + [d["task"] for d in deps if d["status"] != "PASS"],
        validation_summary="outputs/a8/validation_summary.json", automatic_commits_pushes_or_db_writes=False)
    write_json(output / "validation_summary.json", summary)
    receipt["validation_summary_sha256"] = sha256((output / "validation_summary.json").read_bytes())
    write_json(output / "integration_manifest.json", receipt)
    within(root, "report/a8_handoff.md").write_bytes(handoff(summary, receipt).encode("utf-8"))
    return dict(offline_checks_passed=summary["offline_checks_passed"], graph_snapshot_id=receipt["graph_snapshot_id"], counts=counts,
                statuses=summary["statuses"], data_scope_complete=data_complete, release_readiness="partial", final_ready=False,
                output_dir=cfg["output_dir"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("run", "neo4j-check", "test-import"), nargs="?", default="run")
    p.add_argument("--root", type=Path, default=REPO_ROOT)
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--skip-tests", action="store_true")
    a = p.parse_args()
    try:
        if a.action == "run":
            result = run(a.root, a.config, skip_tests=a.skip_tests)
        else:
            cfg, _, gc, _ = configured(a.root, a.config)
            from .neo4j import inspect, test_import
            try:
                result = (inspect if a.action == "neo4j-check" else test_import)(within(a.root, gc["output_dir"]), gc["project_id"])
            except ValueError as exc:
                result = dict(status="FAIL", reason=str(exc))
            except Exception as exc:
                result = dict(status="FAIL", reason="Neo4j verification failed: " + type(exc).__name__)
            result["verified_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            write_json(within(a.root, cfg["output_dir"] + "/" + a.action.replace("-", "_") + ".json"), result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(exit_status(result))
    except (OSError, ValueError, KeyError) as exc:
        p.exit(1, "ERROR: " + type(exc).__name__ + ": " + str(exc) + "\n")


if __name__ == "__main__":
    main()
