# Gates after independent re-review of v2026.09.10.3

Baseline kept: `v2026.09.10.3` / `afac091e60bb6c8a0f0630964e43f5e80951267c`.
Tags `v2026.09.10`, `v2026.09.10.1`, `v2026.09.10.2`, `v2026.09.10.3` không đụng.

Reviewer: 3 cổng code/CI **PASS**. Phần còn lại: JUnit 401 anonymous + Notion.

| Gate | File | Test / evidence | Expected | Actual |
|---|---|---|---|---|
| Public JUnit | `scripts/pack_linux_evidence.py`, workflow `Publish JUnit on GitHub Release` | release asset `linux-junit-v2026.09.10.3.zip` | HTTPS 302, không 401 | 302 `releases/download/.../linux-junit-v2026.09.10.3.zip` |
| Tree identity | `scripts/verify_release_tree.py` | compare gzip/zip vs git blobs | 0 content_differences | script in-repo |
| Notion | `NOTION_GATE.md` | — | chỉ đọc target được chỉ định | `NOTION_TARGET_MISSING` (task không cấp ID) |

G1–G10 + public-transport coverage giữ. Không merge, không deploy, không ghi Notion.
