# M3 — Durable job ledger

> Đọc `shared/SCOPE_UPDATE.md` ở gốc gói trước khi thực hiện. Phạm vi mới cho phép đọc database Notion thật được chỉ định; các câu cấm dữ liệu thật/Notion bên dưới chỉ còn áp dụng ngoài ngoại lệ đó. Mọi kiểm thử ghi vẫn dùng giả lập.

Phát triển package độc lập triển khai Job API trên SQLite tạm hoặc durable store nhúng tương đương. Không dùng queue/database thật.

Acceptance bắt buộc: sequential và concurrent duplicate admission chỉ tạo một job/intent; same key khác digest conflict; hai controller chỉ một claim; counter/deadline giữ qua restart; retry permanent/transient hữu hạn; lease/fence chặn stale worker; timeout external effect chuyển reconcile; terminal replay không restart; cancellation chặn output muộn; cost reservation không race vượt budget.

Dùng barrier/process thật cho concurrency và restart process thật cho durability. Bàn giao schema/migration additive, package source, lockfile, Linux JUnit, event-history receipts, `REPORT.*`, checksum.
