# Google sign-in

Google sign-in uses the existing private accounts and opaque browser cookies. It is enabled
when `ACCOUNTS_ENABLED=true` and both `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set on
the API server. Both empty disables Google; setting only one fails startup. SMTP is independent:
Google registration works without it, while password reset and email registration need mail.
The session endpoint exposes only `google_available`; no browser SDK, frontend client secret,
or extra application signing secret is needed.

## Operator setup

1. Create a **Web application** OAuth client in Google Cloud and configure its consent screen
   and permitted audience/test users. Request only `openid email`.
2. Add the exact authorized redirect URI:
   `https://api.docqa.net/v1/auth/google/callback`. Google requires this provider-side setting;
   server credentials cannot create it automatically. There is no JavaScript-origin requirement
   for this server authorization-code flow.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the private server environment. Keep the
   secret out of Git, UI build variables, diagnostics and browser code. Production Compose
   passes both keys to the API and preconfigures that exact callback URI. Run the normal
   migration/deployment process; migration `0012` adds only the two Google tables.
4. The production callback defaults correctly without a third required secret or option.
   On other deployments, set `GOOGLE_REDIRECT_URI` to their exact API callback and register
   that URI in Google Cloud too. HTTPS is required except localhost/127.0.0.1 HTTP for local
   development. The callback path must remain `/v1/auth/google/callback`; query/fragment and
   embedded credentials are rejected. The browser must support the existing Secure session
   cookie; use local HTTPS where necessary.
5. Verify with a real permitted Google account in the browser: sign in, inspect the private
   library, sign out and return. Local tests validate protocol/security cases with signed test
   tokens and PostgreSQL; they do not prove a real consent-screen configuration works.

## Browser/API contract

`POST /v1/auth/google/start` accepts `{"intent":"login"}` (default) or `{"intent":"link"}`.
It requires the existing account cookie, exact trusted `Origin`, and `X-CSRF-Token`; requests
use the account attempt limit. The response contains only `authorization_url`, always on
`https://accounts.google.com/o/oauth2/v2/auth`. Navigate the browser to it. There is no caller
supplied return URL.

`GET /v1/auth/google/callback` requires the same active browser session and an unused state
valid for ten minutes. It returns a 303 redirect to `AUTH_PUBLIC_URL`:

| Result | Path |
| --- | --- |
| Login | `/` |
| Explicit link | `/account?google=linked` |
| Disabled provider | `/account?google_error=unavailable` |
| Invalid state/provider/session/budget failure | `/account?google_error=failed` |
| Email already belongs to an account | `/account?google_error=email_exists` |
| Ineligible or conflicting explicit link | `/account?google_error=link_failed` |

For `email_exists`, sign in with email first, then choose **Connect Google**. Linking requires
that same active, verified account session and the same verified email from Google. A Google
subject cannot move between users, and an account cannot overwrite its existing Google link.
Returning users are found by Google's stable issuer/subject, so a changed Google email does
not move their account, change its stored email, or switch its tenant. To add a password to a
Google-created account later, use the normal email password-reset flow when mail is enabled.

## Security and operations

The database stores only a hash of random state, with its owning browser session, nonce and
PKCE verifier. State is atomically consumed and committed before token exchange; used nonce
and verifier material are cleared. Each new start deletes up to 1,000 expired states. There is
no provider network wait inside a database transaction. Callback handling verifies Google's
RS256 signature against a fixed HTTPS JWKS endpoint, exact issuer/audience, expiration, issued-at,
nonce, subject and a valid verified email. JWKS responses are size-bounded, cached for 30–3,600
seconds, and refreshed for unknown key IDs at most once per 30 seconds. Brief failures during
key rotation fail closed and can be retried by starting a fresh sign-in.

The API never stores or sends Google access/ID/refresh tokens to the browser. It requests no
Google API, profile or offline-access scopes. Requests use bounded HTTP timeouts and response
sizes, fixed Google endpoints and no redirects. Callback responses have `Cache-Control:
private, no-store` and `Referrer-Policy: no-referrer`; application request logging records paths
without callback query strings. Keep reverse-proxy access logging from recording auth query
parameters as well.

A new Google account receives one personal tenant, one **My documents** collection and a random
unknown Argon2 password hash. Account creation is committed before importing guest spending;
that prevents the separate ledger transaction waiting on its own uncommitted User foreign key.
Login imports existing guest reservations before rotating the cookie, using the existing
account/IP ledger. A pending $0.20 reservation leaves $0.30 available after sign-in and later
settlement updates both scopes without double charging. Provider or quota-storage failures
preserve the previous cookie. Session/account authority is rechecked after external network
work and after quota import so revocation during either wait cannot finish authentication.

Migration `0012` adds `google_identities` and `google_auth_states`. The existing schema-owner
runtime-grants script grants DML to these tables and default grants cover future migrations.
Full database dumps include both tables. Their foreign keys follow account/session deletion;
Google identity tables carry no provider bearer tokens. Disabling both credentials stops new
Google flows without deleting accounts, documents, spending records or existing browser sessions.

References: [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect)
and [PyJWT validation and RSA/JWK usage](https://pyjwt.readthedocs.io/en/stable/usage.html).
