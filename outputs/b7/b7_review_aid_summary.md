# B7 — Gợi ý chấm trước (pre-review aid) cho reviewer B

**Lưu ý quan trọng:** đây là gợi ý do AI tạo ra từ dữ liệu offline (source_records, authorships.csv, text_versions.jsonl, nodes/edges). B phải tự kiểm tra và xác nhận từng dòng trước khi nhập vào form; không được sao chép máy móc. Không có form nào bị sửa. Các file form A6 và dữ liệu snapshot giữ nguyên.

Phạm vi: 60 dòng cạnh (50 primary + 10 cross) và 25 dòng node có `assigned_reviewer == B`, giữ đúng thứ tự trong form. Chi tiết từng dòng nằm ở `outputs/b7/b7_review_aid.csv` (cột checked_sources và finding).

## Cách kiểm tra

- AUTHORED, AFFILIATED_WITH, PUBLISHED_IN, BASED_IN: đối chiếu bản ghi OpenAlex work_detail (đã giải nén từ raw_path), CVF paper_detail và authorships.csv.
- COAUTHORED_WITH và COLLABORATED_WITH: dựng lại tập paper core có cả hai đầu mút từ authorships.csv và OpenAlex; cả 12 cạnh khớp tập paper_ids và weight.
- CITES: kiểm tra openalex_id của paper được trích nằm trong referenced_works của paper trích, và id đó khớp tiêu đề.
- NLP: cắt đúng đoạn bằng offset trong text_versions.jsonl (khớp evidence_text ở mọi dòng), đọc cả câu.
- Node: so với các node cùng tên chuẩn hóa về ORCID, OpenAlex ID, cơ quan, đồng tác giả, chủ đề, đồng thời đọc raw ORCID/affiliation.

## Đếm theo loại quan hệ (cạnh) và node

| Loại | correct | incorrect | unverifiable | tổng |
|---|---:|---:|---:|---:|
| AFFILIATED_WITH | 6 | 0 | 0 | 6 |
| AUTHORED | 6 | 0 | 0 | 6 |
| BASED_IN | 6 | 0 | 0 | 6 |
| CITES | 6 | 0 | 0 | 6 |
| COAUTHORED_WITH | 6 | 0 | 0 | 6 |
| COLLABORATED_WITH | 6 | 0 | 0 | 6 |
| EVALUATED_ON | 6 | 0 | 0 | 6 |
| Node:Author | 14 | 3 | 8 | 25 |
| PUBLISHED_IN | 6 | 0 | 0 | 6 |
| STUDIES_TASK | 6 | 0 | 0 | 6 |
| USES_METHOD | 6 | 0 | 0 | 6 |
| **Tổng** | 74 | 3 | 8 | 85 |

## Đếm theo owner

| Form / owner | correct | incorrect | unverifiable | tổng |
|---|---:|---:|---:|---:|
| edge / owner A | 31 | 0 | 0 | 31 |
| edge / owner A/B | 3 | 0 | 0 | 3 |
| edge / owner B | 26 | 0 | 0 | 26 |
| node / owner A | 13 | 2 | 8 | 23 |
| node / owner A/B | 1 | 0 | 0 | 1 |
| node / owner B | 0 | 1 | 0 | 1 |
| **Tổng** | 74 | 3 | 8 | 85 |

Ghi chú: owner `A|B` là thực thể dùng chung của hai corpus. Cột owner theo đúng form; nhiều dòng được giao cho B nhưng owner là A.

## Đếm theo phase

| Phase | correct | incorrect | unverifiable | tổng |
|---|---:|---:|---:|---:|
| cross | 10 | 0 | 0 | 10 |
| node | 14 | 3 | 8 | 25 |
| primary | 50 | 0 | 0 | 50 |
| **Tổng** | 74 | 3 | 8 | 85 |

## Dòng nghi ngờ (incorrect / unverifiable)

| STT | form | loại | owner | đối tượng | gợi ý | nhóm lỗi | độ chắc | lý do |
|---:|---|---|---|---|---|---|---|---|
| 61 | node | Author | B | Guanbin Li | incorrect | identity | medium | Hai node Guanbin Li (A5042965510 ICCV, A5101691639 CVPR) cùng ORCID 0000-0002-4805-0926 trong OpenAlex, cùng Sun Yat-sen University, cùng chủ đề đa phương thức; nhiều khả năng cùng một người bị tách (identity split). Hợp đồng không tự gộp nên cần reviewer quyết định. |
| 62 | node | Author | A | Shanghang Zhang | incorrect | identity | medium | Hai node Shanghang Zhang (A5013030532 ICCV, A5040418528 CVPR) cùng ORCID 0000-0003-4047-3526 và cùng Peking University; rất có thể cùng một người bị tách thành hai node (identity split). |
| 63 | node | Author | A | Liang Lin | incorrect | identity | medium | Hai node Liang Lin (A5091923424 CVPR, A5100412937 ICCV) cùng ORCID 0000-0003-2248-3755 và cùng Sun Yat-sen University; rất có thể cùng một người bị tách (identity split). |
| 66 | node | Author | A | Bingbing Ni | unverifiable | identity | medium | Hai node Bingbing Ni (A5014362734, A5102795444) đều ở Shanghai Jiao Tong University, cùng lĩnh vực đồ họa, chung đồng tác giả Qiaoqiao Jin nhưng ORCID khác nhau (…7339-028X vs …5582-577X); có thể là một người bị tách nhưng ORCID xung đột nên offline không kết luận được. |
| 67 | node | Author | A | Yikai Wang | unverifiable | identity | medium | Node Yikai Wang này (Tsinghua, GaussianEditor, ORCID …8212-0222) khác rõ với Yikai Wang ở Fudan, nhưng node A5100747441 (Tsinghua/BNRist, Text-to-3D GS) chung đồng tác giả Feng Wang, Huaping Liu và cùng chủ đề 3D; ORCID khác nhau nên chưa kết luận được có bị tách hay không. |
| 73 | node | Author | A | Xingyu Zhou | unverifiable | identity | medium | Hai Xingyu Zhou (A5050708940, A5011261173) cùng UESTC, cùng đồng tác giả Shuhang Gu, ORCID khác nhau (…0523-5699 vs …3439-4450); có thể là một người bị tách nhưng ORCID xung đột nên không kết luận được offline. |
| 76 | node | Author | A | Zilong Chen | unverifiable | identity | medium | Hai Zilong Chen (A5101757449 GaussianEditor, A5006790291 Text-to-3D GS) cùng Tsinghua, chung đồng tác giả Feng Wang, Huaping Liu, ORCID khác nhau (…2977-1824 vs …0400-9470); có thể là một người bị tách nhưng ORCID xung đột nên chưa kết luận. |
| 77 | node | Author | A | Feng Wang | unverifiable | identity | medium | Ba node Feng Wang (A5029738971, A5100431251, A5115590901) đều Tsinghua và đều có Huaping Liu làm đồng tác giả nhưng ORCID khác nhau (…7553-3184, …4556-5326, …8775-4925); nhiều khả năng ít nhất hai node là cùng một người bị tách, nhưng ORCID xung đột nên không kết luận offline. |
| 78 | node | Author | A | Zhaoxiang Zhang | unverifiable | identity | medium | Hai Zhaoxiang Zhang (A5101589393, A5028016065) cùng CAS/Institute of Automation, chung đồng tác giả Junsong Fan, ORCID khác nhau (…1469-1469 vs …2648-3875); có khả năng cùng một người bị tách, ORCID xung đột nên chưa kết luận được. |
| 79 | node | Author | A | Xingyu Zhou | unverifiable | identity | medium | Hai Xingyu Zhou (A5011261173, A5050708940) cùng UESTC, cùng đồng tác giả Shuhang Gu, ORCID khác nhau; có thể một người bị tách nhưng ORCID xung đột nên không kết luận được offline (cặp với N12). |
| 83 | node | Author | A | Feng Wang | unverifiable | identity | medium | Feng Wang (A5115590901, GaussianEditor, Tsinghua, ORCID …8775-4925) chung đồng tác giả Huaping Liu với hai Feng Wang Tsinghua khác nhưng ORCID khác nhau; có thể bị tách, ORCID xung đột nên không kết luận được (cặp với N16). |

STT là số thứ tự dòng dữ liệu trong b7_review_aid.csv (cạnh 1-60, node 61-85); sample_id đầy đủ ở file CSV.

## Nhận xét chung

- Toàn bộ 60 cạnh được gợi ý correct: không phát hiện sai về bằng chứng gốc. Tuy vậy 6 cạnh CITES có evidence gắn trên cạnh chỉ là metadata chung (issue citation_evidence_specificity); referenced_works trong bản ghi OpenAlex thô thì xác nhận cặp trích dẫn. Nếu rubric yêu cầu bằng chứng trên chính cạnh, reviewer có thể chấm khác (nhóm missing_evidence).
- Các cạnh STUDIES_TASK/USES_METHOD/EVALUATED_ON dựa trên tiêu đề (6 dòng) có độ chắc medium vì node tác vụ/phương pháp thô (Transformer, Vision-Language Model, Object Detection).
- Vấn đề thực sự nằm ở node Author đồng tên: 3 cặp có cùng ORCID nhưng tách thành hai node (Guanbin Li, Shanghang Zhang, Liang Lin), và 8 dòng node có ORCID khác nhau nhưng cùng cơ quan/đồng tác giả nên chưa thể khẳng định. Xingyu Zhou, Yanfeng Wang và Feng Wang mỗi tên xuất hiện ở hai hoặc ba dòng node trong form (cùng một nhóm đồng tên), nên gợi ý của các dòng đó liên quan với nhau.
- authorships.csv có 439 authorship_id lặp (mỗi dòng một cơ quan), cần lưu ý khi đếm số lượt authorship.
