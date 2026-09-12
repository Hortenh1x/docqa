# DocQA browser UI

The production account UI is enabled at **build time** with
`NEXT_PUBLIC_ACCOUNTS_ENABLED=true`. Set `NEXT_PUBLIC_API_BASE_URL` to the API origin
and leave `NEXT_PUBLIC_DEMO_API_KEY` empty. Account builds reject a browser API key.
Use HTTPS and the configured same-site UI/API origins for Secure session cookies.
The Dockerfile accepts the same public build arguments.

Account mode obtains a session before showing collection data and revalidates it
before every mutation. Requests use cookies and the current session CSRF token.
Session changes abort fetches, streams and uploads, replace the query cache, close
readers and revoke their blob URLs, and discard answers/drafts. A BroadcastChannel
coordinates sign-out across tabs; returning to a hidden tab checks its session
again. Account forms stay hidden but mounted during that check; an unchanged
identity preserves their in-memory proof/password, while a changed or invalid
session discards them. Account-mode passwords, proof tokens and private answers are never written
to localStorage or sessionStorage. Proof links use fragments, which the form reads
and immediately removes. Verification chooses the final password and requires a
subsequent sign-in. A confirmed password change keeps only its non-secret success
result through session-recovery retries; opening a new proof link clears that result.

Guests can explore published collections. A verified account can upload to its
private writable collection. Its owner can read every content label, download an
original even if processing failed, retry failed processing and delete files.
The public role selector remains a demonstration on published collections only.
The UI displays the API's remaining daily budget, including guest use retained
after sign-in, and its UTC reset. Usage separates today's settled spend, pending
reservations, remaining allowance and daily limit from the 30-day query totals.
Network users may share the IP allowance.

The `/v1/site` response supplies provider disclosures, actual upload size and an
optional operator contact. Uploads wait for this disclosure. Missing SMTP is
shown as unavailable registration/recovery; existing accounts can still sign in.
The UI does not simulate mail delivery or invent operator details.

`NEXT_PUBLIC_ACCOUNTS_ENABLED=false` preserves the legacy API-key/demo modes.
Run `npm --prefix ui run typecheck` and `npm --prefix ui run build` for validation.
Browser test instructions and their limits are in [tests/README.md](tests/README.md).
