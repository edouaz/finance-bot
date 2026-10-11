# Bank reauthorization

v2 checks session status AUTHORIZED and UTC valid_until; expired/cancelled sessions require new user consent. 401/403 can also mean application authentication problems and are reported as authorization_unavailable rather than asserted bank expiry. Bank-specific features are not presumed.

Keep the currently registered redirect URL unchanged: https://edouaz.github.io/finance-bot/callback.html . Existing bank_auth.py remains operator-only:

```sh
.venv/bin/python bank_auth.py start bnp
.venv/bin/python bank_auth.py finish bnp
# Repeat with revolut when necessary.
```

Open the authorization URL privately. Finish validates redirect scheme/host/path and state, and now accepts the callback URL without echoing it in the terminal. Never paste callback URLs or auth codes into chat. Session creation is a consent-management operation, not an MCP tool. Session files remain 0600 in ignored data/. Account identification hashes preserve local identities across renewed sessions when available.

A static callback cannot prevent initial hosting logs containing the code. Before switching to a VPS HTTPS callback: prepare TLS, private state storage with expiry, one-use callback handling, no-query logs and controlled replay tests; register/test the new redirect with explicit approval; retain rollback until both banks succeed. No redirect registration or revocation performed here.

Pending authorization state now expires after 30 minutes, uses constant-time comparison and is persisted with 0600 mode. Session updates are atomic; a failed write cannot truncate the previous working session. Pending authorizations created by the old version lack a creation timestamp and must be restarted.
