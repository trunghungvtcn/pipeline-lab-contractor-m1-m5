#!/bin/sh
# Offline Linux acceptance for all five modules. No credentials.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"
python3 run_all.py
