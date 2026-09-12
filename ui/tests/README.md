# Local browser regressions

`about-regressions.cjs` checks the public About page and its source/license downloads
at 320px and 1280px, including an API outage, keyboard footer navigation and disabled
JavaScript. Run against a prepared production UI from `docs/source-releases.md`, in
each accounts/demo/keyless build mode:

```bash
DOCQA_UI_URL=http://127.0.0.1:18326 DOCQA_CHROMIUM=/usr/bin/chromium \
  node ui/tests/about-regressions.cjs
```

`browser-regressions.cjs` exercises the production UI with synthetic API responses.
It intercepts every `/v1/` request and blocks third-party requests, so it does not
use a backend, paid provider, real tenant, or live endpoint. The UI URL must be local.

Build and serve a keyless UI (use a temporary copy if a dev server is running):

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:18123 \
  NEXT_PUBLIC_DEMO_MODE=false NEXT_PUBLIC_DEMO_API_KEY='' npm --prefix ui run build
node ui/node_modules/next/dist/bin/next start ui -H 127.0.0.1 -p 18124
```

From a separate terminal:

```bash
DOCQA_PLAYWRIGHT=/path/to/node_modules/playwright \
  DOCQA_CHROMIUM=/usr/bin/chromium \
  DOCQA_UI_URL=http://127.0.0.1:18124 \
  node ui/tests/browser-regressions.cjs
```

`DOCQA_PLAYWRIGHT` (alias `PLAYWRIGHT_MODULE`) can be omitted if Playwright is
already resolvable by Node. `DOCQA_CHROMIUM` (alias
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`) can be omitted to use Playwright's bundled
Chromium, installed with `npx playwright install chromium` in CI.
The script prints each check and a JSON summary, and exits nonzero on failure.
`DOCQA_TEST_FILTER` optionally limits checks by a regular expression.

Repeat with a separate demo build using `NEXT_PUBLIC_DEMO_MODE=true` and
`NEXT_PUBLIC_DEMO_API_KEY=synthetic-demo-key`; run the tests with `DOCQA_DEMO=true`.
This checks baked-in demo authentication, same-day answer restoration, expiry of
previous-day and undated legacy answers, and the 5 MB hint.
The keyless run checks the 25 MB hint, key lifetime, tenant cache/storage reset, and
aborted fetch/SSE/upload requests. Both runs check reader/source focus with keyboard,
close button and backdrop at phone/desktop widths; literal file markup; stale text
after role changes; pending/processing/failed reader responses; delete confirmation,
cancellation, visible errors and retry; and server upload-size errors.
Both runs also move the browser clock across UTC midnight and verify that the saved
exchange expires on a timer, visibility change, or the next interaction.

These are Chromium browser regressions with mocked API responses, not live-provider
end-to-end tests or a complete screen-reader/browser compatibility audit.

The additional W10 regression suite uses the same synthetic fixture and a keyless
UI build. Run it from the repository root:

```bash
DOCQA_UI_URL=http://127.0.0.1:18124 \
  DOCQA_PLAYWRIGHT=/path/to/node_modules/playwright DOCQA_CHROMIUM=/usr/bin/chromium \
  node audit/ui-accessibility.cjs
```

It checks Tab reachability on all three routes, accessible names/live messages,
long prose and unbroken answers, long filenames, 320/640/1280 CSS-pixel layouts,
injected 200% text resizing, and 16 rendered small-text contrast pairs against
4.5:1. It writes JSON, accessibility snapshots, and screenshots under
`audit/evidence/implementation-v1` (override with `DOCQA_A11Y_OUT`) and exits
nonzero on a failed check. The JSON describes the measurement method and limits;
the text-resize stress test does not claim native browser zoom or WCAG conformance.

The account suite uses a separate production build. It keeps every API response
local, sends no mail, and invokes no AI providers:

```bash
NEXT_PUBLIC_ACCOUNTS_ENABLED=true NEXT_PUBLIC_DEMO_API_KEY='' \
  NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:18125 NEXT_PUBLIC_DEMO_MODE=true \
  npm --prefix ui run build
node ui/node_modules/next/dist/bin/next start ui -H 127.0.0.1 -p 18126
DOCQA_UI_URL=http://127.0.0.1:18126 DOCQA_CHROMIUM=/usr/bin/chromium \
  node ui/tests/account-regressions.cjs
```

The account suite covers registration, verification with a final chosen password,
recovery, fragment removal, unavailable mail, unverified writes, public versus
private collections, guest-to-account budget continuity, HTTP/SSE quota errors,
failed-original reading and retry, XHR/file/SSE credentials, cross-tab logout and
request abortion, stale-state clearing during session refresh, expiry recovery,
mobile layout, source/form keyboard focus, proof/password retention across unchanged
session checks, confirmed reset success through revoked-cookie recovery and network
retries, fresh proof links after completion, and separate daily settled/pending/remaining
budget amounts. It observes browser request options
and CSRF headers; cookie generation, Secure/SameSite enforcement, revocation and
actual mail delivery belong to backend/integration tests. Synthetic provider and
contact names are fixture data only.

Set `NEXT_PUBLIC_ACCOUNTS_ENABLED=false` explicitly for the legacy keyless/demo
builds above. Account builds reject a nonempty `NEXT_PUBLIC_DEMO_API_KEY` while loading the build
configuration to prevent accidentally publishing an operator credential. Keep all
three build variants separate; rebuilding a directory used by a running Next.js
server replaces its assets.
