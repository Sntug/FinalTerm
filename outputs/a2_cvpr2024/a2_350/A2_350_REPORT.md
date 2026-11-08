# Kết quả A2 350 — bằng chứng

Đã thu 350 Paper A hợp lệ; 328 Work matched, 22 needs_review, không còn bài chưa thu. Kết quả/coverage và hướng dẫn chuẩn: [A2_HANDOFF](../../../handoff/a/A2_HANDOFF.md). Manifest metadata giữ nguyên, graph_ready=false; không nghiệm thu A3/NLP/Neo4j/pilot nhóm.

| Bằng chứng | Tệp |
| --- | --- |
| Số liệu và request của lượt thu thật | [live_summary.json](live_summary.json), [live_run.log](live_run.log) |
| Khóa lựa chọn trước thu detail, membership | [selection_verification.json](selection_verification.json), [cvf_verification.json](cvf_verification.json) |
| Đối chiếu Work, danh sách cần review | [matching.json](matching.json), [WORK_REVIEW.md](WORK_REVIEW.md) |
| Schema/hash/FK, offline, resume không nhân đôi | [verify_350.log](verify_350.log), [offline_run.log](offline_run.log), [cached_resume.log](cached_resume.log), [replay_and_preservation.json](replay_and_preservation.json) |
| Test cuối | [final_tests.log](final_tests.log) |
| Retry/429, giới hạn quan sát status | [transport_audit.json](transport_audit.json) |
| Lỗi checkpoint Windows đã sửa; log gốc giữ lại | [offline_run_initial.log](offline_run_initial.log), [offline_failure_summary.json](offline_failure_summary.json) |

Các log/JSON là bằng chứng của lượt chạy tương ứng, không phải hướng dẫn vận hành thay thế. `summary.json` là kết quả mutable khi chạy local; dùng `live_summary.json` để đọc số request thu thật. 22 Work còn review không làm mất Paper CVF hợp lệ.
