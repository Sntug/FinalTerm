# Lệnh chạy phần của B

Chạy từ gốc repo với Python 3.12, sau khi cài `pip install -r config/requirements_trend_b.txt`. Các lệnh dưới dùng `python` là Python 3.12 của môi trường đó.

## Chọn mẫu ICCV (H3)

```bash
python -B -X utf8 -m src.collect_b.select_iccv2025
python -B -X utf8 -m src.collect_b.select_iccv2023
```

Hai lệnh kiểm hash thứ hạng ứng viên và không ghi đè lock trong `config/b_iccv2025_350_selection.json`, `config/b_iccv2023_trend_350_selection.json`.

## Metadata ICCV 2023 và 2025 (H5)

Replay dùng phản hồi CVF và OpenAlex đã lưu trong `data/raw/iccv2023/`, `data/raw/iccv2025/`. Để thu lần đầu, bỏ `--offline` và đặt `OPENALEX_API_KEY` trong môi trường hoặc `.env` local.

```bash
python -B -X utf8 -m src.collect --config config/b_iccv2025_350.json --offline
python -B -X utf8 -m src.clean --config config/b_iccv2025_h5.json
python -B -X utf8 -m src.collect_b.h5_coverage_iccv2025
```

ICCV 2023 dùng `config/b_iccv2023_trend_350.json`, `config/b_iccv2023_trend_h5.json` và `src.collect_b.h5_coverage_iccv2023`. Độ phủ ghi ở `outputs/b_iccv2025/h5_coverage.json` và `outputs/b_iccv2023/trend/h5_coverage.json`.

Giữ nguyên `data/processed/iccv2025/` đã commit. Dựng lại H5 từ raw cho cùng nội dung bảng, nhưng `created_at`, `decided_at` và `snapshot_id` của H5 đổi theo giờ chạy, nên không dựng lại sau khi đã bàn giao. Nếu buộc phải dựng lại, xóa `outputs/b_iccv2025/h5_coverage.json` trước lệnh cuối vì lệnh này không ghi đè file khác byte.

## SLM (H2)

Cần Ollama chạy local (`ollama serve`) với `qwen3:8b` và `qwen3:4b`. Cấu hình ở `config/trend_slm.json`.

```bash
python -B -X utf8 -m src.slm.pilot
```

Pilot dùng 20 bài ngoài `data/gold/gold_set.csv`, ghi `outputs/trend/slm_pilot/`. Kết quả được cache theo sha256 của văn bản, prompt và digest model, nên chạy lại từ cache không cần Ollama. Đã thử với Ollama 0.40.17; bản cũ hơn có thể bỏ qua tùy chọn `truncate`. Pilot đo RAM bằng `ps` và `sysctl` nên chỉ chạy trên macOS.

Khi gọi `generate_json` hoặc `generate_text` từ module khác, truyền `config` có `cache_dir` riêng để không ghi vào cache của pilot. Prompt vượt `num_ctx` ném `RuntimeError`; schema dùng từ khóa không hỗ trợ ném `TypeError` trước khi gọi model. Với `qwen3:4b`, phần suy luận cũng tính vào `num_predict`.

## Snapshot `mxh_cv_trend` (H8)

Neo4j 5.28 nghe ở bolt `127.0.0.1:17687`, heap tối thiểu 2g (`server.memory.heap.max_size=2g` trong `conf/neo4j.conf`). Cấu hình ở `config/trend_graph.json`.

```bash
python -B -X utf8 -m src.graph.snapshot dryrun
python -B -X utf8 -m src.graph.snapshot lock
```

`dryrun` chạy được với H7 giả trong `outputs/trend/h7_fixture/`. `lock` chỉ chạy khi đủ H5 của các kỳ giữ lại và H7 thật: nó dựng và kiểm trong `graph_dryrun/`, đạt cả ba điều kiện mới ghi `data/processed/mxh_cv_trend/graph/`. Sau khi khóa, `dryrun` bị từ chối để không nạp đè Neo4j. Cả hai ghi `outputs/trend/snapshot_check.json` với ba điều kiện khóa của PLAN §3.

Kiểm contract cho snapshot đã khóa:

```bash
python -B -c "import json; from src.graph import snapshot as s; print(s.verify_graph_contract(s.ROOT, json.load(open('data/processed/mxh_cv_trend/graph/snapshot_manifest.json'))))"
```

## Phân tích MXH (H9) và Q1b (H11)

```bash
python -B -X utf8 -m src.analysis.sna --snapshot data/processed/mxh_cv_trend/graph
```

Cấu hình ở `config/trend_sna.json`, đầu ra ở `outputs/trend/sna/`. Sau khi khóa H8, đổi `snapshot` trong config sang `data/processed/mxh_cv_trend/graph` để lệnh không tham số cũng chạy trên snapshot chính thức. Louvain chạy trên LCC; mỗi thành phần nhỏ là một nhóm riêng, `summary.json` ghi phạm vi tính (bài thiếu tác giả hoặc tổ chức). `queries/trend_q1b.cypher` nhận `$author_ids` là thành viên một cộng đồng trong `communities.csv`; `src.analysis.test_q1b` cần Neo4j đang bật, nếu không hai test bị bỏ qua.

## Embedding (H12)

```bash
python -B -X utf8 -m src.embed.embed --input data/processed/mxh_cv_trend/graph
```

Cấu hình ở `config/b_embed.json`, đầu ra `outputs/trend/embed/similar_topics.csv` và `topic_umap.csv`. FastRP được cài bằng numpy (Neo4j local không có GDS), lấy trung bình 8 seed cố định và bỏ cặp có cosine dưới 0,02, nên mỗi chủ đề có tối đa 5 hàng, có chủ đề không có hàng nào. `topic_umap.csv` có cột `n_papers` để app cảnh báo chủ đề ít bài. Cần khoảng 4 GB RAM trống. Sau khi khóa H8, đổi `input_dir` trong config sang snapshot chính thức rồi chạy lại.

## App

```bash
streamlit run app/Home.py
```

## Kiểm thử

```bash
PYTHONPATH=src/graph:. python -B -X utf8 -m unittest src.collect_b.test_h5_iccv2025 src.collect_b.test_select_iccv2025 src.collect_b.test_select_iccv2023 src.slm.test_slm src.graph.test_snapshot src.graph.test_load_neo4j src.graph.test_export_graph src.graph.test_b_pilot src.analysis.test_sna src.analysis.test_q1b src.analysis.test_analysis src.embed.test_embed app.lib.test_lib
```
