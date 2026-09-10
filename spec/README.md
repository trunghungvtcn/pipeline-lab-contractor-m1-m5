# Gói giao việc Grok — 5 mô-đun độc lập

> Đọc `shared/SCOPE_UPDATE.md` ở gốc gói trước khi thực hiện. Phạm vi mới cho phép đọc database Notion thật được chỉ định; các câu cấm dữ liệu thật/Notion bên dưới chỉ còn áp dụng ngoài ngoại lệ đó. Mọi kiểm thử ghi vẫn dùng giả lập.

## Ranh giới bắt buộc

Nhà thầu phát triển từng mô-đun độc lập theo contract và tài nguyên giả lập trong gói này. Không được yêu cầu, tìm kiếm, đọc, clone, tải, suy luận hoặc truy cập bất kỳ repository, Notion workspace/database, VPS, bucket, backup, credential, corpus, source hay dữ liệu hiện tại nào của THBISON.

Kết nối GitHub và Notion của Grok chỉ được dùng với tài nguyên sandbox mới, do nhà thầu sở hữu hoặc được cấp riêng cho bài kiểm thử. Không dùng tên/ID hiện hữu của THBISON làm target. Không mở PR, issue, database hoặc page trong tài nguyên thật.

Mọi kiểm tra dịch vụ thật, migration dữ liệu thật và triển khai lên hạ tầng THBISON nằm ngoài phạm vi. Đội nội bộ sẽ tiếp nhận source, cấu hình secret/endpoint thật, kiểm tra tích hợp và triển khai sau.

## Năm nhiệm vụ

| Mô-đun | Thư mục | Đầu ra chính |
|---|---|---|
| M1 | `module-1-locator/` | Bộ phân giải locator đa dialect an toàn |
| M2 | `module-2-asset-store/` | Kho asset content-addressed, publish atomic |
| M3 | `module-3-job-ledger/` | Admission/idempotency/lease/retry ledger |
| M4 | `module-4-notion-projection/` | Adapter projection dùng Notion giả lập |
| M5 | `module-5-integration/` | Harness tích hợp, Linux CI và gói nghiệm thu |

M1–M4 phải có thể phát triển và test song song chỉ dựa trên `shared/CONTRACTS.md`. M5 không được sửa source của M1–M4 để ép tích hợp; nếu contract không khớp phải trả `CONTRACT_MISMATCH` cho owner tương ứng.

## Cách giao cho Grok

1. Tạo năm task độc lập, mỗi task chỉ nhận `shared/` và thư mục mô-đun của mình.
2. M1–M4 không nhận output hay lịch sử hội thoại của nhau.
3. Khi bốn task hoàn tất, tạo task M5 với bốn artifact source đã đóng gói và checksum.
4. Yêu cầu mỗi task xuất `REPORT.json`, `REPORT.md`, source hoàn chỉnh, test/JUnit và `SHA256SUMS.txt`.
5. Chỉ đội nội bộ quyết định tích hợp vào THBISON.

## Trạng thái không được phép thay đổi

`thbison_accessed=false`, `production_deployed=false`, `real_notion_writes=false`, `real_github_repo_mutated=false`, `paid_model_calls=false`, `scheduler_enabled=false`, `model_training=NOT_RUN`.
