#!/bin/sh
# Prepare dependencies only. No service, tunnel or remote mutation.
set -eu
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.lock
./scripts/verify.sh
