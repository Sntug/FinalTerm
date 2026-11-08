# Collector dùng chung cho B

Hướng dẫn chuẩn: [Bàn giao A2](../../../handoff/a/A2_HANDOFF.md#bàn-giao). Mẫu: [collector.example.json](../../../config/collector.example.json). B tự cấp registry ICCV và cấu hình đường dẫn riêng; fixture ICCV không thay cho pilot thật của B.

Bước kiểm tra key trước đó thành công HTTP 200, giữ bằng chứng an toàn trong [auth_check.json](auth_check.json). Không gửi `.env`; đây không phải phép đo quota hiện tại hoặc nghiệm thu pipeline nhóm.
