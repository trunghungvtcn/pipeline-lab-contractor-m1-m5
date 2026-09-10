# Phạm vi cập nhật — Notion read-only

Người giao việc đã cho phép Grok đọc dữ liệu thật trên Notion. Tài liệu này thay thế mọi câu cấm toàn bộ truy cập Notion/dữ liệu THBISON trong gói. Các giới hạn khác giữ nguyên.

- Chỉ đọc database/data source được người dùng chỉ định bằng link hoặc ID, các page/block thuộc database đó và attachment liên quan. Không dò toàn workspace, không tự mở rộng sang database được liên kết.
- Được đọc schema, properties, nội dung và tải attachment cần thiết. Connector có toàn quyền không đồng nghĩa được ghi: cấm tạo/sửa/xóa page, schema, comment, Status, Decision, Reviewer Note và approval.
- Chưa có database link/ID được cấp trong task Grok thì ghi NOTION_TARGET_MISSING; tiếp tục phần synthetic. Không đoán ID từ tài liệu lịch sử.
- M4 là đầu mối thu snapshot read-only trước bước test. Ghi source page/block/file ID, revision/last_edited_time, thời điểm UTC, size, SHA256 và lỗi quyền/quota cụ thể. Signed URL không là ID lâu dài. Nếu nguồn đổi trong lúc thu, ghi SNAPSHOT_DRIFT và không chứng nhận snapshot nhất quán.
- Snapshot thật chỉ lưu trong vùng riêng có kiểm soát, ngoài Git và ngoài ZIP source. Không đưa token vào log, báo cáo hay môi trường test. Không tái upload raw dữ liệu lên GitHub/Notion hoặc công khai artifact CI.
- M1–M4 vẫn phát triển độc lập bằng synthetic fixtures. Sau khi M4 bàn giao snapshot receipt, các test tương thích dữ liệu thật chạy offline trên bản sao ghim hash. M5 nhận package source và receipt; dữ liệu thật được cấp riêng trong môi trường riêng tư.
- Kiểm thử ghi/projection chỉ chạy fake transport. Test read-only phải chặn mutation theo tên thao tác/API semantics; không chặn nhầm POST query chỉ đọc. Kiểm redirect attachment không chuyển credential Notion sang host tải file.
- Báo cáo tách SYNTHETIC_TEST, NOTION_READ_VERIFIED và SNAPSHOT_OFFLINE_TEST. Không dùng test giả lập để tuyên bố dịch vụ thật đã đạt.
- Không truy cập VPS, repository hiện tại, backup hoặc dịch vụ THBISON khác. Không deploy, bật scheduler, train hoặc gọi model trả phí.

Trạng thái báo cáo: notion_access_mode=READ_ONLY; notion_reads_performed=true/false theo thực tế; real_notion_writes=false; other_thbison_resources_accessed=false. Không còn dùng thbison_accessed=false hoặc real_services_called=false để phủ nhận các lượt đọc Notion đã được cho phép.
