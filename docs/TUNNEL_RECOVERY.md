# Tunnel recovery — 2026-10-12

Incident: ChatGPT returns McpServerError: Session terminated and still lists the two v1 tools. Direct inspection found no running tunnel-client/MCP process, and named system/user finance services are inactive. The protected finance configuration and SQLite store exist. Current v2 stdio initialization, 15-tool discovery and safe calls pass; local database health passes. No claim that the exact ChatGPT error has a single proven cause: the confirmed missing runtime must be fixed before testing remote sessions and cached discovery.

The tunnel profile and plugin identity are retained. A previous terminal-only CONTROL_PLANE_API_KEY is unavailable in the current environment. Existing banking consents do not supply this separate OpenAI credential. Do not create a new tunnel or revoke bank consents for this incident.

## One-time private credential setup

On the VPS in an interactive SSH terminal:

```sh
cd /home/edouard/finance-bot
./scripts/run_tunnel.sh configure
```

Enter the existing OpenAI tunnel API key at the masked prompt. It is stored outside the repository at ~/.config/finance-tracker/tunnel-api.key with permissions 0600. No overwriting or rotation. Never paste the key into chat or a shell command argument. The startup helper passes only a file reference to tunnel-client. Inherited CONTROL_PLANE_API_KEY is still supported when no saved file exists.

## Start persistently

```sh
./scripts/activate_tunnel.sh
```

This installs the supplied system-level service, requires the user's sudo authentication and enables automatic startup/restart. The helper cannot be completed by the agent while the key and sudo authentication are unavailable. It preserves the same finance-bot profile; finance_mcp.py loads v2. No new public MCP listener is created.

Check locally:

```sh
systemctl is-active finance-tunnel.service
/home/edouard/.local/bin/tunnel-client health --port 8080 --require-control-plane-poll
```

The health port is a local operator endpoint; confirm the profile's configured port if 8080 differs. Do not publish log exports or paste entire journal output containing credentials. A healthy tunnel poll is necessary but does not prove a ChatGPT report call succeeded.

For an immediate foreground test instead of persistent service activation:

```sh
./scripts/run_tunnel.sh
```

Keep the SSH terminal open for this foreground test. After startup, retry the connector from a fresh ChatGPT conversation. If only two tools remain despite a healthy tunnel, refresh the existing connector's discovery using the available UI; investigate stale sessions before recreating anything. Verify get_accounts, get_data_coverage and get_weekly_report. Remote discovery is not yet confirmed.

Source: https://developers.openai.com/api/docs/guides/secure-mcp-tunnels . Installed tunnel-client 0.0.16 help confirms file:/path credential references and local health probes.
