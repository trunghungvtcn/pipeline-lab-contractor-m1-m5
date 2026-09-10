# F01–F14 — bảng sửa gửi reviewer

Gói này sửa source theo `THBISON-VENDOR-INDEPENDENT-REVIEW-20260910`. Không merge, không deploy, không ghi Notion, không đổi phê duyệt knowledge.

`loads_strict('{"x":NaN}')` **raise `ValueError`** (cùng kiểu reject duplicate key). Probe gốc R14 không bọc try/except nên sẽ dừng ở bước parser — đó là reject đúng contract, không phải chấp nhận NaN.

| ID | P | Module | Test regression | Expected | Actual (sau sửa) |
|---|---|---|---|---|---|
| F01 / R01 | P1 | M5 `harness.py` | `test_r01_write_before_validate` | sentinel BEFORE, writes=0 | LOCATOR_REJECTED, sentinel BEFORE |
| F02 / R02 | P1 | M2 `store.py` | `test_r02_source_id_escape` | không ghi ngoài root | status error, không `escaped.json` |
| F03 / R03 | P1 | M2 `store.py` | `test_r03_existing_corrupt_blob` | freeze error | CORRUPT_CAS |
| F03 / R04 | P1 | M2 `store.py` | `test_r04_manifest_forgery` | verify false | False |
| F04 / R05 | P1 | M2 `store.py` | `test_r05_replay_identity` | cùng payload_sha256 | hai digest trùng |
| F05 / R06 | P1 | M3 `ledger.py` | `test_r06_cancel_finalize_race` | CANCELLED | CANCELLED, finalize error |
| F06 / R07 | P1 | M3 `ledger.py` | `test_r07_negative_and_over_budget` | reject âm / 1100 | INVALID_AMOUNT / BUDGET_EXCEEDED |
| F06 / R08 | P1 | M3 `ledger.py` | `test_r08_crash_reclaim_bounded` | claim hữu hạn | 2 ok, còn lại error |
| F07 / R09 | P1 | M4 `fake_transport.py` | `test_r09_readonly_blocks_projection_and_unknown` | WRITE_BLOCKED | WRITE_BLOCKED, query vẫn chạy |
| F08 / R10 | P1 | M4 transport/adapter | `test_r10_same_revision_terminal_rollback` | giữ SUCCEEDED | state SUCCEEDED |
| F08 / R11 | P1 | M4 `adapter.py` | `test_r11_untrusted_retry_override` | 1 call | 1 call, PROJECTION_TIMEOUT |
| F08 / R15 | P1 | M4 `adapter.py` | `test_r15_unmapped_and_protected_fields` | không forward Decision | properties `{}` |
| F09 / R12 | P1 | M5 `harness.py` | `test_r12_projection_retry_after_terminal` | replay project, không recompute | replay ok, page SUCCEEDED, cùng result_digest |
| F09 / R13 | P1 | M5 identity | `test_r13_source_in_identity` | DIGEST_CONFLICT | DIGEST_CONFLICT |
| F10 | P1 | M1 `resolver.py` | `test_no_read_on_rejected_locator`, `test_expected_hash_mismatch`, `test_dot_and_double_sep_rejected` | 0 read, HASH_MISMATCH, alias reject | PASS |
| F11 / R14 | P2 | M1–M4 `canon.py` | `test_loads_strict_rejects_nonfinite` | raise NaN/Inf | raise |
| F12 | P1 | M5 tests + Linux | `test_e2e` equality thật; `test_concurrent_*` thu exception; `run_linux.sh` gọi `run_all.py`; Dockerfile cài pytest lúc build | không `a==b or a` | đã sửa |
| F13 | P2 | M4 `snapshot.py` | `test_acquire_*` | raw≠redacted, missing target, drift, không forward auth | PASS |
| F14 | P2 | `run_all.py` | run dir mới, env whitelist, hash bỏ pycache, không hard-code notion_reads, verdict theo gate | CONTRACTOR_PASS khi 0 fail | PASS trên Linux sandbox Python 3.10 |

## Việc chưa chứng minh trong đợt này (NOT_VERIFIED)

- Docker `network_mode: none` trên host reviewer — image đã khai báo, chưa chạy container ở đây.
- Race symlink ancestor/root trên kernel barrier riêng ngoài openat+O_NOFOLLOW.
- Đọc Notion thật: `notion_real_read=NOT_VERIFIED`. Không dò workspace, không ghi Status/Decision.
- Power-loss từng byte tại finalize M2: crash injection trước MANIFEST vẫn unpublished; kill OS không tái hiện.

Không tuyên bố production-ready.
