# Kiểm tra cấu hình OpenAlex và bàn giao collector cho B

Ngày 08/11/2026, nhánh feat/a2-collector-v2. Chưa commit/push.

- Key đã nạp: có. Request kiểm tra duy nhất tới /works?per_page=1: thành công, HTTP 200; không lỗi xác thực, mạng hoặc quota trong request này. Kết quả an toàn ở auth_check.json. Không lưu response body hoặc header.
- Request thật được thực hiện khi terminal ở thư mục cha repo, vẫn đọc đúng .env của repo. Môi trường không rỗng được ưu tiên; môi trường rỗng/không có mới đọc .env tại REPO_ROOT. Không cần dependency mới, không cài package global hoặc chỉnh .venv.
- .env Git ignored và không tracked; .env.example chỉ có placeholder. Cả hai giữ nguyên bytes; không sửa biến Neo4j hoặc biến khác.
- 42 test qua, gồm precedence, root độc lập CWD, không sửa cấu hình, đúng một request, lỗi 401/403/429/network được phân loại không lộ exception/key, và fixture ICCV. Log: auth_readiness_tests.log.
- Verifier offline của snapshot hiện hành qua: 30 Paper, 159 authorship, 89 source records, 60 text versions, 12 bảng/741 records; snapshot ID không đổi: snapshot:v2:737f8bc206c9a39e0b99d6ffb085036acbbfdf323556b717e5634c5cea0d64ba.
- Không chạy collector production 30/350 bài. Test chỉ dùng mock mạng và replay fixture/cache tại thư mục tạm. Contract, raw, processed và phần việc B không sửa.

## Kết luận bàn giao

Có thể gửi collector dùng chung và config mẫu cho B để chạy pilot ICCV. Mẫu config chưa phải registry/dữ liệu ICCV: B cần tự cấp input_registry.csv đúng target_count, owner B và ICCV 2023, sau đó kiểm tra trên máy mình. API key mới không thay kết quả matching cũ: pilot đã xử lý được 30/30 Work bằng truy cập không key, đạt 27 matched và 3 needs_review; ba trường hợp còn lại là thiếu đối chứng title/byline, không phải lỗi xác thực. Chưa resolve affiliation/Author.

Không coi đây là nghiệm thu lô 350. Phần lựa chọn registry/manifest 350 (giữ 30 A đã khóa), review mơ hồ và pilot thật phía B vẫn còn. Code không tự thêm 320 bài khi thay target_count.

## Tệp cập nhật ở bước này

- src/collect/cache.py: tái sử dụng loader key, thêm root mặc định và parse giá trị nháy/comment, không phụ thuộc CWD.
- src/collect/auth_check.py: một GET nhỏ, Bearer header, không retry/body/cache, lỗi được lọc.
- quality/checks/test_a2_auth.py: 5 test mới.
- README.md, handoff/a/A2_HANDOFF.md và báo cáo/log tại outputs/a2_cvpr2024/pilot.

## Lệnh

```powershell
py -3.12 -B -X utf8 -m src.collect.auth_check
py -3.12 -B -X utf8 -m unittest discover -s quality/checks -p "test_a2_*.py" -v
py -3.12 -B -X utf8 -m src.collect.verify --manifest data/processed/cvpr2024/pilot/snapshot_manifest.json
```

Lệnh auth_check tự gửi một request mới mỗi khi gọi; hai lệnh sau không cần mạng. Trường hợp lỗi: exit 2 và error_category, không coi authentication là not_found. Request HTTP 200 xác nhận kết nối ở thời điểm kiểm tra, không phải đo quota còn lại hoặc sức chịu tải của lô 350.
