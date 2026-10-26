# MCP tools

17 registered endpoints over stdio: 15 cached read-only queries, one read-only private-interface link tool and one explicit synchronization tool. Errors use {"error":"safe_code"}; SDK rejects type/enum mismatches. Missing encryption configuration returns a safe local error; consent status can still be inspected.

| Tool | Functional views |
|---|---|
| get_reauthorization_link | bank=bnp or revolut only; configured private interface root with bank selection, no provider request or authorization start |
| get_connection_status | Cached expiry, days_remaining, expires_soon (7 days), reauthorization need; live_verified false |
| get_accounts | Opaque account references and bank separation |
| get_balances | Current snapshots; history=true for balance history |
| get_total_balance | One balance type, totals per currency, missing accounts |
| get_data_coverage | Inclusive date range, missing/stale coverage |
| sync_transactions | Fetch transactions, account details and balances from banks into the encrypted cache; start_date/end_date required, bank defaults to all; per-account results and overall complete flag |
| get_sync_status | Last 100 synchronization attempts |
| get_transactions | Search/history, refund kind, pending status, details via transaction_id |
| get_recent_transactions | Last N days and bounded pagination |
| get_spending_summary | Consumption, refunds, cashflow, estimated savings rate, daily average; category/merchant/date/month grouping |
| compare_periods | Changes, relative changes and period lengths; usable for trends |
| get_recurring_payments | Subscriptions filter, evidence, upcoming estimates, annual costs, price changes |
| get_financial_alerts | Unusual spending, duplicate and internal transfer candidates |
| get_financial_report | Weekly/monthly/yearly arbitrary date ranges, dashboard and largest transactions |
| get_weekly_report | Previous seven completed Brussels days plus year-long recurrence window |
| get_financial_intelligence | Explicit budget, fixed/variable estimates, recurring forecast and subscription review opportunities |

Example get_transactions parameters: start_date="2026-01-01", end_date="2026-10-11", bank="revolut", direction="outgoing", currency="EUR", min_amount="10", query="market", limit=50. next_cursor is opaque; keep all filters unchanged. A page can be empty with a non-null cursor because text filtering is bounded. Local transaction_id is the returned opaque ID, not Enable Banking's transient identifier.

get_spending_summary group_by="merchant" gives top merchant totals; "date" or "month" gives daily/monthly consumption. Group lists cap at 100: narrow the date range for longer daily series. get_financial_report returns 10 largest outflows; recurrence/alerts cap at 100. Analysis fails explicitly above 20,000 records. get_total_balance defaults to CLBD; if unavailable select a provider-supported type from get_balances. Never sum all available/booked/interim types together.

Budget input is an explicitly supplied amount, not stored configuration. Savings rate uses heuristic salary income and classified net consumption; it is not an authoritative wealth-change figure. No savings-account balance change or future-income forecast is invented.

`sync_transactions(start_date="2026-10-01", end_date="2026-10-14", bank="all")` refreshes the requested inclusive interval. Check `complete`, per-account errors and warnings before using the results. Concurrent MCP synchronizations return `sync_in_progress`. This tool writes local cache data and contacts banks using GET requests only; it cannot initiate payments. Restart the existing server/tunnel and refresh tool discovery to load it. Queries do not automatically synchronize. The optional weekly systemd timer must be installed and enabled separately.

Provider transaction statuses are preserved: BOOK, PDNG, CNCL, HOLD, OTHR, RJCT, SCHD. All are searchable with the status filter. Only BOOK contributes to financial totals, recurrence and alerts. Summary pending_excluded counts PDNG only; other_statuses_excluded reports the other excluded statuses. Sync warnings such as non_booked_status_OTHR identify uncertain/non-booked records without rejecting them. A complete fetch does not establish that OTHR is booked.

Consent reminders: any guarded tool response may include `connection_notices` with
bank, validated cached expiry, days remaining, a short message and renewal action.
The first tool call within seven days of expiry (or after expiry) can deliver the
notice, at most once per 24 hours per bank/expiry/state in this MCP process. Restarting
may repeat it; expiration or a changed session can prompt a fresh notice. Initialization
instructions ask ChatGPT to relay notices; client presentation is not guaranteed.
No bank calls, background messages, new scheduled task or bank-write permission is
added by checking consent metadata. Missing/malformed/private-permission failures
return session_unavailable through get_connection_status; reminder failure never
blocks cached queries. Existing clients must tolerate the optional response field.

`get_reauthorization_link(bank="bnp")` (or `"revolut"`) returns the configured private
interface root, for example `https://your-private-server.example/?bank=bnp`. It reads
`FINANCE_AUTH_REDIRECT_URL`, which must be an HTTPS URL with the exact `/callback`
path, a valid hostname/port and no credentials, query or fragment. Missing, malformed
or legacy GitHub Pages callback configuration returns `private_web_not_configured`;
there is no fallback to a public site. The tool uses the existing MCP tunnel access,
makes no network request, starts no banking authorization and performs no financial
cache writes. The user still authenticates and confirms on their own private server;
no bank code, state, session identifier or Enable Banking redirect is returned.

When private HTTPS is configured, `get_connection_status` also includes a validated
`renewal_url` per bank, even without a due reminder. This preserves access through
existing ChatGPT connections that have not yet refreshed discovery of the new
`get_reauthorization_link` tool. Invalid/missing web configuration omits that URL.
