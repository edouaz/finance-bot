import json
import time
from pathlib import Path
from datetime import datetime, timezone

import jwt
import requests
from mcp.server.fastmcp import FastMCP

BASE = Path.home() / "finance-bot"
APP_ID = "b0d5b4da-d0e4-45ed-95fc-3267a2e7f353"
API = "https://api.enablebanking.com"

BANKS = {
    "bnp": "BNP Paribas Fortis",
    "revolut": "Revolut",
}

mcp = FastMCP("Personal Finance Tracker")


def api_headers():
    now = int(time.time())
    key = (BASE / "keys/private.pem").read_bytes()

    token = jwt.encode(
        {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 600,
        },
        key,
        algorithm="RS256",
        headers={"kid": APP_ID},
    )

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


def api_get(path):
    response = requests.get(
        API + path,
        headers=api_headers(),
        timeout=25,
    )
    response.raise_for_status()
    return response.json()


def session_id(bank):
    if bank not in BANKS:
        raise ValueError("Banque non autorisée")

    path = BASE / "data" / f"{bank}_session.json"
    data = json.loads(path.read_text())
    return data["session_id"]


def get_accounts(bank):
    session = api_get(
        f"/sessions/{session_id(bank)}"
    )
    accounts = session.get("accounts", [])
    return session, accounts


@mcp.tool()
def get_connection_status() -> dict:
    """
    Vérifie la disponibilité des sessions bancaires.
    Ne retourne aucune information financière sensible.
    """
    result = {}

    for bank, name in BANKS.items():
        try:
            session, accounts = get_accounts(bank)
            result[bank] = {
                "bank": name,
                "status": session.get("status", "unknown"),
                "account_count": len(accounts),
                "valid_until": session.get(
                    "valid_until",
                    session.get("access", {}).get(
                        "valid_until"
                    ),
                ),
            }
        except Exception:
            result[bank] = {
                "bank": name,
                "status": "unavailable",
            }

    return result


@mcp.tool()
def get_balances(bank: str = "all") -> dict:
    """
    Consulte les soldes bancaires en lecture seule.
    bank: 'bnp', 'revolut' ou 'all'.
    N'expose pas les IBAN ni les identifiants de compte.
    """
    if bank not in ("bnp", "revolut", "all"):
        return {"error": "Banque invalide"}

    selected = (
        list(BANKS)
        if bank == "all"
        else [bank]
    )

    result = {}

    for code in selected:
        try:
            _, accounts = get_accounts(code)
            balances = []

            for account_id in accounts:
                data = api_get(
                    f"/accounts/{account_id}/balances"
                )

                for item in data.get("balances", []):
                    amount = item.get(
                        "balance_amount", {}
                    )
                    balances.append({
                        "type": item.get(
                            "balance_type"
                        ),
                        "amount": amount.get(
                            "amount"
                        ),
                        "currency": amount.get(
                            "currency"
                        ),
                    })

            result[code] = {
                "bank": BANKS[code],
                "balances": balances,
            }

        except Exception:
            result[code] = {
                "bank": BANKS[code],
                "error": "Accès indisponible",
            }

    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
