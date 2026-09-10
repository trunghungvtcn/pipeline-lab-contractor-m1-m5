# Linux offline acceptance

Execution host: Linux, Python 3.12. Windows host is not supported.

## 1. Acquire wheels (network allowed)

Wheels already live in `vendor/wheels` with hashes in `requirements.lock`.
To refresh:

```sh
pip download pytest==9.1.1 -d vendor/wheels --only-binary=:all:
```

## 2. Runtime tests (network disabled)

```sh
docker compose -f m5_integration/docker-compose.yml build
docker compose -f m5_integration/docker-compose.yml run --rm --no-deps accept
```

`network_mode: none` on the test container. Env is an allowlist without credentials.

Without Docker, from a Linux Python 3.12 venv:

```sh
pip install --require-hashes --find-links vendor/wheels -r requirements.lock
python3 run_all.py
```

Expected: 0 failed, 0 skipped, 0 deselected, unhandled-thread and ResourceWarning are errors.
