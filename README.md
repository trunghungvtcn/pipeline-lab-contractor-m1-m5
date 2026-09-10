# Pipeline Lab contractor M1–M5

Gói audit synthetic sau sửa G1–G12 (2026-09-10.1). Không phải production, không merge Knowledge Factory.

Tag cũ `v2026.09.10` giữ nguyên.

## Tải xuống

- gzip: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/download/v2026.09.10.1/pipeline-lab-contractor-m1-m5.tar.gz
- zip: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/download/v2026.09.10.1/pipeline-lab-contractor-m1-m5.zip
- release: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/tag/v2026.09.10.1
- branch: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/tree/fix/g1-g12-20260910

SHA-256 gzip: `120f056acda3f78b443c191d31fad753e282617378e96f456ae583db9c9d6c7a`  
SHA-256 zip: `8a6f1017f279464f8954bb1c016cf9d9a2e214898274d1bd61cf5e1141db4663`  
Commit: `5ddb949da986130c59625469b4403e6344dfa353`

## Chạy test

```sh
python3 -m pip install --require-hashes --find-links vendor/wheels -r requirements.lock
python3 run_all.py
```

Kỳ vọng: 95 passed, 0 failed, 0 skipped. Overall `CONTRACTOR_PARTIAL` cho đến khi Linux Docker và Notion target được cấp.
