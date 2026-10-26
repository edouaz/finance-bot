# Réautorisation bancaire privée

Le MCP reste en stdio ; `get_reauthorization_link` retourne le lien privé sans démarrer de consentement. Le processus optionnel `bank_auth_web.py`
sert deux boutons, « Réautoriser BNP Paribas Fortis » et « Réautoriser Revolut ».
Il réutilise `Settings`, le JWT RSA de `Client` et les fichiers privés
`FINANCE_SESSIONS/{bnp,revolut}_session.json`. Aucun paiement, virement, révocation
ou droit d’écriture bancaire n’est ajouté. La base de transactions n’est jamais ouverte
par le flux de réautorisation.

## Flux et garanties

- Toutes les routes exigent HTTPS, l’hôte configuré et une authentification HTTP Basic
  (utilisateur `finance`, mot de passe aléatoire dans un fichier 0600).
- `GET /` crée un cookie `__Host-finance-auth` Secure, HttpOnly, SameSite=Lax.
  `POST /authorize/bnp` ou `/authorize/revolut` exige aussi l’Origin exacte et le
  jeton CSRF du formulaire. Aucun lancement par GET.
- `POST /auth` demande uniquement les informations de comptes, soldes et transactions,
  avec la durée maximale annoncée pour cette banque par `GET /aspsps`
  (`maximum_consent_validity`, en secondes). Aucun plafond local de dix jours n’est
  ajouté. Si cette limite est absente ou invalide, le lancement est refusé.
  L’URL renvoyée doit être HTTPS sur
  `auth.enablebanking.com` ou `tilisy.enablebanking.com` (migration fournisseur). Le callback doit être enregistré auprès d’Enable Banking.
- Les empreintes SHA-256 du state aléatoire et du cookie, la banque et l’heure sont
  conservées dans `FINANCE_SESSIONS/authorization.sqlite3` (0600, dossier 0700).
  Le state expire après 30 minutes et survit à un redémarrage du serveur. Les anciennes
  entrées expirées sont nettoyées au lancement d’une nouvelle autorisation.
- `GET /callback` exige le même navigateur et rejette paramètres dupliqués et state
  inconnu/expiré. SQLite consomme atomiquement le state **avant** tout échange,
  même si le fournisseur refuse ou si l’échange échoue. Deux callbacks concurrents
  ne peuvent pas échanger le même code. Un mauvais cookie ne consomme pas le state.
- Le code est échangé une seule fois avec `POST /sessions`, sans nouvelle tentative
  automatique. `GET /sessions/{id}` vérifie AUTHORIZED, une expiration UTC future
  et la banque attendue avant le remplacement atomique du fichier local (0600).
  Les métadonnées renvoyées une seule fois par POST sont conservées. Tout échec
  de vérification ou d’écriture laisse le précédent fichier intact.
- Le callback redirige immédiatement vers une URL sans code. Les réponses portent
  no-store, no-referrer et une CSP sans ressources externes ; les erreurs affichées
  sont fixes. Aucun corps fournisseur, code, state, cookie ou mot de passe n’est journalisé
  par ce code. Le lanceur Uvicorn désactive les access logs et les traces ordinaires.

Référence du protocole : [API Enable Banking](https://enablebanking.com/docs/api/reference/).

## Installation légère sur un VPS sans domaine acheté

Un nom DNS public fourni avec le VPS peut suffire : il doit pointer sur ce serveur
et permettre les validations HTTPS sur les ports 80/443. Aucun tunnel temporaire,
conteneur Docker ou service payant supplémentaire n’est nécessaire. Le contrôle
DNS doit porter sur les enregistrements publics A/AAAA et CAA, pas seulement /etc/hosts.
L’émission du certificat par l’autorité publique reste à vérifier au déploiement.

Le script fourni prend explicitement le nom choisi et réutilise la configuration
privée existante du propriétaire du dépôt :

```sh
cd /chemin/vers/finance-bot
sudo ./scripts/install_bank_web.sh nom-public-du-vps.example
```

Il prépare les fichiers sous `data/web-deployment/`, installe le paquet Debian Caddy,
valide sa configuration, génère un mot de passe web local si nécessaire, sauvegarde
le fichier d’environnement privé avant sa mise à jour atomique, puis démarre
`finance-bank-auth.service` et Caddy. Si `finance-tunnel.service` est déjà actif,
il le redémarre pour charger le nouvel outil MCP. Aucun second tunnel n’est créé.
Il refuse d’écraser une configuration Caddy ou une unité de réautorisation existante,
et refuse des ports 80/443/8765 déjà occupés avant l’installation.

Un seul processus Python utilise le venv existant. Le proxy gère et renouvelle les
certificats. Les processus restent disponibles, avec une faible activité au repos ;
il n’y a pas de minuterie qui pourrait interrompre un callback bancaire. Mesurer
la mémoire après le démarrage avec `systemctl show ... -p MemoryCurrent`, sans
promettre une consommation non mesurée. Node n’est utilisé que pour les tests du site.

Le proxy écoute en HTTPS public ; Python écoute exclusivement sur 127.0.0.1:8765.
Les journaux de requêtes et les erreurs HTTP Caddy pouvant contenir un callback sont désactivés. Seuls `tls.obtain` et `tls.issuance.acme` peuvent produire des diagnostics de certificat, jamais les requêtes bancaires.
Le service Python a `NoNewPrivileges`, un umask 0077, un système/home en lecture seule
et un droit d’écriture limité au dossier des sessions. Ce choix masque aussi les
traces d’erreur : diagnostiquer avec des codes fixes, jamais des callbacks complets.

À faire une seule fois par le propriétaire :

1. Ajouter `https://nom-public-du-vps.example/callback` aux redirections autorisées
   de son application Enable Banking, en conservant l’ancien callback de secours.
2. Exécuter la commande sudo ci-dessus dans son terminal privé.
3. Récupérer le mot de passe dans `~/.config/finance-tracker/web-password` uniquement
   dans son terminal privé/gestionnaire de mots de passe, puis le mémoriser pour
   l’adresse HTTPS du serveur, utilisateur `finance`. Ne pas le coller dans un chat.
4. Demander « reconnecter Revolut » dans ChatGPT : `get_reauthorization_link`
   fournit `https://nom-public-du-vps.example/?bank=revolut`. Le navigateur exige
   l’authentification privée et un clic explicite avant tout lancement bancaire.
5. Valider le consentement dans le même navigateur. Le callback termine la session
   automatiquement : aucun code ou URL bancaire à renvoyer à ChatGPT.

Le serveur conserve les sessions et l’historique en place. Une migration de callback
ne prolonge pas une session déjà créée pour dix jours ; terminer les flux CLI en
cours avant la bascule. Le lancement CLI peut garder l’ancien callback en exportant
explicitement `FINANCE_AUTH_REDIRECT_URL=https://edouaz.github.io/finance-bot/callback.html`
pour cette commande seulement si cet ancien callback reste enregistré.

L’interface initiale demeure volontairement simple. Un autre utilisateur remplace
le nom public, utilise sa propre application Enable Banking et sa propre configuration.
Ni les identifiants du propriétaire de la page ni son serveur ne sont mutualisés.

## Procédure manuelle de mise en service (alternative)

1. Sauvegarder de manière privée les sessions et la configuration existantes.
   Conserver la clé de chiffrement et le cache historique inchangés. Installer les
   dépendances verrouillées si nécessaire (`scripts/install.sh`) ; Starlette et
   Uvicorn sont déjà présents dans `requirements.lock`, aucune dépendance ajoutée.
2. Dans le fichier d’environnement privé existant
   `~/.config/finance-tracker/environment` (0600), conserver les valeurs actuelles de
   `ENABLE_BANKING_APP_ID`, `ENABLE_BANKING_KEY`, `FINANCE_SESSIONS`, `FINANCE_STORAGE`
   et `FINANCE_DATA_KEY`. Ajouter :

   ```dotenv
   FINANCE_AUTH_REDIRECT_URL=https://votre-hote-prive.example/callback
   FINANCE_AUTH_PASSWORD_FILE=/home/edouard/.config/finance-tracker/web-password
   ```

   Le chemin du callback web doit être exactement `/callback`. Aucun `.env` du dépôt
   n’est chargé automatiquement. Le dossier FINANCE_SESSIONS doit appartenir à
   l’opérateur et avoir le mode 0700 ; les sessions restent 0600.
3. Générer localement un mot de passe sans l’imprimer ni le placer dans une commande :

   ```sh
   .venv/bin/python - <<'PY'
   import os, secrets
   from pathlib import Path
   p = Path.home()/'.config/finance-tracker/web-password'
   fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
   with os.fdopen(fd, 'w') as f:
       f.write(secrets.token_urlsafe(48) + '\n')
   PY
   ```

   Le récupérer uniquement dans un gestionnaire de mots de passe ou terminal privé.
   Ne pas le transmettre au chat. HTTP Basic sur TLS convient à cette interface
   personnelle ; limiter aussi l’accès réseau (VPN ou restriction au proxy).
4. Préparer un reverse proxy TLS sur **la même machine**, vers `127.0.0.1:8765`.
   Transmettre l’hôte public exact et remplacer `X-Forwarded-Proto` par `https`.
   Ne pas accepter cette valeur fournie par le client. Le lanceur ne fait confiance
   qu’aux connexions locales pour cet en-tête. Bloquer tout accès externe au port 8765.
   Exemple de bloc Nginx dans un serveur TLS privé existant :

   ```nginx
   # Serveur dédié : ne pas hériter de journaux contenant les query strings.
   access_log off;
   error_log /dev/null crit;
   location / {
       proxy_pass http://127.0.0.1:8765;
       proxy_set_header Host votre-hote-prive.example;
       proxy_set_header X-Forwarded-Proto https;
       proxy_set_header Authorization $http_authorization;
       proxy_cache off;
   }
   ```

   Désactiver aussi la capture des URLs complètes, query strings, en-têtes et corps
   dans les éventuels CDN/WAF/APM/diagnostics en amont. Ne pas placer le callback sur
   GitHub Pages. Les journaux de l’hébergeur échappent au contrôle de Python.
5. Après autorisation explicite, enregistrer le nouveau redirect HTTPS exact dans
   l’application Enable Banking. Garder l’ancien callback CLI comme solution de
   repli si le fournisseur permet plusieurs URLs. Aucune inscription effectuée ici.
6. Exécuter les tests hors réseau bancaire :

   ```sh
   .venv/bin/python -m unittest discover -s tests -v
   ```

   Puis, seulement une fois les étapes précédentes validées et l’activation autorisée :

   ```sh
   .venv/bin/python bank_auth_web.py
   ```

   Aucun service systemd ni tunnel n’est créé ou activé automatiquement. Ne pas lancer
   `uvicorn --reload`, de logs debug, d’access logs ou d’APM capturant les callbacks.
7. Ouvrir l’URL HTTPS privée, se connecter avec `finance`, cliquer sur une banque,
   consentir puis revenir dans le **même navigateur**. La page confirme uniquement
   une session vérifiée. Refaire pour l’autre banque. Contrôler ensuite le statut
   et une synchronisation limitée via les outils existants ; la réautorisation
   seule ne télécharge pas de transactions. Vérifier la continuité de l’historique.

## Échec et retour arrière

Si une autorisation échoue, relancer depuis le bouton : un state consommé n’est jamais
réutilisable, y compris après un timeout. En cas de session créée chez le fournisseur
mais non vérifiable/non sauvegardable, l’ancienne session locale reste en place ; aucune
révocation automatique n’est tentée. Fermer la page et arrêter le processus web suffit
pour désactiver l’interface. Ne pas restaurer/supprimer le cache SQLite des transactions.

La CLI partage désormais le même flux et respecte les variables de configuration :

```sh
.venv/bin/python bank_auth.py start bnp
.venv/bin/python bank_auth.py finish bnp
# Même chose avec revolut.
```

Le callback CLI par défaut reste l’ancien
`https://edouaz.github.io/finance-bot/callback.html` en l’absence de configuration.
Pour l’utiliser en repli, retirer temporairement FINANCE_AUTH_REDIRECT_URL ou lui donner
cette URL déjà enregistrée. Les anciens `*_pending.json` ne sont plus lus : recommencer
les flux en attente. Ne jamais coller l’URL de retour dans un chat ; finish la demande
avec saisie masquée et valide son schéma/hôte/chemin. Le mode CLI n’est pas lié au navigateur.

## Diagnostic CLI

Les erreurs CLI affichent uniquement des messages fixes et, en cas de refus fournisseur,
le statut HTTP. Elles n’affichent jamais le corps de réponse, le code bancaire ou le state.
Une erreur « URL d’autorisation non autorisée » signifie que le contrôle du lien
a refusé son origine ; les deux origines officielles `auth.enablebanking.com` et
`tilisy.enablebanking.com` sont acceptées, sans autoriser les autres sous-domaines.
La [migration de domaine Enable Banking](https://enablebanking.com/blog/2026/06/12/enable-banking-changelog-may-2026)
explique la coexistence de ces origines.

## Moins de renouvellements et rappels dans ChatGPT

Le lancement CLI et web lit la limite de la banque avant chaque consentement.
Le contrôle en lecture seule du 25 octobre 2026 a annoncé **180 jours** pour BNP
Paribas Fortis et Revolut en Belgique. La limite n’est pas codée en dur : une valeur
plus courte ou plus longue sera respectée lors du prochain lancement. La banque
peut imposer un renouvellement anticipé. La date effective retournée après le
consentement reste la référence.

Les sessions créées auparavant pour dix jours ne sont pas prolongées automatiquement.
Pour obtenir la nouvelle durée, refaire le consentement de la banque concernée ;
les transactions historiques restent dans leur stockage actuel. Les liens déjà
créés avant la modification conservent la durée demandée au moment de leur création.
Il n’y a pas besoin de renouveler les clés applicatives à chaque consentement.

Au prochain chargement du serveur MCP, les réponses des outils peuvent inclure
`connection_notices`. Un rappel est dû quand l’échéance locale est à sept jours ou
moins, ou déjà dépassée. Il est joint au prochain appel d’outil, puis au maximum
une fois toutes les 24 heures par banque, session et état (bientôt expiré/expiré).
Le passage à l’état expiré peut donc déclencher un nouveau rappel immédiatement.
Le résultat indique `live_verified: false` : il s’agit de métadonnées locales,
pas d’une interrogation bancaire en direct.

Les instructions d’initialisation MCP demandent à ChatGPT de présenter brièvement
les rappels reçus. Le client garde le contrôle de leur affichage. Aucun appel modèle,
cron, e-mail, tâche planifiée ou notification hors conversation n’est ajouté.
Le délai anti-répétition est en mémoire : un redémarrage du processus peut répéter
un rappel. `get_connection_status` reste consultable à chaque appel, même si le
rappel est temporairement masqué. Un échec de lecture du rappel ne bloque pas
l’accès aux données financières en cache.

## Une page publique commune, un serveur privé par utilisateur

`public/connection.html` est le point d’entrée statique prévu pour GitHub Pages.
Une personne saisit l’origine HTTPS de **son propre serveur**, vérifie la destination,
puis clique sur « Mémoriser et ouvrir mon serveur privé ». L’origine sans secret est
mémorisée dans le `localStorage` de ce navigateur ; rien n’est mémorisé côté serveur
GitHub par ce code. Le bouton « Oublier cette adresse » supprime cette préférence.
Le stockage bloqué n’empêche pas la navigation manuelle confirmée.

La page ne réalise aucun appel API au VPS et ne reçoit aucun résultat bancaire.
Elle ouvre seulement la racine de l’interface privée déjà configurée ; le propriétaire
s’y authentifie et clique sur sa banque. Le callback reste sur ce serveur privé,
sans transit du code par GitHub Pages. Aucune configuration CORS publique n’est nécessaire.

La même page statique peut servir à tous. Chaque utilisateur garde sa propre
application Enable Banking, sa clé RSA, son consentement bancaire, ses sessions,
son stockage chiffré et son authentification web. Il utilise son VPS et ses services
existants ou ceux qu’il choisit de provisionner. Cette architecture n’ajoute aucun
hébergement bancaire mutualisé ni facturation à la charge du propriétaire de la page.
Les frais éventuels de leurs fournisseurs restent à vérifier par chaque utilisateur.

Le premier paramétrage HTTPS/Enable Banking/VPS reste nécessaire (procédure ci-dessus).
La page ne peut ni créer un serveur ni configurer des secrets pour un tiers. Ensuite,
le renouvellement se fait dans le navigateur sans terminal. La publication de la page statique et l’activation du serveur privé sont deux étapes
distinctes : publier la page ne démarre pas le service bancaire. Le script
`scripts/publish_pages.sh` inclut les nouveaux fichiers dans sa liste autorisée mais
continue à refuser la modification d’un dépôt existant ; aucune publication lancée.

Vérification de la page statique : `node tests/test_connection.js` (Node uniquement
pour le test, aucune dépendance frontend à installer). La navigation réelle et le
retour bancaire devront être validés après la mise en service HTTPS autorisée.

Quand `FINANCE_AUTH_REDIRECT_URL` désigne le callback privé `/callback`, la commande
CLI `start` fournit elle aussi le lien vers l’interface privée, sans créer de state
CLI ni appeler Enable Banking. Le consentement démarre dans le navigateur afin de
lier correctement le cookie au state ; le retour est automatique, sans `finish`.
Le parcours CLI start/finish demeure réservé au callback statique de secours
(`callback.html`), qui doit toujours être enregistré si l’on souhaite le conserver.

## Certificat HTTPS pas encore disponible

Si les services sont actifs mais la négociation TLS échoue, ne pas lancer de
consentement bancaire et ne pas contourner la vérification du certificat.
`scripts/diagnose_bank_tls.sh nom-public-du-vps.example`, exécuté avec sudo,
active uniquement les diagnostics d’obtention de certificat (`tls.obtain` et
`tls.issuance.acme`) en conservant tous les journaux HTTP masqués. Il valide la
configuration, garde une sauvegarde, redémarre seulement Caddy et affiche après
15 secondes les seuls événements d’émission, en masquant les paramètres d’URL.
Il refuse de remplacer une configuration modifiée indépendamment depuis la préparation.
Ne pas activer les logs globaux debug ou les journaux d’accès pour ce diagnostic.

## Parcours manuel immédiat : Revolut avec le callback GitHub

Si HTTPS du VPS est reporté, réenregistrer d’abord exactement
`https://edouaz.github.io/finance-bot/callback.html` dans Enable Banking.
Les commandes ci-dessous remplacent le callback pour cette commande seulement,
sans modifier l’environnement privé installé ni les sessions existantes :

```sh
env FINANCE_AUTH_REDIRECT_URL=https://edouaz.github.io/finance-bot/callback.html /home/edouard/finance-bot/.venv/bin/python /home/edouard/finance-bot/bank_auth.py start revolut
```

Ouvrir le lien, valider Revolut, puis copier l’URL du champ « Callback URL » sur
la page GitHub : les paramètres ont déjà été retirés de la barre d’adresse.
La commande finish imprimée par start conserve maintenant explicitement le même
callback et le même interpréteur. La lancer et coller l’URL dans sa saisie masquée,
au plus tard 30 minutes après start. Ne jamais coller ce retour dans un chat.
Le site statique peut être journalisé par son hébergeur ; il demeure un repli manuel.
