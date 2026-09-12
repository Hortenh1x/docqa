# Browser accounts and private documents

`ACCOUNTS_ENABLED=true` enables browser accounts. The browser sends requests with
`credentials: include`, obtains a session with `GET /v1/auth/session`, and sends the
returned `csrf_token` in `X-CSRF-Token` on every POST/DELETE. `Origin` must exactly
match `AUTH_ALLOWED_ORIGINS`; the API CORS list must also allow the UI origin.

The host-only `__Host-docqa_session` cookie is HttpOnly, Secure, SameSite=Lax and
has a finite lifetime. Only its SHA-256 hash is stored in PostgreSQL. Login rotates
the session and CSRF token. Logout revokes the session server-side. Invalid,
expired, disabled or revoked sessions return `401 invalid_session` and clear the
cookie; they never authorize that request as a guest or API-key request. The UI
can then explicitly obtain a new anonymous session and show sign-in.

## HTTP contract

All password payloads are JSON. Registration and login normalize email case. New
passwords need at least eight Unicode characters, a letter and a decimal digit.
There are no uppercase, special-character, diversity, email-similarity or breach-list
rules, and password checks make no external requests. Passwords remain hashed with
Argon2id. Registration, verification and reset require a matching
`password_confirmation`; a mismatch cannot consume an email proof or change credentials.
The UI checks both entries before sending; the server independently enforces equality.
Existing password logins are not retroactively subject to the new creation rules.

| Endpoint | Payload | Successful result |
| --- | --- | --- |
| `GET /v1/auth/session` | — | `{user, csrf_token, registration_available, google_available}` |
| `POST /v1/auth/register` | `{email, password, password_confirmation}` | 202 neutral `{message}`; creates private tenant and “My documents” collection |
| `POST /v1/auth/login` | `{email, password}` | 200 session result; rotates cookie and CSRF token |
| `POST /v1/auth/verify` | `{token, password, password_confirmation}` | 200 `{message}`; sets the mailbox owner's chosen final password, verifies email and revokes every earlier session and email link |
| `POST /v1/auth/resend` | `{email}` | 202 neutral `{message}` |
| `POST /v1/auth/forgot-password` | `{email}` | 202 neutral `{message}` |
| `POST /v1/auth/reset` | `{token, password, password_confirmation}` | 200 `{message}`; revokes all existing user sessions and verification/reset links |
| `POST /v1/auth/logout` | `{}` | 204; revokes session and deletes cookie |

`user` is either `null` or `{id, email, email_verified, tenant_id}`. When accounts
are disabled, the session endpoint returns `user: null`, `csrf_token: null` and
`registration_available: false`. Session responses and document/API responses use
`Cache-Control: private, no-store`.

Email links are `${AUTH_PUBLIC_URL}/account/verify#token=…` and
`${AUTH_PUBLIC_URL}/account/reset#token=…`. The UI reads and immediately removes the
fragment, then submits the token in the JSON body. Token fragments are not sent in
HTTP requests or referrers. Verification and reset tokens are random, stored only
as hashes, expire, and are single-use. Resending invalidates earlier matching links.

The verification page shows a **Choose your password** form. It requires an explicit
password and matching confirmation together with the email token. It applies the
same password rule as registration/reset. Registration alone cannot establish verified credentials:
someone else may have preregistered the address with a password they know. Completing
verification replaces that password, revokes every prior login session and invalidates
all outstanding verification/reset links under one account lock. Verification does not
sign in automatically; the UI shows success and asks the owner to sign in with the
chosen password. If the verification request used that user's earlier login session,
the response also clears its cookie. Anonymous proof-completion sessions remain valid
for the subsequent explicit login. Token operations lock the user before tokens and
recheck the token after acquiring the user lock, including its expiry.

Unknown and existing email addresses receive the same API response on registration
and recovery. Ineligible recovery addresses receive a neutral informational email,
so delivery failures do not distinguish registered addresses. Wrong credentials
return the same 401 for missing and existing users. Per-operation counters in
PostgreSQL limit attempts by address and email, survive application restarts and
fail closed when the attempt store is unavailable.

## Resource scope

Each account owns exactly one personal tenant. IDs supplied by clients never
establish ownership. `CollectionOut` adds `is_public`, `owned`, and `writable`.
Unverified accounts can inspect their collection, but writes require verified
email. Owners read every label in their private collection, including historical
labels outside the current demo role map. Public demo role switches continue to
work only on the published corpus.

Guest access requires `PUBLIC_TENANT_ID`, an active service tenant. Only explicitly
published collections in that tenant are visible. Publication requires read-only
mode at the database level. Migration 0009 leaves all existing tenants as service
tenants and all existing collections unpublished. Operators must select which
existing corpus to publish; `read_only` alone does not publish anything.

Private metadata, lists, originals, query sources, suggestions and ingest status
are scoped in SQL; a foreign owner gets 404. Account queries against public
collections retrieve from the collection tenant while retaining the account actor
for billing. Personal tenants never authenticate with API keys. The configured
public tenant's legacy API key resolves as a guest when accounts are enabled.
Other service keys preserve operator integration access; browser mutations using
service keys require account sign-in.

## Delivery configuration

Set `SMTP_HOST`, `SMTP_PORT` (default 587), `SMTP_FROM`, optional matching
`SMTP_USERNAME`/`SMTP_PASSWORD`, `SMTP_STARTTLS` (default true), and `SMTP_TIMEOUT_S`.
Production has an SMTP implementation behind `Mailer`; local capture exists only
in test fixtures. Missing SMTP configuration sets `registration_available=false`
and email-dependent endpoints return 503. No successful production delivery is
simulated. The delivery adapter does not log recipients, credentials or link tokens.


## Google sign-in

[Google configuration and HTTP contract](google-auth.md) describe the server-only
Client ID/Client Secret settings. `google_available` is a runtime flag, independent
of SMTP. The login/register screen offers Google only when configured; a verified
signed-in user can explicitly connect the matching Google account. Existing emails
are never silently merged. Google login uses the same private tenant, secure session
and guest-spend import as password login. No Google tokens enter frontend storage.
