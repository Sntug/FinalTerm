# Tiếp tục dự án trong Codex

Dùng Codex với repo nhóm cho các thay đổi code, test, data contract và import Neo4j. Dùng ChatGPT Work để đọc plan, phân tích số liệu, chuẩn bị bảng/hình và báo cáo. Các quyết định quan trọng phải được ghi lại trong repo để cả hai môi trường đọc được, tránh dựa hoàn toàn vào lịch sử chat.

## Đưa gói này vào repo

1. Giải nén và mở thư mục bằng VS Code/Codex để kiểm tra riêng.
2. Clone/pull repo nhóm do B tạo. Tạo nhánh `feat/a1-pilot-schema-v1`.
3. Yêu cầu Codex so sánh gói với repo đang có. Ghép các module thay vì ghi đè toàn bộ file của B. Gói này chưa biết cấu trúc hoặc remote GitHub của nhóm.
4. Chạy collect offline, quality, unit tests; xem diff code/schema và bảng kiểm tra B. Commit các file đã đọc, mở PR để B review nếu nhóm dùng PR.

## Nội dung gửi cho Codex khi bắt đầu A2

```text
Đây là repo nhóm môn Phân tích phương tiện mạng xã hội trong kinh doanh.
Tôi là A, phụ trách 350 bài CVPR 2024. B phụ trách 350 ICCV 2023.
Đọc README.md, docs/DATA_CONTRACT.md, outputs/REVIEW_A1_B.md,
config/project.json và schemas/data_contract.json trước khi sửa code.
Plan gốc là Plan_FinalTerm.docx nếu file đã được thêm vào repo hoặc đính kèm.

A1 hiện có 30+30 CVF pilot, schema v1, source snapshots và kiểm tra offline.
Tiếp tục A2 theo từng thay đổi nhỏ: mở manifest A lên 350 (giữ 30 đã khóa),
viết OpenAlex collector cache/retry/resume và báo ứng viên ghép chưa chắc chắn.
Không đổi paper_id, không gộp Author bằng tên, không tạo affiliation giả,
không đổi 8 node labels hay 10 relation types, không sửa graph của B âm thầm.
Nếu thay schema, mô tả migration và tăng version phù hợp.
Chạy kiểm tra đã có, thêm test có ý nghĩa cho lỗi mới, báo file đổi và giới hạn.
API key đọc từ .env hoặc biến môi trường, không ghi vào code/log/data.
Chưa push hoặc thay đổi nhánh chính khi tôi chưa yêu cầu.
```

Mỗi lần làm một hạng mục A2/A3/A4. Sau mỗi lần: xem changed files, đọc diff, chạy lệnh xác minh, commit một mục rõ ràng. Khi nhờ Work viết báo cáo, cung cấp output cùng snapshot/tag Git để số liệu và mô tả code khớp nhau.

Hướng dẫn chính thức về giao diện và môi trường:

- [ChatGPT Work và Codex](https://learn.chatgpt.com/docs/use-chatgpt)
- [Local Worktree và Cloud](https://learn.chatgpt.com/docs/environments/modes)

Tài liệu này đề xuất quy trình theo nhu cầu review/commit của nhóm; không xác nhận các tính năng cụ thể đã được bật cho tài khoản hay máy của bạn.
