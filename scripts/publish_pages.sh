#!/bin/sh
# Publishes only the allowlisted static pages from an isolated fresh repository.
set -eu
command -v git >/dev/null || { echo 'Installez git et gh sur le VPS.' >&2; exit 1; }
command -v gh >/dev/null || { echo 'Installez gh sur le VPS puis lancez gh auth login.' >&2; exit 1; }
gh auth status >/dev/null
account=$(gh api user --jq .login)
if [ "$account" != 'edouaz' ]; then
  echo 'Le compte GitHub connecté doit être edouaz, conformément au callback enregistré.' >&2
  exit 1
fi
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
publish_dir=$(mktemp -d /tmp/finance-pages.XXXXXX)
chmod 700 "$publish_dir"
for file in index.html privacy.html terms.html callback.html callback.js style.css; do
  cp "$project_root/public/$file" "$publish_dir/$file"
done
cd "$publish_dir"
printf '%s\n' 'Static public site only. Banking code, credentials and financial data are not published.' > README.md
touch .nojekyll
git init -b main
git config user.name "$account"
git config user.email "$account@users.noreply.github.com"
git add index.html privacy.html terms.html callback.html callback.js style.css README.md .nojekyll
git commit -m 'Publish Personal Finance Tracker static pages'
# Refuse to modify any existing repository or its history.
existing=$(gh api "repos/$account/finance-bot" --jq .full_name 2>/dev/null || true)
if [ -n "$existing" ]; then
  echo 'Le dépôt existe déjà : arrêt avant modification. Son contenu et son historique doivent être audités.' >&2
  exit 1
fi
gh repo create "$account/finance-bot" --public --source . --remote origin --push
gh api --method POST "repos/$account/finance-bot/pages" -f 'source[branch]=main' -f 'source[path]=/'
printf 'Dépôt : https://github.com/%s/finance-bot\nSite : https://%s.github.io/finance-bot/\n' "$account" "$account"
echo 'La publication Pages peut prendre quelques minutes. Vérifiez callback.html avant toute nouvelle autorisation bancaire.'
