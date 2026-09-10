# Prompt điều phối cho Grok

> Đọc `shared/SCOPE_UPDATE.md` ở gốc gói trước khi thực hiện. Phạm vi mới cho phép đọc database Notion thật được chỉ định; các câu cấm dữ liệu thật/Notion bên dưới chỉ còn áp dụng ngoài ngoại lệ đó. Mọi kiểm thử ghi vẫn dùng giả lập.

Điều phối năm nhiệm vụ trong gói này theo cơ chế cô lập. Trước khi chạy, xác nhận từng agent/task không có URL, ID, token, SSH key, source tree hoặc credential THBISON trong context hay environment. Nếu có, dừng `BOUNDARY_VIOLATION` và không đọc giá trị.

Khởi chạy M1, M2, M3 và M4 độc lập. Mỗi task chỉ được dùng contract chung, fixture synthetic của chính nó và tài nguyên GitHub/Notion sandbox mới. Không cho các task xem source của nhau. Mỗi task phải bàn giao source hoàn chỉnh có lockfile, Linux test, JUnit, coverage nếu đã cấu hình, SBOM/dependency list, checksum và báo cáo máy đọc được.

Sau khi M1–M4 đạt gate riêng, chuyển bốn source artifact đã checksum cho M5. M5 dựng integration bằng public interfaces; không sửa implementation của module con. Chạy clean Linux CI, test contract, concurrency, restart, crash injection, offline/no-secret gate và đóng gói source tích hợp.

Không truy cập hoặc kiểm tra dịch vụ thật. Không tự tích hợp vào repository/Notion/VPS THBISON. Kết quả cuối là `CONTRACTOR_PASS`, `CONTRACTOR_PARTIAL` hoặc `BOUNDARY_VIOLATION`, không dùng `PRODUCTION_READY`.
