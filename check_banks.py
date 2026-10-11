import runpy
import requests

# Réutilise le JWT créé par ton script fonctionnel
# sans afficher le token.
data = runpy.run_path("test_api.py")
token = data["token"]

response = requests.get(
    "https://api.enablebanking.com/aspsps",
    params={"country": "BE"},
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    },
    timeout=20,
)

response.raise_for_status()

for bank in response.json().get("aspsps", []):
    name = bank.get("name", "")
    if any(x in name.lower() for x in ["bnp", "fortis", "revolut"]):
        print({
            "name": name,
            "country": bank.get("country"),
        })
