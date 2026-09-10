# Linux offline acceptance

Base image (linux/amd64):

`python:3.12.10-slim-bookworm@sha256:97983fa8cc88343512862c62307159a82261c3528dc025f79e5a3f7af43e50b4`

## Acquire (network allowed)

Wheels live in `vendor/wheels` with hashes in `requirements.lock`.

## Build and test (test step has no network)

```sh
docker build -f m5_integration/Dockerfile -t contractor-accept:candidate .
docker run --rm --network=none --env PYTHONDONTWRITEBYTECODE=1 --env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 contractor-accept:candidate
```

Or GitHub Actions workflow `.github/workflows/linux-offline.yml`.

Without Docker, Linux Python 3.12:

```sh
python3 -m pip install --no-index --require-hashes --find-links vendor/wheels -r requirements.lock
python3 run_all.py
```
