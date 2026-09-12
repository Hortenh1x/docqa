# Independent reviews — implementation v2

Reviews were read-only. Implementers addressed findings in the shared uncommitted
working tree; no review authorized a commit or deployment.

| Scope | Result | Findings and resolution |
|---|---|---|
| Accounts specification and quality | PASS | Email proof sets the final password, revokes prior sessions/links and prevents preregistration takeover. Credential/token locking checked. Auth throttling moved to an independent short engine to avoid request-pool exhaustion. |
| Billing and worker integration | PASS | Guest/account reservations share immutable associations; pending transfers settle once. Login/account-disabled bypass, anonymous replay scope, deletion-triggered payer and stale suggestion revision findings fixed and regression tested. |
| Storage/deployment specification and quality | PASS after fixes | Durable staging ancestors, artifact/manifest/directory fsync before backup publication, source==destination preservation. Final integration review additionally reproduced failed-ancestor-fsync retry; both helpers now resync existing ancestors, with independent25-test confirmation. |
| AI prompt/context/fixture/evaluation | PASS | Original trimmed context is captured and judged directly; section-level finance visibility remains closed;40/18,000 defaults match the tested regression. Reviewer explicitly confirms bounded7/7 answerable correctness,8/8 generated faithfulness,2/3 hard refusals and no numeric leak in the third.20 offline tests independently passed. |
| UI specification | PASS after fixes | Both verify/reset forms retain in-memory proof across same-session visibility/BFCache refresh; changed/invalid identity clears it. Daily Usage distinguishes settled/reserved/remaining/limit/reset.16 tests independently passed. |
| UI final quality | PASS after fixes | Confirmed proof outcome is explicit non-secret action state outside the cleared session tree. It survives expected401 and a failed guest-bootstrap retry; a new proof fragment clears the old result.19/19 full production browser tests; reviewer independently reran9 privacy/recovery/Usage scenarios plus typecheck/diff checks. No remaining actionable findings. |
| Final backend integration | PASS | Ownership, usage attribution, saved upload/retry payer, suggestion payer+revision, wipe exclusions and durability retry reviewed together.25 focused tests independently passed. |

External SMTP delivery, actual private/versioned S3, independently hosted synchronous
standby and encrypted off-host backup remain unverified. Local same-host rehearsals
do not establish physical failure-domain independence. Backend and browser fixtures
are complementary checks, not proof of a deployed end-to-end account flow.
