# M2 — Immutable asset store

> Đọc `shared/SCOPE_UPDATE.md` ở gốc gói trước khi thực hiện. Phạm vi mới cho phép đọc database Notion thật được chỉ định; các câu cấm dữ liệu thật/Notion bên dưới chỉ còn áp dụng ngoài ngoại lệ đó. Mọi kiểm thử ghi vẫn dùng giả lập.

Phát triển package độc lập triển khai Asset API. Input chỉ là file synthetic nhỏ. Không tải corpus hay gọi URL thật.

Acceptance bắt buộc: hai path trùng basename nhưng khác bytes không overwrite; cùng bytes dedupe nhưng giữ hai provenance; locator ngoài source bị reject trước read; read/hash/publish cùng byte snapshot; crash trước manifest không tạo success; crash tại finalize có đúng một complete output hoặc trạng thái recoverable; replay idempotent; manifest canonical và kiểm lại toàn bộ hash/size.

Bàn giao: package source, format manifest versioned, recovery procedure, lockfile, tests Linux/JUnit, crash-injection receipts, `REPORT.*`, checksum.
