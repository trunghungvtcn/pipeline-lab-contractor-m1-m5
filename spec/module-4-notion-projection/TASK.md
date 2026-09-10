# M4 — Notion-compatible projection adapter

> Đọc `shared/SCOPE_UPDATE.md` ở gốc gói trước khi thực hiện. Phạm vi mới cho phép đọc database Notion thật được chỉ định; các câu cấm dữ liệu thật/Notion bên dưới chỉ còn áp dụng ngoài ngoại lệ đó. Mọi kiểm thử ghi vẫn dùng giả lập.

Phát triển adapter theo Projection API. Mặc định dùng fake transport in-memory. Nếu cần chứng minh connector, chỉ tạo database/page trong Notion sandbox hoàn toàn mới của nhà thầu; không search workspace và không dùng bất kỳ tên/ID THBISON nào.

Acceptance bắt buộc: auth/target scope trước write; duplicate event idempotent; event revision cũ không rollback; sync timeout retry projection hữu hạn nhưng không gọi compute; terminal state không quay về Ready; property mapping versioned; log/receipt che token và signed URL; fake transport chạy đủ suite offline.

Bàn giao package source, fake server/transport, sandbox setup template không chứa ID thật, tests Linux/JUnit, `REPORT.*`, checksum. Không thay approval/decision fields ngoài synthetic schema.
