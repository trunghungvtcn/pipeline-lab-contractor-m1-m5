# M1 — Safe locator resolver

> Đọc `shared/SCOPE_UPDATE.md` ở gốc gói trước khi thực hiện. Phạm vi mới cho phép đọc database Notion thật được chỉ định; các câu cấm dữ liệu thật/Notion bên dưới chỉ còn áp dụng ngoài ngoại lệ đó. Mọi kiểm thử ghi vẫn dùng giả lập.

Phát triển package độc lập triển khai Locator API trong contract chung. Không xem source hiện tại. Dùng filesystem tạm và fixture synthetic tự tạo.

Acceptance bắt buộc: POSIX/Windows locator hợp lệ cùng resolve đúng bytes; thiếu profile bị reject; traversal/absolute/drive/UNC/device/ADS/control bị reject trước read; symlink escape và symlink-swap race không đọc ngoài; case/Unicode/separator alias bị reject; hash sai không auto-accept; graph cycle/depth/node cap kết thúc hữu hạn.

Bàn giao: package source, public type/interface docs, lockfile, tests Linux, JUnit, mutation/negative-test evidence, `REPORT.*`, checksum. Không monkeypatch path global, không basename fallback.
