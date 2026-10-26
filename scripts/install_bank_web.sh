#!/bin/sh
# Run explicitly with sudo; application imports and private config run as their owner.
set -eu
[ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ] || {
    echo 'Usage: sudo ./scripts/install_bank_web.sh hostname' >&2; exit 1;
}
[ "$#" = 1 ] || { echo 'Un nom DNS public est requis.' >&2; exit 1; }
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
owner_home=$(getent passwd "$SUDO_USER" | cut -d: -f6)
[ -n "$owner_home" ] && [ "$(stat -c %U "$repo")" = "$SUDO_USER" ] || exit 1
[ ! -e /etc/caddy/Caddyfile ] && [ ! -L /etc/caddy/Caddyfile ] || {
    echo 'Configuration Caddy existante : installation arrêtée pour la préserver.' >&2; exit 1;
}
if systemctl cat finance-bank-auth.service >/dev/null 2>&1 || [ -L /etc/systemd/system/finance-bank-auth.service ]; then
    echo 'Service existant : installation arrêtée pour le préserver.' >&2; exit 1;
fi
runuser -u "$SUDO_USER" -- env -i HOME="$owner_home" USER="$SUDO_USER" PATH=/usr/bin:/bin "$repo/.venv/bin/python" -B "$repo/scripts/prepare_bank_web.py" --hostname "$1"
if [ -n "$(ss -H -ltn '( sport = :80 or sport = :443 or sport = :8765 )')" ]; then
    echo 'Ports 80, 443 ou 8765 déjà occupés : aucun service existant ne sera remplacé.' >&2; exit 1;
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends caddy
install -o root -g root -m 0644 "$repo/data/web-deployment/Caddyfile" /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
runuser -u "$SUDO_USER" -- env -i HOME="$owner_home" USER="$SUDO_USER" PATH=/usr/bin:/bin "$repo/.venv/bin/python" -B "$repo/scripts/prepare_bank_web.py" --hostname "$1" --activate-config
install -o root -g root -m 0644 "$repo/data/web-deployment/finance-bank-auth.service" /etc/systemd/system/finance-bank-auth.service
systemctl daemon-reload
systemctl enable --now finance-bank-auth.service
systemctl enable caddy.service
systemctl restart caddy.service
if systemctl is-active --quiet finance-tunnel.service; then
    systemctl restart finance-tunnel.service
fi
printf '%s\n' 'Services démarrés ; certificat HTTPS et callback à vérifier avant utilisation.'
