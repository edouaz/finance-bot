#!/bin/sh
# Operator-only: sudo asks for authentication in the terminal.
set -eu
cd /home/edouard/finance-bot
.venv/bin/python -c 'from finance.tunnel_runtime import credential_reference; credential_reference()'
sudo install -m 644 deploy/finance-tunnel.service /etc/systemd/system/finance-tunnel.service
sudo systemctl daemon-reload
sudo systemctl enable --now finance-tunnel.service
systemctl is-active finance-tunnel.service
