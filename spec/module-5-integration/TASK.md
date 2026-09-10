# M5 — Integration and Linux acceptance

> Đọc `shared/SCOPE_UPDATE.md` ở gốc gói trước khi thực hiện. Phạm vi mới cho phép đọc database Notion thật được chỉ định; các câu cấm dữ liệu thật/Notion bên dưới chỉ còn áp dụng ngoài ngoại lệ đó. Mọi kiểm thử ghi vẫn dùng giả lập.

Chỉ bắt đầu khi nhận bốn source artifact M1–M4 có checksum và verdict PASS. Không truy cập tài nguyên THBISON. Không sửa source module con; tích hợp qua shared contracts.

Dựng môi trường Linux tái lập bằng Docker/Compose hoặc script tương đương. Tách dependency acquisition khỏi offline test. Dùng network-disabled phase cho test; không truyền credential vào container. Tạo synthetic end-to-end: admit → resolve/freeze → deterministic fake compute → durable finalize → projection. Chạy duplicate, concurrent, restart, crash, stale lease, projection timeout và replay.

Gate cuối: lockfiles hợp lệ; dependency check; compile/lint/type nếu cấu hình; full suite exit 0; không skip/xfail/deselect để đạt PASS; node IDs lưu đầy đủ; source/artifact/input hashes nhất quán; scan package không có token/private key/raw THBISON data. Xuất source tích hợp hoàn chỉnh, Compose, runbook, rollback cho sandbox, JUnit/log, SBOM/dependency list, `REPORT.*`, `SHA256SUMS.txt`.

Verdict là `CONTRACTOR_PASS` hoặc `CONTRACTOR_PARTIAL`, tuyệt đối không ghi production ready/deployed.
