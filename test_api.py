from pathlib import Path
import time
import jwt
import requests

APP_ID = "b0d5b4da-d0e4-45ed-95fc-3267a2e7f353"
PRIVATE_KEY = Path.home() / "finance-bot/keys/private.pem"

with open(PRIVATE_KEY, "rb") as f:
    private_key = f.read()

now = int(time.time())

token = jwt.encode(
    {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": now,
        "exp": now + 3600,
    },
    private_key,
    algorithm="RS256",
    headers={"kid": APP_ID},
)

response = requests.get(
    "https://api.enablebanking.com/application",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    },
    timeout=20,
)

print("HTTP status:", response.status_code)

if response.ok:
    data = response.json()
    print("API authentication: OK")
    print("Application status:", data.get("status", "Not returned"))
else:
    print("API authentication failed")
    print("Provider error (response withheld)")
