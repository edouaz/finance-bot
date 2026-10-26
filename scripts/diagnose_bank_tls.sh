#!/bin/sh
# Certificate diagnostics only: never enable HTTP/access/debug logging.
set -eu
[ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ] || {
    echo 'Usage: sudo ./scripts/diagnose_bank_tls.sh hostname' >&2; exit 1;
}
[ "$#" = 1 ] || exit 1
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
owner_home=$(getent passwd "$SUDO_USER" | cut -d: -f6)
[ -n "$owner_home" ] && [ "$(stat -c %U "$repo")" = "$SUDO_USER" ] || exit 1
# Refuse to replace a Caddy configuration changed independently since our installation.
cmp -s /etc/caddy/Caddyfile "$repo/data/web-deployment/Caddyfile" || {
    echo 'Configuration modifiée depuis la préparation : arrêt pour la préserver.' >&2; exit 1;
}
runuser -u "$SUDO_USER" -- env -i HOME="$owner_home" USER="$SUDO_USER" PATH=/usr/bin:/bin "$repo/.venv/bin/python" -B "$repo/scripts/prepare_bank_web.py" --hostname "$1"
caddy validate --config "$repo/data/web-deployment/Caddyfile" --adapter caddyfile
backup=/etc/caddy/Caddyfile.before-certificate-diagnostics
if [ ! -e "$backup" ]; then cp -p /etc/caddy/Caddyfile "$backup"; fi
install -o root -g root -m 0644 "$repo/data/web-deployment/Caddyfile" /etc/caddy/Caddyfile
started=$(date --iso-8601=seconds)
systemctl restart caddy.service
sleep 15
journalctl -u caddy.service --since "$started" --no-pager -o cat | "$repo/.venv/bin/python" -c '
import json, re, sys
for line in sys.stdin:
    try: entry = json.loads(line)
    except ValueError: continue
    logger = entry.get("logger", "")
    if not (logger == "tls.obtain" or logger.startswith("tls.issuance.acme")): continue
    result = {key: entry[key] for key in ("level", "logger", "msg", "error") if key in entry}
    for key, value in result.items():
        if isinstance(value, str): result[key] = re.sub(r"(https?://[^\s?]+)\?[^\s]+", r"\1?[redacted]", value)
    print(json.dumps(result, ensure_ascii=False))
'
