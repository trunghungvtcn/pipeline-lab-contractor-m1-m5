# Pipeline Lab contractor M1–M5

Candidate `v2026.09.10.4` — public JUnit on GitHub Release + `NOTION_TARGET_MISSING`.

Independent re-review of `v2026.09.10.3` passed the three code/CI gates. Remaining partial is Notion (no target ID in this task) plus previously-401 Actions artifacts. JUnit for `.3` is now a public release asset.

Không đụng tag `v2026.09.10` … `v2026.09.10.3`.

## Tải

- Release: https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/tag/v2026.09.10.4
- JUnit `.3` (anonymous): https://github.com/trunghungvtcn/pipeline-lab-contractor-m1-m5/releases/download/v2026.09.10.3/linux-junit-v2026.09.10.3.zip
- Checksum: file `*.sha256` cạnh asset

```sh
python3 -m pip install --no-index --require-hashes --find-links vendor/wheels -r requirements.lock
python3 run_all.py
```
