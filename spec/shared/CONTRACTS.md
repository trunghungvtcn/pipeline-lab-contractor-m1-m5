# Shared contracts v1

> Đọc `shared/SCOPE_UPDATE.md` ở gốc gói trước khi thực hiện. Phạm vi mới cho phép đọc database Notion thật được chỉ định; các câu cấm dữ liệu thật/Notion bên dưới chỉ còn áp dụng ngoài ngoại lệ đó. Mọi kiểm thử ghi vẫn dùng giả lập.

## Nguyên tắc chung

- Python 3.12; API thuần Python, không framework bắt buộc.
- JSON canonical: UTF-8, sorted keys, compact separators, không NaN/Infinity, duplicate key bị reject.
- Mọi public result có `schema_version`, `status`, `reason_code`, `trace_id`.
- Clock, filesystem, network và ID generator phải inject được để test.
- Không module nào gọi dịch vụ thật trong test.
- Log không chứa secret hoặc raw document ngoài synthetic fixture.

## M1 Locator API

`resolve(root, locator, profile) -> ResolvedLocator`

Profile bắt buộc khai báo `dialect`, `root_id`, `case_policy`, `unicode_policy`. Reject absolute, drive, UNC, device, ADS, NUL/control, traversal, ambiguous aliases và symlink escape trước khi đọc.

## M2 Asset API

`freeze(job_root, sources, reader) -> FreezeReceipt`

Mỗi source có `source_id`, validated relative locator và expected SHA256. Blob lưu theo digest; nhiều provenance có thể trỏ cùng blob. Stage toàn bộ rồi atomic finalize. Không published manifest nếu fail/crash.

## M3 Job API

`admit(scope, idempotency_key, request_digest) -> JobReceipt`

Same scope/key/digest trả existing job; khác digest trả conflict. Claim trả lease token/fence. Attempt, deadline và retry class bền qua restart. Worker cũ không finalize sau khi mất lease. Ambiguous external effect chuyển `RECONCILE_REQUIRED`.

## M4 Projection API

`project(event, expected_revision, transport) -> ProjectionReceipt`

Projection chỉ phản chiếu job state; không tạo/rerun compute. Event cũ không rollback revision. Timeout chỉ retry projection theo budget. Transport test là fake in-memory hoặc sandbox mới, không tài nguyên THBISON.

## M5 Integration contract

M5 chỉ import public API/package metadata. Một synthetic request đi qua admission → freeze → synthetic compute → terminal ledger → projection. Replay/restart không tạo logical output thứ hai. Mọi artifact và input có hash.
