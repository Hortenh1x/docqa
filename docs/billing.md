# Daily AI allowance

Production enables `BUDGET_ENABLED=true` and `BUDGET_DAILY_USD=0.50`. This is a daily
allowance, resetting at 00:00 UTC. There is no global monetary cap.

A guest is identified by a stable HMAC of the client IP (IPv6 addresses use their
/64 network). `BUDGET_IP_SECRET` must be a stable secret of at least 32 characters;
changing it changes visitor identities. Trust forwarded IP headers only when the
ingress replaces untrusted client headers. Users behind one NAT share an allowance.

At login, the account receives associations with that day's guest reservations.
Spending $0.20 as a guest leaves $0.30 after login. Repeated login does not duplicate
the debit; settling an in-flight guest call updates the same reservation. Existing
account spending remains. Both the account and current IP must have enough allowance,
so login, logout or a second account cannot reset the current IP's budget. Changing
networks does not reset an account's accumulated spending.

Every paid embedding batch, LLM attempt and retry reserves a conservative input and
maximum-output charge before its HTTP call. Known provider usage replaces that
reservation; missing usage or an interrupted stream retains the full reservation.
Prices use configured known models and cache-miss/peak rates, so the ledger is a
conservative allowance rather than the provider's invoice. An unknown model or an
unavailable ledger fails closed before the call. Free local/stub models cost zero.
Background ingestion and suggestions retain the owner and triggering IP in the DB.
Trusted service-tenant operator jobs are outside visitor quotas.

PostgreSQL serializes short admission transactions; no lock is held during provider
I/O. This also makes pending reservations survive an API/worker restart. Failed
ingestion keeps the uploaded original. After reset, its verified owner can explicitly
retry it; retries use the current IP and remain subject to both limits.

`GET /v1/budget` reports spent, reserved and remaining USD, the controlling scope and
the UTC reset. Exhaustion is `429 quota_exceeded` with `Retry-After` and `reset_at`;
stream errors carry the same reset information. `503 budget_unavailable` means no
paid request was admitted. Redis per-minute counters remain separate traffic controls;
the legacy daily request counter is disabled when monetary accounting is enabled.

Back up the spend tables with accounts and documents. Do not delete pending rows to
free a balance: the provider may already have charged them. Account and IP allocations
reference the same reservation, so summing allocations would double-count service cost.
