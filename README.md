# Finance Tracker

**A self-hosted finance MCP server for ChatGPT.** Connect your bank accounts, explore spending and review recurring payments through read-only tools backed by an encrypted local cache.

[Website](https://edouaz.github.io/finance-bot/) · **[Installation guide](https://edouaz.github.io/finance-bot/installation.html)** · [MCP tools](docs/MCP_TOOLS.md) · [Security](docs/SECURITY.md)

- **Run it yourself:** Python on your computer or VPS. No frontend build or Docker setup required.
- **Store history locally:** encrypted SQLite financial payloads, with a separate encryption key outside the repository.
- **Connect ChatGPT:** a private Secure MCP Tunnel routes calls to the stdio server. Tools cannot make payments or transfers.
- **Review estimates:** categories, recurring charges and alerts include context; currencies stay separate and coverage can be incomplete.

The project targets BNP Paribas Fortis Belgium and Revolut Belgium through Enable Banking. Provider access and bank availability depend on your application. This is a personal project, not a hosted banking service or an official bank integration. The website uses fictional data and does not connect to any account.

## Installation

The [website installation guide](https://edouaz.github.io/finance-bot/installation.html) covers the full path: prerequisites, bank application, callback, encryption, consent, synchronization, tunnel creation, ChatGPT connection and optional Linux service. Its source is [public/installation.html](public/installation.html), which you can also preview locally before publication.

Start with Python **3.10+**, Git and a shell on Linux or macOS. You need your own Enable Banking application ID, matching RSA private key and registered HTTPS callback. For ChatGPT, you also need custom MCP access and the appropriate OpenAI tunnel permissions. These are separate from bank consent.

```sh
git clone https://github.com/edouaz/finance-bot.git "$HOME/finance-bot"
cd "$HOME/finance-bot"
./scripts/install.sh
```

The installer creates `.venv`, installs `requirements.lock` and runs offline checks. If virtual environments are unavailable on Debian/Ubuntu, install `python3-venv`. Use a Python version supported by the locked dependencies rather than removing the lock file.

Before connecting real accounts:

1. Host `public/` on your own HTTPS website. Register its exact `callback.html` URL with Enable Banking.
2. Set your own `APP_ID` and `REDIRECT_URL` in your local `bank_auth.py`. That historical script expects `~/finance-bot` and does not read these constants from the environment.
3. Place your application’s RSA key at `keys/private.pem` (mode `600`); protect `keys/` and `data/` with mode `700`.
4. Create the external encryption key and environment file as shown in the guide. Use absolute paths and your own application ID. **Never replace an encryption key used by an existing database.**
5. Authorize each desired bank with `bank_auth.py start bnp` and `bank_auth.py finish bnp` using `.venv/bin/python`. Repeat with `revolut` if needed. Paste the callback URL only into the masked terminal prompt.
6. Check local health and synchronize a short past date range. Configure the private tunnel, then verify a read-only tool call from ChatGPT.

The protected configuration file is `~/.config/finance-tracker/environment` (mode `600`):

```dotenv
ENABLE_BANKING_APP_ID=your-application-id
ENABLE_BANKING_KEY=/absolute/path/to/finance-bot/keys/private.pem
FINANCE_SESSIONS=/absolute/path/to/finance-bot/data
FINANCE_STORAGE=/absolute/path/outside-the-repository/finance-tracker
FINANCE_DATA_KEY=/absolute/path/to/data.key
```

Use the same application ID in `bank_auth.py` and this file. Do not use `$HOME` or `~` inside it. Keep the database and encryption key outside the repository. The CLI and `finance_mcp.py` load this file; a repository-root `.env` is not automatically loaded. Already exported process variables take precedence.

```sh
.venv/bin/python -m finance.cli health
.venv/bin/python -m finance.cli sync --bank bnp --start YYYY-MM-DD --end YYYY-MM-DD
```

Replace the dates with a short past interval in ISO format. Use `--bank revolut` for Revolut; `--bank all` only after authorizing both banks. `health` checks local storage, not the bank or tunnel. Check `complete`, `errors` and data coverage before relying on totals.

## Connecting an MCP client

For a client supporting local stdio servers, adapt this example to its configuration format:

```json
{
  "mcpServers": {
    "finance-tracker": {
      "command": "/absolute/path/to/finance-bot/.venv/bin/python",
      "args": ["/absolute/path/to/finance-bot/finance_mcp.py"]
    }
  }
}
```

The stable entrypoint loads the protected environment and starts v2. It waits for MCP input, so an idle terminal is expected. Tools query the cache; use the CLI to refresh it.

For ChatGPT, follow [the tunnel instructions](https://edouaz.github.io/finance-bot/installation.html#tunnel), based on [official OpenAI documentation](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels). The project launcher expects `~/.local/bin/tunnel-client` and profile `finance-bot`. The existing shell helpers and systemd templates contain the original owner’s paths and user; adapt them before use. Keep the bank server private. Financial information returned to ChatGPT is subject to your OpenAI account’s data settings.

## Tests and website preview

```sh
./scripts/verify.sh
python3 -m http.server 8000 --directory public
# Open http://localhost:8000
```

Tests use generated keys and synthetic data, without bank calls. **Do not discover tests from the repository root:** legacy `test_api.py` makes a live request on import. The verification script restricts discovery to `tests/`.

The static site needs no framework, build step or third-party services. CSS animations respect `prefers-reduced-motion`. Publish **only `public/`**, including the installation guide and favicon. Never publish keys, sessions, financial data, backups or the environment file.

The current live website uses `gh-pages:/`; merging `main` does not update that branch. The historical `scripts/publish_pages.sh` is owner-specific and refuses existing repositories, so it is not an update command or a generic fork deployment tool.

## Repository map

| Path | Purpose |
| --- | --- |
| `finance/` | Provider access, encrypted storage, synchronization and analysis |
| `finance_mcp.py` / `finance_mcp_v2.py` | Stable entrypoint / read-only MCP tools |
| `bank_auth.py` | Operator-only consent management |
| `public/` | Website, installation guide, policies and bank callback |
| `tests/` | Synthetic unit and MCP integration checks |
| `deploy/`, `scripts/` | Installation helpers and Linux service templates to adapt |

[Architecture](docs/ARCHITECTURE.md) · [Maintenance and backups](docs/DEPLOYMENT.md) · [Bank reauthorization](docs/BANK_REAUTHORIZATION.md) · [Tunnel recovery](docs/TUNNEL_RECOVERY.md) · [Emergency shutdown](docs/EMERGENCY_SHUTDOWN.md)

Older operational runbooks include details specific to the original host and some French content. For a new installation, start with the English website guide. Keep protected offline copies of your encryption key and necessary credentials; losing the key makes encrypted history unreadable. Estimates are not financial advice. Use fictional examples in issues and screenshots.
