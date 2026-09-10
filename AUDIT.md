# Gói audit Pipeline Lab — M1–M5 (G1–G12)

Ngày: 2026-09-10  
Tag cũ giữ nguyên: `v2026.09.10` (`e618646f7cd42d42e7b55aa9cb6e333d524c188b`)  
Nhánh sửa: `fix/g1-g12-20260910`  
Verdict: `CONTRACTOR_PARTIAL` — 95/95 synthetic trên Linux sandbox. `linux_docker` và `notion_real_read`: NOT_VERIFIED.

Không merge Knowledge Factory, không deploy, không VPS.

## Có gì

| File | Nội dung |
|---|---|
| `m1_locator/` … `m5_integration/` | Source 1.2.0 + test |
| `FIXES.md` | Bảng G1–G12 |
| `SUPPORT.md` | Linux/Python 3.12 only |
| `requirements.lock` + `vendor/wheels/` | pytest hashed, offline install |
| `pack.py` / `pack_gzip.py` | zipfile / gzip.GzipFile |

## Chạy

```sh
python3 run_all.py
```

Kỳ vọng modules 95 passed, 0 failed, 0 skipped. Overall PARTIAL cho đến khi Docker Linux và Notion target được cấp.
