# W10 bounded UI accessibility and reflow review

2026-09-10. Original local Docker UI: `http://127.0.0.1:18127`; corrected temporary
production build: `http://127.0.0.1:18129`; final rebuilt Docker UI rechecked at
`http://127.0.0.1:18127`. Next.js 15.5.25, Chromium, synthetic API
fixture shared with `ui/tests/browser-regressions.cjs`. All `/v1/` requests are
intercepted; third-party requests are blocked. No live API or AI provider was used.

## Reproduce

From the repository root, with a running keyless UI build:

```bash
DOCQA_UI_URL=http://127.0.0.1:18127 \
DOCQA_PLAYWRIGHT=/home/horten/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright \
DOCQA_CHROMIUM=/usr/bin/chromium \
node audit/ui-accessibility.cjs
```

`DOCQA_A11Y_OUT` overrides the artifact directory. The script exits nonzero on a
failed assertion, measured contrast/reflow check, or execution error. Original
RED script/results/screenshots are preserved in `ui-accessibility-red/`.

## Confirmed failures and corrections

| Case | Before | After |
|---|---|---|
| 160-character answer identifier | Page scroll width 1732 at viewport 320; 1992 at 1280 | Answer wraps within its card; page stays at viewport width |
| Long ordinary prose at 320 | Hidden absolute citation previews extend page to 345 | Preview is available where the desktop reading column has room; citation opens the existing source drawer at every width |
| Header with doubled text at 640 | Role select extends page to 678 | Select group wraps and stays within available width |
| Empty Ask title with doubled text at 320 | Heading clipped; page width 354 | Full heading wraps within available width |
| Composer placeholder | 2.959:1 on white | 5.399:1, full-opacity existing secondary-text color |
| Pending/processing, 12px | 3.505:1 on white | 5.275:1 with darker amber `#926216` |
| Partial confidence, 12px | 3.217:1 on paper | 4.842:1 with the same amber |

The corrected suite passes **42 layout/semantic checks, 16 contrast pairs, and
keyboard reachability on Ask/Library/Usage**, with no execution errors. The
existing keyless browser suite also passes **18/18**. Production build passed;
its existing metadataBase warning is outside this correction.

## Scope and limits

- Layout: 320/640/1280 CSS-pixel viewports, ordinary long prose, an unbroken
  identifier, long filename in Library and reader, focused citation preview,
  and injected 200% font-size/line-height stress on all three routes. Scrollable
  document tables remain local scroll containers, recorded separately.
- Keyboard: real Tab traversal and Enter route activation; `/` focus and Enter
  question submission; expected controls reachable by name. Existing regression
  suite separately covers source/reader focus restoration and delete retry.
- Semantics: browser accessibility snapshots, answer live-region text, delete
  alert and named retry, full long-filename name/title. No assistive technology
  was run, and announcement quality with a screen reader is not certified.
- Contrast: computed rendered foreground/background colors, alpha composition,
  sRGB relative luminance, 4.5:1 benchmark for the selected small text. Disabled
  controls are excluded. These are 16 measured pairs, not all possible states.
- A 640 CSS-pixel viewport represents layout space equivalent to a 1280-pixel
  viewport at 200% page zoom. Separately doubling text via injected inline styles
  is a stress test; it does not claim native browser text-zoom equivalence.
- Chromium only. No full WCAG, screen-reader, touch-target, high-contrast-mode,
  or cross-browser conformance claim is made.

Spec review: corrections address the observed approved W10 cases; no redesign,
metadata, API/auth behavior, package/configuration, or deployment change was made.
Quality review: reviewed the small source diff, production build and both suites;
visually inspected corrected 320px long answer and 320/640px doubled-text images.
No remaining blocking defect was found within this bounded scenario set.

Final-image recheck: the first run exposed a test readiness race before the
composer's passive shortcut listener was registered. Instrumented diagnosis
reproduced 2/12 missed immediate shortcuts. The test now observes a real
controlled-input response before one shortcut assertion; 20/20 synchronized
diagnostic runs and the complete 42/16/3 suite passed against final Docker18127.
See `ui-accessibility-focus-diagnosis.md` for timestamps and artifacts. No UI
source or image changed during that diagnosis.
