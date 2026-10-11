import json
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import jwt
import requests

BASE = Path.home() / "finance-bot"
API = "https://api.enablebanking.com"
APP_ID = "b0d5b4da-d0e4-45ed-95fc-3267a2e7f353"

def get_headers():
    now = int(time.time())
    private_key = (BASE / "keys/private.pem").read_bytes()

    token = jwt.encode(
        {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": APP_ID},
    )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

def get(url, params=None):
    try:
        response = requests.get(
            url,
            headers=get_headers(),
            params=params,
            timeout=30,
        )
        if response.status_code != 200:
            print(f"  Erreur HTTP {response.status_code}")
            return None

        return response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"  Échec de la requête : {type(e).__name__}")
        return None

def check_bank(bank):
    print(f"\n=== {bank.upper()} ===")

    session_file = BASE / "data" / f"{bank}_session.json"
    if not session_file.is_file():
        print("Session introuvable")
        return

    session = json.loads(session_file.read_text())
    session_id = session.get("session_id")

    if not session_id:
        print("Session ID manquant")
        return

    info = get(f"{API}/sessions/{session_id}")
    if info is None:
        return

    print("Session :", info.get("status", "Inconnu"))
    print("Expiration :", info.get("access", {}).get("valid_until", "Inconnue"))

    account_ids = info.get("accounts", [])
    print("Comptes :", len(account_ids))

    for index, account_id in enumerate(account_ids, start=1):
        print(f"\nCompte {index}")

        balances = get(f"{API}/accounts/{account_id}/balances")
        if balances is not None:
            print("  Soldes : OK")
            print("  Types de solde :", len(balances.get("balances", [])))

        start = (datetime.now(timezone.utc) - timedelta(days=30)).date()
        end = datetime.now(timezone.utc).date()

        params = {
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
        }

        total = 0
        pages = 0
        seen = set()

        while True:
            data = get(
                f"{API}/accounts/{account_id}/transactions",
                params=params,
            )
            if data is None:
                print("  Transactions : échec ou accès indisponible")
                break

            total += len(data.get("transactions", []))
            pages += 1

            continuation = data.get("continuation_key")
            if not continuation:
                print(f"  Transactions sur 30 jours : {total}")
                print(f"  Pages récupérées : {pages}")
                break

            if continuation in seen or pages >= 100:
                print("  Pagination interrompue : limite de sécurité")
                break

            seen.add(continuation)
            params["continuation_key"] = continuation

for bank in ("bnp", "revolut"):
    check_bank(bank)
