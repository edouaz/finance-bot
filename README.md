# Finance Tracker

**Vos finances, l’esprit plus clair.** Un serveur MCP Python auto-hébergé pour consulter vos comptes et comprendre vos dépenses avec un client compatible MCP, dont ChatGPT via un tunnel configuré séparément.

[Découvrir le projet](https://edouaz.github.io/finance-bot/) · [Outils MCP](docs/MCP_TOOLS.md) · [Architecture](docs/ARCHITECTURE.md) · [Sécurité](docs/SECURITY.md)

- **Lecture seule** : aucun paiement ni virement depuis les outils MCP.
- **Historique local** : données financières dans une base SQLite chiffrée, avec une clé distincte hors du dépôt.
- **Analyses expliquées** : dépenses, catégories, récurrences et alertes, avec leurs limites de couverture.
- **Deux banques prévues** : BNP Paribas Fortis Belgique et Revolut Belgique via Enable Banking. Leur disponibilité dépend de votre accès fournisseur.

Ce dépôt est un projet personnel, pas un service bancaire prêt à l’emploi. Chaque personne doit créer sa propre application Enable Banking et autoriser ses propres comptes. Le site public est une présentation statique, sans connexion bancaire ; son aperçu utilise des données fictives.

## Avant de commencer

Il vous faut :

- Un ordinateur ou VPS avec Python **3.10 ou plus récent**, Git et la possibilité de créer un environnement virtuel. Les exemples ci-dessous utilisent un shell Linux/macOS ; le déploiement systemd nécessite Linux.
- Une application Enable Banking avec un identifiant, une clé privée RSA associée et une URL de redirection enregistrée. Vérifiez auprès du fournisseur les conditions d’accès et les banques disponibles avant d’utiliser des comptes réels.
- Un client MCP pour la consultation. Le tunnel vers ChatGPT nécessite sa propre configuration et ses propres autorisations ; installer ce dépôt ne crée pas automatiquement de connecteur ChatGPT.

Vous pouvez tester le code hors ligne sans compte bancaire. Pour une installation existante, suivez plutôt [la procédure de mise à jour](docs/UPDATE_EXISTING_TUNNEL.md) : ne recréez pas la clé de chiffrement.

## Installation

### 1. Récupérer le projet et vérifier les dépendances

Le script historique d’autorisation attend le dépôt dans `~/finance-bot`. Utilisez ce chemin pour suivre ce guide sans modifier ses chemins.

```sh
git clone https://github.com/edouaz/finance-bot.git "$HOME/finance-bot"
cd "$HOME/finance-bot"
./scripts/install.sh
```

`install.sh` crée `.venv`, installe les versions de `requirements.lock` et lance les vérifications hors ligne. Si `venv` manque sur Debian/Ubuntu, installez le paquet `python3-venv` de votre distribution. En cas d’incompatibilité Python, utilisez une version acceptée par les dépendances verrouillées plutôt que de supprimer le verrouillage.

### 2. Configurer votre application bancaire

Dans **votre copie locale** de `bank_auth.py`, remplacez :

| Valeur | Votre configuration |
| --- | --- |
| `APP_ID` | L’identifiant de votre propre application Enable Banking |
| `REDIRECT_URL` | Votre URL HTTPS, exactement identique à celle enregistrée auprès du fournisseur |

Le script d’autorisation historique ne lit pas ces deux valeurs depuis le fichier d’environnement. Le serveur v2, lui, lit `ENABLE_BANKING_APP_ID` : utilisez le même identifiant des deux côtés.

Placez votre clé privée RSA associée à l’application dans `~/finance-bot/keys/private.pem`, puis protégez-la :

```sh
mkdir -p keys data
chmod 700 keys data
# Copier votre propre clé privée dans keys/private.pem avant la commande suivante.
chmod 600 keys/private.pem
```

Pour votre callback, hébergez les fichiers de `public/` sur votre propre site HTTPS en conservant `callback.html` et `callback.js`. En cas de fork GitHub Pages, l’URL ressemble à `https://VOTRE_COMPTE.github.io/finance-bot/callback.html` ; vérifiez qu’elle fonctionne avant de l’enregistrer. Cette page retire les paramètres de la barre d’adresse, mais l’hébergeur peut journaliser l’URL initiale. Ne recopiez pas l’identifiant ou le callback du propriétaire pour votre application.

### 3. Préparer le stockage privé

```sh
mkdir -p "$HOME/.config/finance-tracker" "$HOME/.local/share/finance-tracker"
chmod 700 "$HOME/.config/finance-tracker" "$HOME/.local/share/finance-tracker"
.venv/bin/python -m finance.cli init-key "$HOME/.config/finance-tracker/data.key"
(umask 077; cp .env.example "$HOME/.config/finance-tracker/environment")
chmod 600 "$HOME/.config/finance-tracker/environment"
```

Ces commandes concernent une **installation neuve**. Conservez une copie protégée de la clé hors du serveur : sans elle, les données chiffrées ne sont pas récupérables. Ne remplacez jamais une clé utilisée par une base existante.

Éditez `~/.config/finance-tracker/environment` avec vos valeurs :

```dotenv
ENABLE_BANKING_APP_ID=votre-identifiant-application
ENABLE_BANKING_KEY=/chemin/absolu/vers/finance-bot/keys/private.pem
FINANCE_SESSIONS=/chemin/absolu/vers/finance-bot/data
FINANCE_STORAGE=/chemin/absolu/hors-du-depot/finance-tracker
FINANCE_DATA_KEY=/chemin/absolu/vers/data.key
```

Utilisez des **chemins absolus**, sans `$HOME` ni `~` dans ce fichier. La base et la clé de chiffrement doivent rester hors du dépôt. Les commandes `finance.cli` et l’entrée `finance_mcp.py` chargent ce fichier protégé ; un `.env` à la racine n’est pas chargé automatiquement. Les variables déjà exportées dans le processus ont priorité.

### 4. Autoriser vos comptes

```sh
.venv/bin/python bank_auth.py start bnp
```

Ouvrez l’URL affichée dans votre navigateur et suivez le consentement bancaire. Sur la page de retour, copiez l’URL depuis le champ prévu, puis lancez :

```sh
.venv/bin/python bank_auth.py finish bnp
```

Collez l’URL dans l’invite masquée du terminal. Ne la partagez pas dans un chat, une issue ou une capture d’écran. La commande vérifie le callback et le `state` ; l’autorisation en attente expire après 30 minutes. Pour Revolut, répétez avec `revolut` à la place de `bnp`. Autorisez uniquement les banques que vous souhaitez utiliser.

### 5. Vérifier et synchroniser

```sh
.venv/bin/python -m finance.cli health
.venv/bin/python -m finance.cli sync --bank bnp --start AAAA-MM-JJ --end AAAA-MM-JJ
```

Remplacez les deux dates par une petite période passée au format ISO, par exemple une semaine. Utilisez `--bank revolut` pour Revolut ; `--bank all` seulement après avoir autorisé les deux banques.

`health` vérifie le stockage local, pas la banque ni le tunnel. La synchronisation résume `accounts_processed`, `complete` et `errors` sans afficher les transactions. Une synchronisation partielle ne garantit pas un historique complet : examinez la couverture avant d’interpréter les totaux.

### 6. Brancher un client MCP

Pour un client acceptant un serveur local en **stdio**, adaptez ce bloc à son format de configuration et remplacez les chemins :

```json
{
  "mcpServers": {
    "finance-tracker": {
      "command": "/chemin/absolu/vers/finance-bot/.venv/bin/python",
      "args": ["/chemin/absolu/vers/finance-bot/finance_mcp.py"]
    }
  }
}
```

L’entrée `finance_mcp.py` charge l’environnement protégé, puis lance la v2. Le processus attend des messages MCP : l’absence d’affichage dans un terminal est normale. Les outils consultent le cache ; synchronisez avec la CLI pour actualiser les données.

Pour ChatGPT via un tunnel privé, consultez [le déploiement](docs/DEPLOYMENT.md) et [la récupération du tunnel](docs/TUNNEL_RECOVERY.md). Ces documents contiennent aussi des informations propres au serveur d’origine : adaptez chemins, utilisateur et profil. Ne publiez jamais le serveur bancaire comme une API anonyme. Des informations financières retournées par MCP peuvent être transmises au fournisseur du client utilisé.

## Dépannage

| Symptôme | À vérifier |
| --- | --- |
| `application_id_not_configured` | Identifiant dans le fichier `environment`, ou variable exportée prioritaire |
| `unsafe_environment_permissions`, `unsafe_key_permissions`, `unsafe_session_permissions` | Permissions `600` du fichier concerné ; ne rendez pas les secrets accessibles à tous |
| `storage_must_be_outside_repository`, `key_must_be_outside_repository` | Emplacement de la base ou de la clé de chiffrement |
| Session absente, expirée ou `reauthorization_required` | Refaire `start` puis `finish` pour la banque concernée |
| `authorization_unavailable` | Application, clé et autorisations fournisseur ; ce code ne prouve pas à lui seul une expiration bancaire |
| Callback refusé | Même URL HTTPS dans `bank_auth.py` et chez le fournisseur, puis nouveau `start` |
| Aucun résultat / couverture partielle | Consentement, dates, limites d’historique bancaire et dernière synchronisation |
| Outils absents dans ChatGPT | Diagnostic du tunnel et découverte MCP ; un `health` local réussi ne suffit pas |

## Tests et développement

```sh
./scripts/verify.sh
# Prévisualiser uniquement le site statique :
python3 -m http.server 8000 --directory public
# Puis ouvrir http://localhost:8000
```

Les tests utilisent des clés générées et des données synthétiques, sans appels bancaires. **Ne lancez pas une découverte de tests à la racine** : le fichier historique `test_api.py` fait un appel réel à l’import. Le script de vérification limite la découverte à `tests/`.

Le site ne nécessite ni framework frontend, ni compilation, ni service tiers. Les animations CSS respectent `prefers-reduced-motion`. Pour GitHub Pages, publiez uniquement le contenu de `public/` (y compris `favicon.svg`), jamais la racine du projet ni les fichiers de configuration privés. Le script historique `scripts/publish_pages.sh` est réservé au compte d’origine et refuse un dépôt déjà existant ; ce n’est pas une commande de mise à jour ni une procédure générique pour les forks.

## Repères dans le dépôt

| Chemin | Rôle |
| --- | --- |
| `finance/` | Accès fournisseur, stockage chiffré, synchronisation et analyses |
| `finance_mcp.py` / `finance_mcp_v2.py` | Entrée stable / outils MCP en lecture seule |
| `bank_auth.py` | Autorisation bancaire, côté opérateur |
| `public/` | Présentation, confidentialité, conditions et callback |
| `tests/` | Tests synthétiques et intégration MCP |
| `deploy/`, `scripts/` | Installation et modèles de services Linux à adapter |

[Maintenance et sauvegardes](docs/DEPLOYMENT.md) · [Réautoriser une banque](docs/BANK_REAUTHORIZATION.md) · [Arrêt d’urgence](docs/EMERGENCY_SHUTDOWN.md) · [Audit technique](docs/PROJECT_AUDIT.md)

Les devises restent séparées. Catégories, récurrences et alertes sont des heuristiques, pas des conseils financiers. Ne publiez jamais clés, sessions, base, sauvegardes, rapports ou URLs d’autorisation. Avant de proposer une modification, lancez les vérifications hors ligne et utilisez uniquement des exemples fictifs dans les issues et captures.
