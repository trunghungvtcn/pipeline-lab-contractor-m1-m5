# Pipeline Lab contractor M1–M5

Candidate `v2026.09.10.2` — public transport boundary + pinned Docker digest + GitHub Actions Linux receipt.

Không đụng tag `v2026.09.10` hay `v2026.09.10.1`.

## Tải

- Release: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/tag/v2026.09.10.2
- Checksum: file `*.sha256` cạnh asset trên GitHub Release

```sh
python3 -m pip install --no-index --require-hashes --find-links vendor/wheels -r requirements.lock
python3 run_all.py
```
