# M5 Linux acceptance runbook

## Scope
Synthetic integration only. No THBISON VPS, no production Notion writes, no merge, no deploy.

## Dependency acquisition (may use network)
Build the image or install pytest + the five packages from this tree:

```sh
pip install pytest
```

## Offline test (no network, no credentials)

From the package root (parent of `m5_integration/`):

```sh
python3 run_all.py
```

or:

```sh
sh m5_integration/scripts/run_linux.sh
```

Compose (build may use network; the `accept` service has `network_mode: none`):

```sh
docker compose -f m5_integration/docker-compose.yml build
docker compose -f m5_integration/docker-compose.yml run --rm --no-deps accept
```

## Rollback
Delete the sandbox working directory. SQLite and CAS live under that directory; nothing is published.

## Verdict language
`CONTRACTOR_PASS` or `CONTRACTOR_PARTIAL`. Never `PRODUCTION_READY`.
`notion_real_read` and `linux_docker` stay `NOT_VERIFIED` unless those gates actually ran.
