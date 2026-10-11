# Personal Finance Tracker v2

Private read-only Python MCP server for Enable Banking, BNP Paribas Fortis Belgium and Revolut Belgium. The existing tunnel entrypoint finance_mcp.py now launches v2; restart the existing process to load the update. The profile and plugin are unchanged.

## Structure

- `finance/core.py`: validation, JWT, bounded GET retries, session checks, paginated transactions.
- `finance/store.py`: versioned SQLite, encrypted financial payloads, backups.
- `finance/service.py`: operator synchronization, bounded queries, coverage and reporting.
- `finance/analytics.py`: Decimal cashflow, categorization, recurrence and explainable alerts.
- `finance/cli.py`: local synchronization, encryption-key setup, health, backup, weekly report.
- `finance_mcp_v2.py`: 15 read-only cached MCP tools, stdio only.
- `tests/`: synthetic unit and MCP integration checks.
- `public/`: landing, privacy, terms and callback source; not published.
- `deploy/`, `scripts/`: optional services, Monday timer and verification.
- Legacy scripts, keys and sessions: retained for compatibility, secrets ignored.

## Verify

```sh
./scripts/verify.sh
```

Tests use temporary encrypted stores and generated RSA keys. They never call banks. Do not use root-wide pytest discovery: the legacy `test_api.py` executes a live call on import.

## Configure and operate

Follow [deployment](docs/DEPLOYMENT.md). v2 requires ENABLE_BANKING_APP_ID and an external encryption key. It intentionally refuses unprotected storage or a database inside the repository. Both bank sessions were verified AUTHORIZED outside the sandbox; a seven-day live sync completed with 5 BNP and 4 Revolut transactions stored encrypted. External storage/key/environment configuration was initialized. The tunnel runtime credential remains unavailable, so the existing profile has not been switched.

Financial results stay separate by currency. Recurring charges, merchant categories and alerts are heuristic, with evidence. Coverage reflects successfully fetched provider intervals, not guaranteed bank completeness. Review fallback identities before treating totals as authoritative.

[Audit](docs/PROJECT_AUDIT.md) · [Architecture](docs/ARCHITECTURE.md) · [Tools](docs/MCP_TOOLS.md) · [Security](docs/SECURITY.md) · [Reauthorization](docs/BANK_REAUTHORIZATION.md) · [Emergency shutdown](docs/EMERGENCY_SHUTDOWN.md)

For the existing tunnel update, Monday 06:00 activation and safe GitHub Pages publication, see [update instructions](docs/UPDATE_EXISTING_TUNNEL.md).
