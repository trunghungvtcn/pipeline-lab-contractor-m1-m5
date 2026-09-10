# Pipeline Lab contractor M1–M5

Gói audit synthetic sau sửa F01–F14 (2026-09-10). Không phải production, không merge Knowledge Factory.

## Tải xuống

- gzip: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/download/v2026.09.10/pipeline-lab-contractor-m1-m5.tar.gz
- zip: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/download/v2026.09.10/pipeline-lab-contractor-m1-m5.zip
- trang release: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/tag/v2026.09.10

SHA-256 gzip: `23283b38b56419dcc28c5b1e95b18929c2827a45c8f47e152b83ea86de3aff01`  
SHA-256 zip: `4241b57a50b77dc8f9d691207d04f55ca276a1fb4b607919a845f4b2b6ee46c7`

## Chạy test

```sh
python3 -m pip install pytest
python3 run_all.py
```

Kỳ vọng 78/78, verdict `CONTRACTOR_PASS`. Notion thật và Docker host: `NOT_VERIFIED`.
