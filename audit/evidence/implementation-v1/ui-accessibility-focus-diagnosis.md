# Final Docker keyboard readiness diagnosis

The initial final-image run stopped at the `/` shortcut assertion, before layout
checks. Its JSON/log are preserved as `ui-accessibility-navigation-failure-*`.

Instrumentation on the same final Docker UI (`http://127.0.0.1:18127`) recorded
pathname, active element, textarea visibility/connection/disabled state, keydown
events, and listener registration. The original navigation sequence reproduced
the issue in **2/12** runs. Both failures had path `/`, focus on the Ask navigation
link, and a visible, connected, enabled textarea. The shortcut handler was added
after the key event:

| Run | Slash event | Keydown listener added | Difference |
|---|---:|---:|---:|
| 9 | 357.6 ms | 366.2 ms | 8.6 ms |
| 12 | 345.7 ms | 353.3 ms | 7.6 ms |

Two animation frames after the missed event, focus was still on the navigation
link. This excludes a disabled textarea or a later focus steal in these runs.
The visibility wait returned before the component's passive effect completed.

The audit test now fills the controlled textarea, waits for the matching enabled
Ask button response, clears the text, focuses the Ask navigation link, and sends
**one** `/` event. It does not retry the shortcut or add a fixed sleep. Thus the
assertion concerns the interactive route, not the first milliseconds before its
listener exists. No UI source or Docker image was changed.

**Results:** 20/20 synchronized instrumented runs focused the textarea immediately
and retained focus after two frames. The full final-Docker audit passed 42 checks,
16 contrast pairs, and 3 keyboard routes, with no failures or execution errors.
The final results also include `keyboardReadiness` snapshots before readiness,
before slash, and after slash.

Artifacts:

- `ui-accessibility-focus-diagnosis.cjs`: reproducible instrumentation, same local
  synthetic fixture as the main suite; no live API/provider requests.
- `ui-accessibility-focus-diagnosis.json`: original 12-run trace.
- `ui-accessibility-focus-synchronized.json`: 20-run synchronized trace.
- `ui-accessibility-results.json` and `ui-accessibility-run.log`: full final-image
  GREEN after the test synchronization change.

Use the same DOCQA_UI_URL, DOCQA_PLAYWRIGHT and DOCQA_CHROMIUM environment variables
as the main suite. For the synchronized diagnosis add `DOCQA_FOCUS_SYNC=true`
and `DOCQA_FOCUS_RUNS=20`. Omit DOCQA_FOCUS_SYNC to exercise the original sequence.
