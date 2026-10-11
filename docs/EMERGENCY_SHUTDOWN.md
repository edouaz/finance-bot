# Emergency shutdown — operator procedure

No shutdown, revocation, deletion or rotation was executed. Obtain explicit approval for destructive operations.

1. Stop the current tunnel supervisor. If the supplied unit is active, `sudo systemctl stop finance-tunnel.service`; disable it to prevent automatic relaunch. Stop/disable finance-weekly.timer too. If using an interactive tunnel, stop that process. Do not use a broad process-kill command.
2. Revoke account-information consents in BNP/Revolut banking settings. This stops future bank access; it does not erase history.
3. Enable Banking supports DELETE /sessions/{session_id} with application JWT authentication (official API reference). An authorized operator may close the specific sessions after confirming identifiers privately. This operation is deliberately absent from MCP and CLI.
4. Disable the Enable Banking application through its control panel and disable the OpenAI tunnel/connector as appropriate. Credential rotation requires separate approval and a recovery plan.
5. Only when explicitly requested, remove local SQLite data, encrypted reports, session JSON, pending auth files, and all backups. Inventory actual paths from FINANCE_STORAGE/FINANCE_SESSIONS/FINANCE_DATA_KEY; do not paste contents. Removal is separate from consent revocation. Filesystem unlink is not guaranteed secure erasure on SSDs/snapshots; account for VPS/provider snapshots and offline copies. OpenAI conversation retention must be handled separately in the account's controls.

Recovery requires approved replacement credentials, restored protected configuration, offline tests, fresh consents when necessary and explicit verification of tool discovery. Never silently restart a revoked setup.
