# Gói audit Pipeline Lab — M1–M5 (sau review độc lập)

Ngày đóng gói: 2026-09-10  
Verdict synthetic: `CONTRACTOR_PASS` (78/78, 0 skip).  
`notion_real_read` và `linux_docker`: `NOT_VERIFIED`.  
Không dùng `PRODUCTION_READY`. PR #1 vẫn draft — chưa merge, chưa deploy.

Đây là **source + test + spec + FIXES.md** sau khi sửa F01–F14. Dùng để đọc code và chạy lại pytest. Không phải Knowledge Factory, không phải data sản xuất.

## Có gì trong ZIP

| Thư mục / file | Nội dung |
|---|---|
| `m1_locator/` … `m5_integration/` | Source + test + pyproject 1.1.0 |
| `spec/` | TASK.md + CONTRACTS.md |
| `FIXES.md` | Bảng F01–F14, test ID, expected/actual |
| `pack.py` | Nén ZIP bằng Python `zipfile.ZIP_DEFLATED` |
| `pack_gzip.py` | Nén `.tar.gz` bằng Python `gzip.GzipFile` (không dùng lệnh `gzip`) |
| `run_all.py` | Run directory mới, env whitelist, hash không lẫn pycache |
| `REPORT.md` / `REPORT.json` | Kết quả chạy gói này |
| `MANIFEST.json` / `SHA256SUMS.txt` | Checksum từng file |

## Không có trong ZIP

- Snapshot Notion thật, `__pycache__`, data THBISON, source Knowledge Factory (PR #1)
- Token / secret
- `artifacts/` runtime

## Chạy test

Python 3.10+ và `pytest`:

```sh
python3 -m pip install pytest
python3 run_all.py
```

Kỳ vọng: **78 passed, 0 failed, 0 skipped**, verdict `CONTRACTOR_PASS`.

Linux / Docker: xem `m5_integration/RUNBOOK.md`. Phase test `network_mode: none`.

`loads_strict` reject NaN/Infinity bằng cách **raise** — giống duplicate key.

## Ranh giới giữ nguyên

Không merge, không deploy, không scheduler, không train, không đổi Status / Decision / Reviewer Note.
