#!/bin/sh
set -eu
if [ -z "${CONTROL_PLANE_API_KEY:-}" ]; then
  echo 'La variable CONTROL_PLANE_API_KEY doit être présente dans ce terminal. Réutilisez votre environnement habituel du tunnel ; ne partagez pas la clé dans un chat.' >&2
  exit 1
fi
exec /home/edouard/.local/bin/tunnel-client run --profile finance-bot
