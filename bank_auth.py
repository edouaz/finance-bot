import sys
import json
import time
import secrets
import hmac
import os
from getpass import getpass
from pathlib import Path
from datetime import datetime, timedelta, timezone

import jwt
import requests

APP_ID = "b0d5b4da-d0e4-45ed-95fc-3267a2e7f353"
REDIRECT_URL = "https://edouaz.github.io/finance-bot/callback.html"

BANKS = {
    "bnp": "BNP Paribas Fortis",
    "revolut": "Revolut",
}

BASE = Path.home() / "finance-bot"
DATA = BASE / "data"
DATA.mkdir(mode=0o700, exist_ok=True)

def headers():
    now = int(time.time())
    key = (BASE / "keys/private.pem").read_bytes()

    token = jwt.encode(
        {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
        },
        key,
        algorithm="RS256",
        headers={"kid": APP_ID},
    )

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def start(bank):
    state = secrets.token_urlsafe(32)

    payload = {
        "access": {
            "valid_until": (
                datetime.now(timezone.utc)
                + timedelta(days=10)
            ).isoformat()
        },
        "aspsp": {
            "name": BANKS[bank],
            "country": "BE",
        },
        "state": state,
        "redirect_url": REDIRECT_URL,
        "psu_type": "personal",
    }

    response = requests.post(
        "https://api.enablebanking.com/auth",
        json=payload,
        headers=headers(),
        timeout=30,
    )

    print("HTTP status:", response.status_code)

    if not response.ok:
        print("Erreur fournisseur (réponse masquée)")
        return

    result = response.json()
    path = DATA / f"{bank}_pending.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(json.dumps({"state": state, "created_at": time.time()}))
    path.chmod(0o600)

    print("\nOuvre cette URL dans ton navigateur :")
    print(result["url"])
    print("\nAprès autorisation, reviens sur ton VPS.")
    print(f"Commande suivante : python3 bank_auth.py finish {bank}")

def finish(bank):
    from urllib.parse import urlparse, parse_qs

    pending = DATA / f"{bank}_pending.json"
    if not pending.exists():
        print("Aucune autorisation en attente.")
        return

    url = getpass("Colle l'URL finale du callback (entrée masquée) : ").strip()
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    expected = urlparse(REDIRECT_URL)
    if (parsed.scheme, parsed.netloc, parsed.path) != (
        expected.scheme, expected.netloc, expected.path
    ):
        print("URL de redirection incorrecte.")
        return

    pending_data = json.loads(pending.read_text())
    if time.time() - pending_data.get("created_at", 0) > 1800:
        print("Autorisation en attente expirée. Relancez start.")
        return
    state = pending_data["state"]

    if not hmac.compare_digest(params.get("state", [""])[0], state):
        print("ERREUR : state incorrect. Autorisation rejetée.")
        return

    code = params.get("code", [None])[0]
    if not code:
        print("Aucun code reçu (erreur fournisseur masquée)")
        return

    response = requests.post(
        "https://api.enablebanking.com/sessions",
        json={"code": code},
        headers=headers(),
        timeout=30,
    )

    print("HTTP status:", response.status_code)

    if not response.ok:
        print("Création de session échouée (HTTP", response.status_code, ")")
        return

    result = response.json()

    path = DATA / f"{bank}_session.json"
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix=".session-", dir=DATA)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(result, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists(): Path(temporary).unlink()
    path.chmod(0o600)
    pending.unlink()

    print("Session créée pour :", BANKS[bank])
    print("Nombre de comptes :", len(result.get("accounts", [])))
    print("Données enregistrées localement sur le VPS.")

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in BANKS or sys.argv[1] not in ("start", "finish"):
        print("Usage: python3 bank_auth.py start|finish bnp|revolut")
        sys.exit(1)

    if sys.argv[1] == "start":
        start(sys.argv[2])
    else:
        finish(sys.argv[2])
