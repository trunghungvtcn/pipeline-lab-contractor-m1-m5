# Gates after independent re-review of v2026.09.10.1

Baseline kept: `v2026.09.10.1` / `5ddb949da986130c59625469b4403e6344dfa353`. Tag cũ `v2026.09.10` không đụng.

| Gate | File | Test IDs | Expected | Actual |
|---|---|---|---|---|
| 1 Public transport | `m5_integration/src/grok_pipeline/transport.py`, `harness.py` `_next_revision`/`_refresh_revision` | `test_public_wrapper_has_no_fake_internals`, `test_two_sequential_jobs_through_public_transport`, `test_replay_idempotent_through_public_transport`, `test_projection_timeout_retry_through_public_transport`, `test_restart_through_public_transport`, `test_concurrent_jobs_through_public_transport` | Wrapper không có `.pages`; hai job/replay/retry/restart/concurrent qua `call()` | AttributeError trên `.pages`; jobs `ok` |
| 2 Docker fail-fast | `m5_integration/Dockerfile` | image build | `FROM python:3.12.10-slim-bookworm@sha256:97983fa8cc88343512862c62307159a82261c3528dc025f79e5a3f7af43e50b4`; không `pip --offline`; không `cmd \|\| fallback` | một `pip install --no-index --require-hashes` + `--no-build-isolation --no-deps` |
| 3 Linux evidence | `.github/workflows/linux-offline.yml` | M1 symlink/hash/regular-file + full suite | GH Actions Ubuntu + docker `--network=none` | xem URL run trên tag mới |

G1–G10 coverage giữ nguyên (không xfail/skip).
