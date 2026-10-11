# MCP tools

15 registered endpoints; all read-only, cached and stdio. Errors use {"error":"safe_code"}; SDK rejects type/enum mismatches. Missing encryption configuration returns a safe local error; consent status can still be inspected.

| Tool | Functional views |
|---|---|
| get_connection_status | Cached session expiration, reauthorization need; live_verified false |
| get_accounts | Opaque account references and bank separation |
| get_balances | Current snapshots; history=true for balance history |
| get_total_balance | One balance type, totals per currency, missing accounts |
| get_data_coverage | Inclusive date range, missing/stale coverage |
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
