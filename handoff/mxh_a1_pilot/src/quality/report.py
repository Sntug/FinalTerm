"""Generate the handoff report from observed values, not planned graph targets."""
from pathlib import Path


def write_report(root: Path, summary: dict, manifest: dict) -> None:
    rows = summary["coverage"]
    counts = summary["counts"]
    table = ["| Trường | A có / 30 | B có / 30 | Diễn giải phần thiếu |", "|---|---:|---:|---|"]
    for field in [r["field"] for r in rows if r["owner"] == "A"]:
        a = next(r for r in rows if r["owner"] == "A" and r["field"] == field)
        b = next(r for r in rows if r["owner"] == "B" and r["field"] == field)
        meaning = "Chưa chạy bước làm giàu OpenAlex" if a["missing_interpretation"] == "not_collected_in_A1" else "Không thấy trong HTML CVF nếu còn thiếu"
        table.append(f"| {field} | {a['present']} | {b['present']} | {meaning} |")
    sources = "\n".join(f"- [{c['conference']} {c['conference_year']} main conference]({c['listing_url']}): {c['candidate_count']} URL duy nhất; chọn {c['selected_count']} bài." for c in manifest["corpora"])
    text = f"""# Bàn giao A1 và kiểm tra pilot B

A1 hoàn tất ở phạm vi schema v1, registry, 30 bài CVPR 2024 thô, snapshot nguồn và thống kê trường thiếu. Đã tải và đối chiếu thêm 30 bài ICCV 2023 của B để kiểm tra cùng một hợp đồng dữ liệu. Đây là pilot 60 bài, chưa phải 700 bài, chưa phải pipeline toàn nhóm chạy tới Neo4j.

## Kiểm tra dữ liệu B

File đầu vào có đúng 30 dòng và 7 cột. Không ghi đè file gốc. Sau khi kiểm tra, cả 30 `paper_id` khớp URL, không có ID/URL trùng, đúng owner B, ICCV 2023, thuộc danh sách main conference chính thức, HTTP 200 và metadata từng bài khớp hội nghị/năm. Title và danh sách tác giả được đọc từ HTML; abstract được kiểm tra có/thiếu.

Với mục tiêu bàn giao registry pilot, file B đạt kiểm tra cấu trúc và nguồn. File gốc chỉ là danh sách đăng ký; chưa chứng minh B đã thu đủ 30 Paper thô của B1. Gói này đã bổ sung metadata CVF cho 30 URL đó nhưng giữ owner=B để chỉ phân công corpus, không coi đó là bằng chứng B tự viết/chạy code. Chưa có link repo, quyền truy cập, cấu hình Neo4j hay truy vấn nhập được gửi kèm, nên chưa xác minh các phần còn lại của B1. `False` trong báo cáo nghĩa là chưa có bằng chứng xác minh, không khẳng định bạn B chưa thực hiện.

DOI trống được phép khi có CVF URL ổn định. Không suy DOI từ slug. Trường `provisional_pilot` của file gốc được giữ ở phiếu review; file v1 dùng `cvf_verified`, chỉ nghĩa là metadata CVF vượt kiểm tra tự động. Seed/cách chọn 30 bài của B chưa được cung cấp, vì vậy giữ nguyên danh sách B, không gán seed của A cho B.

## Đầu ra A và thống kê thực tế

Tổng {counts['papers']} Paper duy nhất, A={counts['A_papers']}, B={counts['B_papers']}; {counts['source_records']} bản ghi nguồn gồm hai danh sách hội nghị và 60 trang bài. Có {counts['authorship_observations']} lượt đứng tên (A={counts['A_authorship_observations']}, B={counts['B_authorship_observations']}). Đây là lượt tác giả theo bài, chưa phải số Author duy nhất và chưa dùng làm số nút graph.

{chr(10).join(table)}

Giá trị thiếu trong JSON là `null`; trong CSV là ô trống. Citation chưa thu không được gán 0. `affiliations` và `referenced_works` là `null`, không phải danh sách rỗng đã xác nhận. Ngày công bố giữ đúng độ chi tiết nguồn: năm hoặc tháng, không tự thêm ngày 01. URL arXiv/PDF chỉ được ghi nhận; gói này chưa tải hoặc xác minh nội dung của các nguồn đó.

## Cách lấy mẫu và truy vết

A lấy toàn bộ URL của CVPR 2024 main, chuẩn hóa, khử trùng URL rồi xếp tăng dần theo SHA-256 của `seed + newline + URL`, seed={manifest['seed']}; chọn 30 URL đầu. Thuật toán không phụ thuộc thứ tự trang hoặc phiên bản bộ sinh số ngẫu nhiên Python. Cách lấy mẫu không cố ý cân bằng Task/Method/Dataset, vì vậy pilot chưa chứng minh đủ 10 loại cạnh.

{sources}

B giữ nguyên 30 URL và thứ tự đã bàn giao. Khi mở rộng lên 350: giữ 30 bài đã khóa, xếp các URL còn lại bằng cùng quy tắc rồi chọn thêm 320; ghi thuật toán và seed trong manifest mới. Thao tác mở rộng thuộc A2/B2 và chưa chạy ở gói này.

`source_records.jsonl` liên kết tới snapshot HTML nén gzip bằng `raw_path`, SHA-256 của bytes HTML gốc và thời điểm tải UTC. `paper_id` không đổi khi bổ sung DOI hoặc OpenAlex. `authorships.csv` giữ thứ tự và tên nguồn theo từng bài; `author_id` để trống, `identity_status=unresolved` cho tới khi đối sánh có chứng cứ. Không gộp người bằng chuỗi tên, không dựng cơ quan từ tên/email.

## Schema đã khóa cho pilot

Phiên bản kỹ thuật 1.0.0 được ghi ở `schemas/data_contract.json`, `schemas/paper.schema.json` và `docs/DATA_CONTRACT.md`. Registry v1 giữ 7 cột cũ và thêm 8 cột mô tả scope, track, title, phiên bản và truy vết. Metadata, authorship và source records là các bảng riêng. Hợp đồng có đủ 8 nhãn nút và 10 loại quan hệ theo plan; phần graph là hợp đồng cho bước sau, chưa có node/edge thực nghiệm.

Đây là bản schema để hai thành viên dùng chung trong repo; chưa có xác nhận review của B trong phiên làm việc này. Nếu thay đổi sau review, sửa version và ghi quyết định trong commit, không tự đổi tên cột ở một nhánh.

## Phần tiếp theo

1. B đọc contract, kiểm tra 30 dòng của mình trong file v1 và xác nhận phần repo/Neo4j/nhập chuỗi đơn giản của B1.
2. A2/B2 mở manifest lên 350 mỗi người, bổ sung collector OpenAlex với key cấu hình riêng, cache và quy tắc ghép DOI/venue/tác giả. Không lấy tương đồng title làm quyết định ghép duy nhất.
3. Đo tỷ lệ ghép, affiliation, references; kiểm tra tối thiểu 10 phép ghép và 10 trường hợp tác giả dễ nhầm theo plan. Giai đoạn A1 chưa thực hiện vì chưa gọi OpenAlex.
4. Tiếp tục A3/A4/B3/B4/B5, chạy NLP và Neo4j. Chỉ kết luận đủ nút/cạnh hoặc chất lượng >90% sau khi có số đo tương ứng.

## Tái lập và giới hạn kiểm tra

Chạy `python -m src.collect --offline`, sau đó `python -m src.quality` và `python -m unittest discover -s tests -v`. Mỗi lệnh chạy ở thư mục gốc gói. Code không cần thư viện ngoài cho A1, không cần API key. Cache có hash sai hoặc bị thiếu ở chế độ offline làm lệnh thất bại rõ ràng. HTTP 403/429 dừng truy cập, không tìm cách vượt chặn.

Kiểm tra tự động bao gồm schema JSON, trùng ID/URL, số lượng 30+30, phân công, đúng listing/detail, thứ tự tác giả, khóa ngoại và hash snapshot. Tính đúng ngữ nghĩa khoa học, đồng nhất người và toàn bộ đồ thị chưa được đánh giá. Neo4j Windows chưa được chạy từ môi trường này.

Snapshot: `{summary['snapshot_id']}`.
"""
    (root / "outputs/REVIEW_A1_B.md").write_text(text, encoding="utf-8")
