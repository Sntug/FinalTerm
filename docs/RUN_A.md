# Trend app · Khóa mẫu CVPR (H1/H3)

Từ gốc repo, dùng Python 3.12. Hai lệnh sau đọc listing đã lưu trong Git và chạy offline.

```powershell
py -3.12 -B -m src.collect.trend_selection
py -3.12 -B -m unittest src.collect.test_trend_selection
```

**CVPR 2025.** [Cấu hình H1](../config/a_trend_project.json) cố định seed `20261103`. Từ listing CVF main track, parser chỉ lấy URL trang chi tiết bài đúng kỳ, bỏ trùng URL chuẩn, xếp tăng theo SHA-256 của UTF-8 `seed + "\n" + canonical_url`, hòa thì xét URL. Chọn 350/2.871 bài đầu. Khi thu metadata, bài thiếu abstract vẫn giữ ID và thứ hạng. [Danh sách xếp hạng](../data/processed/cvpr2025/candidates_ranked.csv) ghi toàn bộ ứng viên. [Lock](../config/a_cvpr2025_350_selection.json) ghi nguồn listing, hash raw, hash thứ hạng và hash registry. B và A dùng [input registry](../data/processed/cvpr2025/input_registry.csv) cho H4/H5. DOI và source ID của trang chi tiết để trống đến khi có bằng chứng từng bài. Replay từ chối ghi đè file khác byte.

**CVPR 2024.** Replay kiểm hash listing, hash bảng xếp hạng và registry đầu vào của lock cũ, rồi đối chiếu ID theo thứ tự với registry A5. Trong 2.715 ứng viên, mẫu thực tế khớp top 350 ở **350/350 ID và 350/350 vị trí**, kể cả 30 bài pilot giữ lại. Điều kiện chọn mẫu đạt. Độ phủ văn bản và tỷ lệ NLP chạy thành công cần đo riêng trước khi gắn nhãn xu hướng. [Kết quả đối chiếu](../outputs/trend/quality/cvpr2024_selection.csv)

**D5.** Giữ schema v2, 8 nhãn và 10 loại cạnh. Fixture kiểm đường đi `Paper → PUBLISHED_IN → venue:CVPR:2025:main` qua graph exporter và bước đọc/kiểm hash trước import với `project_id=mxh_cv_trend`. Verifier metadata hiện đối chiếu project với `mxh_cv_700` trong contract cũ. H5 có thể tiếp tục xuất metadata trung gian theo quy ước này. Tới H7, A cần truyền project trend khi tạo và kiểm NLP manifest. A và B cần thống nhất cờ `graph_ready` ở giao diện H7 vì adapter A4 hiện nhận `false`, còn PLAN yêu cầu `true`. H8 vẫn cần kiểm contract đầy đủ và hai lượt nạp Neo4j trên snapshot thật.
