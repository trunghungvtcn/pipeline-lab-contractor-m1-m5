# G1–G12 — file sửa, test, expected/actual

Tag cũ (không đụng): `v2026.09.10` → `e618646f7cd42d42e7b55aa9cb6e333d524c188b`

| ID | File | Test | Expected | Actual (sau sửa) | Evidence |
|---|---|---|---|---|---|
| G1 | `m2_asset_store/src/grok_asset_store/store.py` `_exclusive_stage` | `test_g1_untrusted_stage_id_stays_in_job_root` | write dưới `job_root`; id_gen traversal không thành path | first_write trong `.stage-<sha256>/` | N01 outside=false |
| G2 | `store.py` `verify_manifest` + `_read_bytes` | `test_g2_provenance_locator_and_size_bound` | locator/size lệch → verify False; không ResourceWarning | verified=false | N02 |
| G3 | `m3_job_ledger/src/grok_job_ledger/ledger.py` `_migrate`/`_configure`/`close` | `test_g3_two_processes_one_job` | 8 process, 1 job_id, 0 exception | 1 id, OK/IDEMPOTENT_HIT | pytest M3 |
| G4 | `ledger.py` `record_attempt` | `test_g4_unknown_retry_class_is_rejected` | `INVALID_RETRY_CLASS`, state RUNNING | reason=INVALID_RETRY_CLASS | N03 |
| G5 | `ledger.py` `reserve_budget` | `test_g5_reservation_conflict_across_jobs` | `RESERVATION_CONFLICT`, job2 reserved=0 | RESERVATION_CONFLICT / 0 | N04 |
| G6 | `ledger.py` `admit`/`claim` | `test_g6_deadline_and_not_before` | persist + enforce; deadline sau dispatch → RECONCILE_REQUIRED | cột bền sau reopen | pytest |
| G7 | `snapshot.py` `acquire_snapshot` | `test_g7_missing_attachment_not_consistent` | MISSING → NOT_VERIFIED | custody=NOT_VERIFIED | N05 |
| G8 | `snapshot.py` flags/knowledge_content_read | cùng test G7 | mode input; knowledge_content_read=true sau retrieve | True + SYNTHETIC_TEST | N06 |
| G9 | `harness.py` `_next_revision` | `test_g9_two_jobs_do_not_share_revision` | hai job ok, 2 event | ok/ok | N07 |
| G10 | `harness.py` artifact_bytes + crash_at | `test_g10_crash_after_result_resumes_without_recompute` | resume cùng digest, compute=0 | ok, compute_calls=0 | pytest |
| G11 | `resolver.py` fstat regular-file trước open | `test_rejects_directory` `test_rejects_fifo_when_available` | reject dir/FIFO; Linux host | LOCATOR_REJECTED | SUPPORT.md |
| G12 | `pyproject.toml` `requirements.lock` `Dockerfile` `run_all.py` | run_all + lock hashes | Python 3.12, warning=error, wheels hashed | lock 8 wheels | vendor/wheels |

Regression cũ giữ: NaN JSON, M4 read-only `projection.apply`, mapping allowlist, M3 finalize CAS, M5 source identity.

Verdict gói này: **CONTRACTOR_PARTIAL** — synthetic modules xanh trên Linux sandbox; `linux_docker` và `notion_real_read` vẫn NOT_VERIFIED (không có target Notion, Docker digest chưa attest trên host reviewer).
