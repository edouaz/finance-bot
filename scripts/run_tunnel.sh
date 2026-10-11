#!/bin/sh
set -eu
cd /home/edouard/finance-bot
exec /home/edouard/finance-bot/.venv/bin/python -m finance.tunnel_runtime "$@"
