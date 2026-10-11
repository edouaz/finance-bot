# Mise à jour du tunnel existant — 2026-10-11

Le tunnel et le plugin existants restent inchangés. `finance_mcp.py` est maintenant un lanceur v2 ; il charge uniquement les variables financières autorisées depuis le fichier externe 0600. L'ancien serveur est conservé dans `finance_mcp_legacy.py`.

Le profil finance-bot continue de lancer exactement le même chemin. Test stdio effectué via ce chemin : initialisation, découverte des 15 outils et appels réussis. Un processus déjà lancé doit être redémarré pour recharger Python. Aucun tunnel actif n'a été identifié dans l'espace de processus accessible ici ; aucune relance n'a été effectuée.

Depuis le terminal où le tunnel fonctionnait, arrêter proprement le processus courant puis :

```sh
/home/edouard/finance-bot/scripts/run_tunnel.sh
```

Le script réutilise CONTROL_PLANE_API_KEY déjà exportée ; il ne crée pas de tunnel, ne change pas de profil et ne renouvelle pas de clé. Si cette variable manque, retrouver le mécanisme de chargement habituel. C'est l'authentification du tunnel OpenAI, indépendante du consentement bancaire. Ne pas coller de clé dans ChatGPT. Pour revenir à la v1, conserver le même profil et restaurer son serveur depuis finance_mcp_legacy.py après sauvegarde du lanceur.

Source officielle : https://developers.openai.com/api/docs/guides/secure-mcp-tunnels

## Rapport à 06:00

Le minuteur est maintenant configuré lundi 06:00 Europe/Brussels. Le calendrier systemd a été validé. Le mot de passe sudo n'est pas disponible ici ; les unités ne sont pas installées. Le mode user fonctionnerait seulement avec une session utilisateur persistante (Linger=no actuellement), donc le service système reste le choix documenté :

```sh
sudo install -m 644 /home/edouard/finance-bot/deploy/finance-weekly.service /etc/systemd/system/finance-weekly.service
sudo install -m 644 /home/edouard/finance-bot/deploy/finance-weekly.timer /etc/systemd/system/finance-weekly.timer
sudo systemctl daemon-reload
sudo systemctl enable --now finance-weekly.timer
systemctl list-timers finance-weekly.timer --no-pager
```

Le rapport est chiffré localement, sans envoi. La création d'un rapport à 06:00 n'est pas une notification ChatGPT à 06:00 ; un canal de livraison doit être choisi séparément.

## GitHub Pages

Aucun dépôt n'a été créé par l'agent. Aucun compte GitHub n'est authentifié ici ; ni git ni gh ne sont installés. Le plugin GitHub est disponible mais sa connexion n'est pas confirmée. Les 404 publics ne prouvent pas qu'un dépôt privé n'existe pas.

Alternative à la connexion GitHub dans l'app, depuis le VPS :

```sh
sudo apt-get update
sudo apt-get install -y git gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
/home/edouard/finance-bot/scripts/publish_pages.sh
```

Ce script vérifie le compte edouaz, construit un nouveau dépôt temporaire avec une liste explicite de six fichiers statiques, README et .nojekyll, crée le dépôt public edouaz/finance-bot et active Pages sur main. Il refuse de modifier un dépôt déjà existant : son contenu/historique doit être audité. Il ne copie ni code bancaire, ni clés, ni sessions, ni données ; ne jamais exécuter git add . dans le dossier bancaire pour publier le site.

Adresses attendues APRES réussite (pas des liens de publication confirmés) :
- https://github.com/edouaz/finance-bot
- https://edouaz.github.io/finance-bot/
- https://edouaz.github.io/finance-bot/callback.html

Vérifier les liens après le build Pages ; le callback enregistré reste inchangé. Si le compte désiré n'est pas edouaz, préparer une migration de redirection avant de changer l'adresse publique.

Références CLI/API : https://cli.github.com/manual/gh_repo_create et https://docs.github.com/en/rest/pages/pages#create-a-github-pages-site . Authentification GitHub effectuée dans le navigateur, pas dans le chat.
