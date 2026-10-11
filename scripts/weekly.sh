#!/bin/sh
set -eu
cd /home/edouard/finance-bot
# Failed sync exits nonzero; generate report anyway so missing data is explicitly recorded.
end=$(.venv/bin/python -c 'from datetime import datetime,timedelta; from zoneinfo import ZoneInfo; print((datetime.now(ZoneInfo("Europe/Brussels")).date()-timedelta(days=1)).isoformat())')
start=$(.venv/bin/python -c 'from datetime import date,timedelta; import sys; print((date.fromisoformat(sys.argv[1])-timedelta(days=365)).isoformat())' "$end")
.venv/bin/python -m finance.cli sync --start "$start" --end "$end" || true
exec .venv/bin/python -m finance.cli weekly-report --output /home/edouard/.local/share/finance-tracker/weekly-report.fernet
