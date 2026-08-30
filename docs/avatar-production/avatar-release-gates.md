# Avatar Release Gates

Version: `avatar_release_gates_v2`

Current overall gate: `PASS_PARTIAL`. Public rollout: not executed.

## Flow gate

- no first-photo deadlock
- final Generate starts exactly one upload
- complete/partial source-state behavior passes concurrency tests
- same-source retry and authoritative recovery pass mobile and web E2E
- preview, approval, approved-only display and permanent lock pass

Current: fail.

## Privacy gate

- server Auth and App Check enforcement passes
- Firestore/Storage emulator tests deny private and server-owned state
- broad public relationship/security data grants are removed
- IAM/OIDC and bridge isolation are live-verified
- consent, retention, withdrawal and account deletion pass E2E cleanup
- client, bundle, reports and logs pass privacy scans

Current: fail.

## Quality gate

- real face/person/OCR/logo/background and identity signals are connected
- secondary face geometry reaches preprocessing without persistence
- trait extraction uses the neutralized analysis crop
- production-like heuristic-only preview is impossible
- critical model outage yields review
- realistic calibration produces nonzero hard passes and threshold evidence
- hard rejects never preview

Repository implementation/review: pass for G004. Evidence: 449 passed, 6
skipped implementation tests; focused 69 passed; independent review 85 passed;
`compileall` pass; privacy QA pass with 359 client files and all leak counters
zero; `git diff --check` clean except CRLF warnings; code review `APPROVE`;
architecture `CLEAR`.

Current production quality readiness: fail. `QUALITY_QA_PRODUCTION_READY=false`
because `QA-007` still requires a passing current-QA calibration run and human
signoff.

CURRENT AUTHORITY (2026-08-30, see `g004-calibration-plan.md` "Production
Readiness Gate: 5+ Current-QA Calibration Cohort" and cohort policy
`g004-5plus-v1` in `lib/ai_recommend_model/avatar_generation/artifacts/`):
one current-QA calibration run with at least 5 fresh exact-consent
participants, nonzero machine hard-pass, no hard reject, required signals
available, runtime/offline parity, complete human rubric, and human signoff.
Offline SAME-20 evidence exists (5 participants / 20 candidates: hardPass 8,
needsReview 12, hardReject 0, requiredSignalUnavailable 0 — see
`g004-full-qa-offline-20260828-v2.md`) but runtime parity and human signoff
remain open, so the gate stays `fail` (`humanSignoff=false`).

SUPERSEDED PLAN (historical, retained as history): the earlier mandatory
"10-20 cohort, then 50-100 holdout" sequence. Larger cohorts are now optional
follow-up unless an incident, material model change, threshold change, or an
explicit new decision reopens calibration.

Historical PR8.5 evidence had 8 participants, 32 soft passes, 0 hard passes,
trait coverage avg/p50/p95 0.3667/0.3333/0.4, total duration p50/p95
81.103/86.927 sec, cost p50/p95 USD 0.032011/USD 0.03431, one retry/deadline,
and payload p50/p95 100590/119022 bytes. It predates current real-QA wiring and
cannot prove current production quality.

## Operations gate

- deployed resources match versioned source and image digests
- single-task, drain, batch, retry and extra rounds share cost guards
- queue retry/deadline, lease recovery, monitoring, alerts and rollback pass
- current festival Functions/rules/App Check inventory is verified
- direct festival worker migration or approved temporary bridge plan is complete
- internal mobile and web canary passes with exact consent

Current: fail.

## Mandatory sequence

1. Targeted local tests
2. Full unit/integration and emulator tests
3. Privacy and built-bundle scans
4. Staging mobile/web smoke
5. Exact-consent internal bridge smoke
6. QA calibration gate
7. Security and cost gates
8. Rollback drill
9. Final code review: `APPROVE` and architecture `CLEAR`
10. Explicit human decision for any public rollout

Passing implementation gates does not remove allowlists, publish Hosting live,
or authorize public traffic.
## G005 checkpoint update

Repository implementation/review: partial pass for G005. Functions upload kill-switch ordering, unified worker admission, candidate/retry/deadline and cumulative cost guards, queue reconciliation, festival rule markers, versioned observability, sanitized release inventory, and plan-first rollback tooling are implemented. Functions tests passed 134; queue tests passed 25; the owned admission/worker/lease suite passed 88 before the final alias/deadline follow-up; the operations tool suite passed 63 before the final Windows process tree fix; that fix's focused release inventory suite passed 14. Final touched Python files compile and `git diff --check` is clean except line-ending warnings.

Current production operations readiness: fail. `PRODUCTION_OPERATIONS_READY=false` because festival Functions/direct worker and live monitoring/rollback/rules/App Check/Hosting evidence remain absent or unavailable. The final combined suite and independent review could not be re-run after the last follow-up because the execution service usage limit rejected the required sandbox escalation. No production/public mutation was performed.