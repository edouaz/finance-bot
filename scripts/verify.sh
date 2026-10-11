#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q finance finance_mcp_v2.py
.venv/bin/python -m pip check
