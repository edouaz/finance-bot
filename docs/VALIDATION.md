# Validation results — 2026-10-11

- `./scripts/verify.sh`, outside sandbox: 42 tests passed in 1.566 seconds; no broken requirements; compileall passed.
- MCP subprocess: initialize, discovery of 15 read-only tools, safe status call and invalid-input response passed.
- Banking live read-only test: two AUTHORIZED sessions, 1 account each; seven-day sync 5 BNP/4 Revolut transactions, pagination drained without warnings; details/balances fetched. No records disclosed.
- Private encrypted storage and protected external key/environment initialized. No plaintext financial database in repository.
- Systemd weekly expression validates Monday 06:00 Europe/Brussels. Units/timer not installed or activated.
- Tunnel-client doctor: fails due to missing CONTROL_PLANE_API_KEY. Existing profile remains on v1.
- Named system/user finance-bot and finance-tunnel units: inactive. Interactive process state not established.
- Git history and remote/public page source unavailable; secret-history audit cannot be completed and no publication attempted.
- ChatGPT scheduled invocation of this private plugin remains unverified. Optional VPS scheduler prepared with encrypted local output and no external delivery.

Remaining: extend/live-verify historical sync; protect an offline key copy; establish actual tunnel supervisor and credential environment; stage v2 profile and verify ChatGPT discovery; install optional systemd units with correct private runtime write paths; approve any delivery channel; inspect remote history before publishing public pages.

Live weekly report was generated successfully at the protected external storage path after correcting a nullable bank_transaction_code description found in real data; regression test included. Git executable is absent, so remote clone/history inspection could not proceed.

Public repository API and callback URL both returned HTTP 404 in direct network checks. Prepared Pages source remains local; its deployment URL and existing remote policies require verification.

Follow-up rollout: the unchanged finance_mcp.py tunnel entrypoint now starts v2 and loads protected external finance configuration. 42 tests pass through this entrypoint. Requested one-year live synchronization completed for both accounts without errors; encrypted weekly report regenerated successfully. Timer moved to Monday 06:00 Europe/Brussels, calendar syntax validated. System-level activation awaits sudo authentication; user Linger=no, so unattended user-level scheduling was not substituted. GitHub connection remains unconfirmed; a static-only publication script and manual authenticated setup instructions are supplied. No repository creation or Pages publication performed.
