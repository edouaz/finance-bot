> Current rollout update: finance_mcp.py now launches v2 without changing the profile. See UPDATE_EXISTING_TUNNEL.md; the earlier explicit profile-switch procedure below is an alternative, not required.

# Deployment and maintenance

## Current status

v1 tunnel profile unchanged. SDK 1.30.0, tunnel-client 0.0.16. Doctor fails because CONTROL_PLANE_API_KEY is absent in this environment. Sandbox checks initially failed. Outside the sandbox, named finance-bot/finance-tunnel system and user services report inactive, and both banking sessions are AUTHORIZED. Seven-day live synchronization succeeded (5 BNP, 4 Revolut records). No services activated. External encryption key, environment file and SQLite storage have been initialized under the owner’s .config/.local/share directories with restrictive permissions. Deployment must be verified on the actual host with its protected runtime environment. No paid model calls or external delivery added.

## Prepare

```sh
cd /home/edouard/finance-bot
./scripts/install.sh
# Choose external key location and protect its parent directory.
# Only on a new installation; this host already has a key. Never overwrite it.
.venv/bin/python -m finance.cli init-key /home/edouard/.config/finance-tracker/data.key
```

Install script pins the installed dependency snapshot; review registry availability before assuming replay on another host. Existing venv is not upgraded during this development run. Set a 0600 `/home/edouard/.config/finance-tracker/environment` based on .env.example, with the existing application ID and tunnel credential supplied by the operator. EnvironmentFile syntax must be compatible with systemd; for manual runs export the variables through a protected shell environment. .env is not automatically loaded. Never paste credentials in ChatGPT. Legacy secrets can remain in keys/data for initial compatibility, then migrate to external directories with backups.

```sh
.venv/bin/python -m finance.cli health
.venv/bin/python -m finance.cli sync --bank all --start 2026-01-01 --end 2026-10-11
.venv/bin/python finance_mcp_v2.py
```

The last command runs stdio and waits for MCP input. Test with an MCP client (tests/test_stdio.py demonstrates the protocol). Check summaries/coverage before requesting data in ChatGPT. Retries and provider limits may leave partial results; do not treat count alone as success.

## Tunnel rollout

1. Securely copy existing finance-bot YAML and runtime environment outside the repository (0700/0600); current /tmp backup contains code only.
2. Verify current v1 discovery with the real tunnel credential; run tunnel-client doctor --profile finance-bot without exposing credentials/log exports.
3. After offline and live v2 tests pass, change only the profile command to `/home/edouard/finance-bot/.venv/bin/python /home/edouard/finance-bot/finance_mcp_v2.py`.
4. Restart through the existing supervisor. Re-run doctor, local health endpoints and ChatGPT tool discovery. Confirm date-range transactions and coverage without dumping records to logs.
5. If unsuccessful restore profile command to finance_mcp.py and restart. Do not revoke bank sessions for an application rollout.

Supplied systemd templates require operator installation in /etc/systemd/system. `finance-tunnel.service` restarts on failure; runs as current owner with UMask, NoNewPrivileges, PrivateTmp, read-only home/system and a single storage write path. Confirm whether tunnel-client needs another private runtime write path before enabling it. Do not run both an existing tunnel supervisor and this unit. Dedicated account rollout requires narrowly granted access to key, sessions and tunnel credentials; not provisioned here.

## Weekly workflow

`finance-weekly.timer` schedules Monday 06:00 Europe/Brussels, DST-aware, Persistent=true. weekly.sh fetches a year of provider-limited history and produces an encrypted structured report, even if synchronization fails so failures remain visible. Long history may exceed provider limits; adjust the request for each bank after capability verification. No email, Slack or paid API delivery. Report output is atomically replaced each week. Retrieve through get_weekly_report or decrypt locally with Store.unseal as an authorized operator, never a public URL.

Official scheduled task documentation: https://learn.chatgpt.com/docs/automations . Connected tools may be available, but this private plugin's actual scheduled execution has not been proven. No automation API is available in this session; no ChatGPT schedule created. Verify with a one-off task after connector deployment; retain local timer fallback. Secure tunnel documentation: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels . No inbound MCP port required.

## Backups/recovery

```sh
.venv/bin/python -m finance.cli backup /secure/external/location/finance-backup.sqlite3
```

Destination must not exist or be inside the repository. SQLite backup API yields a consistent snapshot and 0600 backup. Keep offline recovery copies of RSA key, session/config (if needed) and encryption key, separately protected. Stop writers, verify SQLite integrity, restore DB into private FINANCE_STORAGE, restore the matching encryption key, run health and a test read. Recovery is documented, not executed against real data. No automatic retention purge; operator manages disk usage and deletes only with explicit authorization.

## Public Pages

Only publish public/ after inspecting the real remote source and complete Git history for credentials. No publication performed. Preserve callback path and registered redirect URL. Existing public policy may differ; source fetch failed in this run. Do not enable Pages from repository root containing legacy private artifacts.
