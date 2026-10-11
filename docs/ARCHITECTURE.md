# Architecture

Bank -> Enable Banking GET client -> operator-only synchronization -> SQLite -> read-only cached MCP -> outbound OpenAI Secure MCP Tunnel -> ChatGPT.

MCP has no sync, SQL, filesystem or shell tool. Account references are opaque hashes of bank + primary identification hash when supplied, otherwise uid. Bank separation is maintained. entry_reference identifies transactions within an account; unstable transaction_id remains encrypted raw metadata only. Fallback hashes deliberately exclude transaction_id and balance_after_transaction. Same-fetch identical fallback entries receive occurrence suffixes; cross-fetch identity remains ambiguous.

Database schema v1: accounts, transactions, balances, syncs; user_version migration marker; indexed bank/account/date/currency/status lookup. Per-operation connections, transactions, 30-second SQLite busy timeout and DELETE journaling. Financial descriptions, amounts, raw payloads and provider UIDs are encrypted; dates/currency/status/index metadata are not. Fernet authenticated encryption detects altered payloads. No key is generated automatically on startup.

Transactions paginate by opaque local ID, up to 100 outputs; text filtering scans up to 1,000 rows per call, returning a continuation even on an empty filtered page. Reuse all filters. Analytics refuse over 20,000 source rows. Category/merchant group outputs cap at 100; alert and recurrence outputs also cap at 100. Historical balances/syncs cap at 100 snapshots/attempts. Coverage merges successful fetch intervals, flags stale results after 24 hours and includes the latest failed attempt. Provider limitations and omissions remain an explicit warning.

Consumption excludes known owned-account transfers, transfer-like descriptions, savings transfers, cash withdrawals and credit-card repayment candidates. Refunds reduce net spending; pending entries excluded. Unknown credits are separate from heuristic salary income. All arithmetic uses Decimal; no implicit FX. Recurrence requires three booked observations with regular weekly/monthly/yearly gaps; price increases require >5% over previous median. Unusual amounts require at least eight observations and exceed median + max(20 currency units, 6 MAD). Equal/opposite transfers and duplicate payments remain candidates unless independently confirmed by counterparty identity.

Reports include limitations and review recommendations. Savings-account balance changes are unavailable until accounts are explicitly labeled. Full metadata remains encrypted for future safe reconciliation; raw bank metadata is never exposed in MCP.

Provider client can fetch all available provider history by omitting both date parameters, with the same pagination bounds. Operator sync currently takes explicit dates so coverage can be recorded meaningfully. All-bank coverage also flags a bank absent from the local store rather than presenting the remaining bank as complete.
