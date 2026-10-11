# Project audit — 2026-10-11

## Initial state, before implementation

Five Python scripts, RSA key/certificate, two session JSON files, existing virtualenv. No README, migrations, database, automated tests or local website source. `finance_mcp.py` exposes connection status and balances; `read_accounts.py` paginates 30-day transactions but prints diagnostics and executes on import. Existing MCP deployment preserved; code-only backup created in `/tmp/finance-v1-backup` (0700). This is temporary and not disaster recovery.

Python 3.13; MCP SDK 1.30.0; PyJWT 2.15.1; requests 2.34.2; cryptography 50.0.2. Exact installed dependency set in requirements.lock. Tunnel-client 0.0.16, existing finance-bot profile (0600), stdio command pointing to finance_mcp.py. No inbound MCP listener added.

Private key 0600; session files 0600; containing directories 0700. Public certificate 0664. Existing secrets remain in ignored directories for compatibility. Application ID hardcoded in legacy scripts (identifier, not RSA credential). Private key loaded for each JWT; JWTs correctly use RS256, kid, issuer, audience, iat and expiration. v1 lacks retries and transaction persistence; exceptions collapse into generic unavailable states. Auth helper validates redirect origin/path and state, but pending state originally lacked lifetime and terminal input echoed authorization URL. Provider response text was printed by two scripts.

## API review

Official reference: https://enablebanking.com/docs/api/reference/ (accessed 2026-10-11).
GET session returns account uid strings plus accounts_data. Account details/balances/transactions are separate GET operations. Transactions use inclusive date_from/date_to and continuation_key. Continuation is session-scoped. entry_reference is immutable within account identification; transaction_id is explicitly unsuitable for identity. Normalize direction with CRDT/DBIT while retaining original amount. BOOK/PDNG remain separate. Session AUTHORIZED and access.valid_until checked. Bank features and date limits vary: a drained pagination sequence is not proof of full bank history. No payment endpoints implemented.

## Checks and access limitations

Read-only live session requests attempted for both banks: network_unavailable in this sandbox. No financial payload printed or saved. Tunnel doctor exits 2: CONTROL_PLANE_API_KEY environment variable missing; profile references that variable. The secret is not present in this execution environment. User systemd bus access denied, so actual service state cannot be verified. No systemd service was installed or restarted.

`.git` is an empty, read-only placeholder, not an accessible repository. Tracked files and historical secret exposure cannot be audited here. GitHub Pages callback/privacy/terms retrieval and remote contents retrieval failed. Existing public source and remote history remain unverified. Publication is blocked pending real repository/history inspection; nothing pushed.

## Changes and residual risks

New v2 is separate from existing MCP. SQLite financial payloads encrypted with Fernet using a separately configured external key; indexed dates, bank labels, currencies, statuses and opaque account references remain plaintext. Encryption does not protect a compromised running account. 0700 storage and 0600 files enforced; DB backups use SQLite backup API. Schema version 1 rejects future unsupported versions.

Removed raw provider-error printing from legacy auth/test helpers and masked callback terminal input. Legacy read_accounts/test_api retain import-time network calls; excluded from automated test discovery. Do not expose them as model tools.

Fallback transaction identities are explicitly ambiguous: identical records retain same-fetch multiplicity, but changed raw metadata can duplicate records on later syncs; pending/booked transitions without stable IDs are not safely reconciled. Raw metadata retained encrypted for operator review. Heuristic classifications can misclassify cashflows; unknown credits are not assumed income and transfer-like debits excluded from consumption. No bank capability discovery UI, durable classification overrides, automatic FX conversion or savings-account labeling implemented. No static callback can erase an initial query from hosting logs.

Scheduled task docs permit connected tools generally but do not establish this specific private plugin's runtime availability. No end-to-end scheduled ChatGPT invocation verified. Optional systemd report timer is supplied, not enabled, with no external delivery or paid model API calls.

## Offline validation update

38 synthetic unit tests pass, covering JWT verification, retries, pagination failures, identity, currencies, refunds, transfers, pending/undated transactions, coverage, encrypted backup, budget and repeated weekly report output. One additional real MCP stdio subprocess test passes outside the sandbox: initialize, discover 15 tools, safe status call and invalid tool request. Inside the sandbox, AnyIO worker callbacks stall even for a trivial constant-return function; this is an execution restriction, not a server failure. Compilation and pip dependency consistency checks pass. Systemd calendar parsing confirms Monday 06:00 Europe/Brussels (DST-aware). No production service change.

## Final live validation outside the sandbox

Both Enable Banking sessions verified AUTHORIZED, one account each; valid_until 2026-10-21 (BNP 20:40 UTC, Revolut 20:42 UTC). Seven completed Brussels calendar days synchronized successfully: 5 BNP, 4 Revolut records, no provider/normalization warnings. Account details and balances also fetched. Only counts/status printed; encrypted financial data stored outside repository.

Created private configuration at /home/edouard/.config/finance-tracker (0700), data.key and environment (0600), and encrypted SQLite at /home/edouard/.local/share/finance-tracker. Operator must retain an offline recovery key copy. Existing RSA key and banking sessions untouched. CONTROL_PLANE_API_KEY still unavailable. Both system/user finance-bot.service and finance-tunnel.service report inactive; this does not establish whether an interactive tunnel process is running. No restart or profile change.

Final verification: 39 tests pass (38 synthetic calculation/storage/client tests plus one actual MCP stdio protocol test). Compileall and pip check pass. History beyond seven days and end-to-end ChatGPT discovery remain unverified.

Final expanded verification: 42 tests pass in 1.566 seconds. Live encrypted weekly report generation and database health pass. Real bank metadata contained a null transaction-code description; parser repaired with a synthetic regression test. Git is not installed; remote clone/history audit remains blocked independently of the placeholder local .git.

Direct public checks outside the sandbox returned HTTP 404 for GitHub API repository edouaz/finance-bot and the stated GitHub Pages callback URL. This may reflect a private/unavailable repository or an incorrect public address; no authentication or remote mutation attempted. Existing public callback source could not be audited.
