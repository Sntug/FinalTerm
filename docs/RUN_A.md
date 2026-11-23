# Trend app · Dữ liệu CVPR

## Khóa mẫu (H1/H3)

Từ gốc repo, dùng Python 3.12 để replay từ listing đã lưu trong Git và chạy test offline.

```powershell
py -3.12 -B -m src.collect.trend_selection
py -3.12 -B -m src.collect.trend_selection --year 2026
py -3.12 -B -m unittest src.collect.test_trend_selection
```

**CVPR 2025.** [Cấu hình H1](../config/a_trend_project.json) cố định seed `20261103`. Từ listing CVF main track, parser chỉ lấy URL trang chi tiết bài đúng kỳ, bỏ trùng URL chuẩn, xếp tăng theo SHA-256 của UTF-8 `seed + "\n" + canonical_url`, hòa thì xét URL. Chọn 350/2.871 bài đầu. Khi thu metadata, bài thiếu abstract vẫn giữ ID và thứ hạng. [Danh sách xếp hạng](../data/processed/cvpr2025/candidates_ranked.csv) ghi toàn bộ ứng viên. [Lock](../config/a_cvpr2025_350_selection.json) ghi nguồn listing, hash raw, hash thứ hạng và hash registry. B và A dùng [input registry](../data/processed/cvpr2025/input_registry.csv) cho H4/H5. DOI và source ID của trang chi tiết để trống đến khi có bằng chứng từng bài. Replay từ chối ghi đè file khác byte.

**CVPR 2024.** Replay kiểm hash listing, hash bảng xếp hạng và registry đầu vào của lock cũ, rồi đối chiếu ID theo thứ tự với registry A5. Trong 2.715 ứng viên, mẫu thực tế khớp top 350 ở **350/350 ID và 350/350 vị trí**, kể cả 30 bài pilot giữ lại. Điều kiện chọn mẫu đạt. Độ phủ văn bản và tỷ lệ NLP chạy thành công cần đo riêng trước khi gắn nhãn xu hướng. [Kết quả đối chiếu](../outputs/trend/quality/cvpr2024_selection.csv)

**D5.** Giữ schema v2, 8 nhãn và 10 loại cạnh. Fixture kiểm đường đi `Paper → PUBLISHED_IN → venue:CVPR:2025:main` qua graph exporter và bước đọc/kiểm hash trước import với `project_id=mxh_cv_trend`. Verifier metadata hiện đối chiếu project với `mxh_cv_700` trong contract cũ. H5 có thể tiếp tục xuất metadata trung gian theo quy ước này. Tới H7, A cần truyền project trend khi tạo và kiểm NLP manifest. A và B cần thống nhất cờ `graph_ready` ở giao diện H7 vì adapter A4 hiện nhận `false`, còn PLAN yêu cầu `true`. H8 vẫn cần kiểm contract đầy đủ và hai lượt nạp Neo4j trên snapshot thật.

**CVPR 2026.** Cùng seed và quy tắc trên, khóa 350/4.042 ứng viên main track. H4 dùng [registry theo thứ hạng](../data/processed/cvpr2026/input_registry.csv). [Lock](../config/a_cvpr2026_350_selection.json) lưu hash của listing và registry. Pilot metadata ở phần H5 đo độ phủ trên 20 bài đầu tiên.

## Metadata CVPR 2025 và 2026 (H5)

Chạy từ gốc repo với Python 3.12. Replay dùng các phản hồi CVF và OpenAlex đã lưu. Để thu lần đầu, bỏ `--offline` ở lệnh collector và cấu hình `OPENALEX_API_KEY` trong môi trường hoặc file `.env` local.

```powershell
$year = 2026  # Đổi thành 2025 để replay kỳ trước
py -3.12 -B -X utf8 -m src.collect --config "config/a_cvpr${year}_350.json" --offline
py -3.12 -B -X utf8 -m src.clean --config "config/a_cvpr${year}_h5.json"
py -3.12 -B -X utf8 -m src.clean.h5_coverage --year $year
```

H7 đọc từng bảng theo trường `files` của [manifest 2025](../data/processed/cvpr2025/h5/snapshot_manifest.json) hoặc [manifest 2026](../data/processed/cvpr2026/h5/snapshot_manifest.json). Bảng dùng chung với snapshot collector có thể nằm ngoài thư mục `h5/`. Lệnh cuối verify lại snapshot, so rank, ID và URL với lock rồi xuất [độ phủ 2025](../outputs/trend/quality/cvpr2025_h5.json) hoặc [độ phủ 2026](../outputs/trend/quality/cvpr2026_h5.json). Một bài có affiliation khi có ít nhất một tác giả liên kết được với tổ chức qua bằng chứng của chính bài đó. Ở mức lượt tác giả, đếm `authorship_id` riêng biệt để một tác giả có nhiều tổ chức vẫn chỉ tính một lần. Các liên kết thiếu bằng chứng giữ null. Xem `needs_review.csv` theo manifest.

Để tái tạo [pilot metadata CVPR 2026](../outputs/trend/quality/cvpr2026_pilot.json), chạy `py -3.12 -B -X utf8 -m src.integration.cvpr_metadata_pilot`. Pilot đếm tổ chức xuất hiện trong Work OpenAlex đã khớp. H5 đo liên kết đã qua bước xác minh danh tính và affiliation theo bài.

Với CVPR 2026, quy tắc `openalex-work-match` v1.2.0 kiểm tra tiêu đề, đủ tác giả theo đúng thứ tự và bằng chứng DOI, hội nghị/năm hoặc liên kết phiên bản. Dạng tên “họ, tên” được đối chiếu với cách ghi gốc tại cùng vị trí trên CVF. Liên kết arXiv kiểm mã bài trên URL chính thức, phiên bản chỉ định và năm xuất bản. Trong báo cáo H5, nhóm `linked_version_only` cho biết tổ chức được ghi trên Work liên kết. Khi dùng Q1/Q3, cần ghi rõ nguồn này vì affiliation có thể thay đổi giữa bản preprint và thời điểm hội nghị.
