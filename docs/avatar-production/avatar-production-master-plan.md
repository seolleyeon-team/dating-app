# Seolleyeon Avatar Production Completion Master Plan

Last updated: 2026-07-19 KST

## Scope and status

This control plane covers the privacy-preserving avatar flow from local source
selection through upload, generation, QA, preview, approval, public display, and
permanent lock. It also covers the temporary cross-project GPU bridge, but does
not authorize public rollout.

Baseline status: `PASS_PARTIAL`. Production implementation ready: false.
Public rollout executed: false.

This control-center execution changed only control-plane artifacts. The worktree
already contained unattributed implementation changes before G001; they were
inspected but not modified or reverted. No cloud resource, user data, or
production configuration was mutated.

## Confirmed topology

| Area | Confirmed current state |
| --- | --- |
| Mobile/backend/worker repo | `semisemifinal`, dirty user worktree |
| Festival web repo | separate `festival` worktree, also dirty |
| Staging/data projects | staging and bridge host are separate from festival data/control |
| Staging worker | ready revision `seolleyeon-avatar-worker-00045-p7g`, max 1, concurrency 1 |
| Festival bridge worker | ready revision `seolleyeon-avatar-worker-festival-00010-sq9`, max 1, concurrency 1 |
| Bridge public invocation | no `allUsers` or `allAuthenticatedUsers` binding observed |
| Festival queue | running, max concurrent dispatch 1, max attempts 3 |
| Festival avatar Functions | live read-only inventory returned zero on 2026-07-19; May smoke documents are stale evidence |
| Source project | protected; no mutation permitted |

The implementation already contains private source upload, current source/job
validation, worker generation, candidate preview filtering, approval, and
approved avatar locking. The current production blockers are recorded in
`.omx/avatar-production/issue-ledger.json`.

## Frozen ownership

| Owner | Files and responsibilities |
| --- | --- |
| FLOW | Flutter onboarding/profile flow; festival web avatar client/session; safe public display resolver |
| BACKEND FLOW | canonical root `functions/src/avatarMedia.ts`, `avatarApproval.ts`, callable exports and contract tests |
| PRIVACY | Firestore/Storage rules, App Check, retention/deletion, logging redaction, IAM and bridge boundaries |
| QUALITY QA | `lib/ai_recommend_model/avatar_generation/analysis`, preprocessing, trait card, FLUX adapter, QA/rerank |
| OPERATIONS | worker service, leases, cost guard, Cloud Tasks, deployment scripts, monitoring and rollback |
| RELEASE | controlled integration, full test matrix, exact-consent live smoke and final evidence |

Root `functions/src` is the canonical avatar backend. The festival Functions
copy must not evolve independently. It must be removed, generated from the
canonical source, or protected by a contract/diff CI gate before release.

## Dependency order

1. Freeze state, API, data, QA, error, metrics, and release contracts.
2. Repair flow against the frozen state/API contract.
3. Repair privacy and quality pipelines against the frozen data/QA contract.
4. Complete operations controls after retry, QA, and cost semantics are stable.
5. Integrate only reviewed workstream changes.
6. Run local, emulator, staging, bridge, consented canary, security, and cost gates.
7. Produce the final implementation decision. Public rollout remains a separate human action.

## Workstream completion criteria

### Flow

- One local primary photo can be selected, removed, or replaced before Generate.
- Generate performs one backend submission and immediately freezes the source.
- Partial current-source state fails closed.
- Same-source retry and authoritative refresh recovery work on mobile and web.
- Preview, approval, approved-only display, and permanent lock pass E2E.

### Privacy and security

- Auth and production App Check are server enforced.
- Private collections and storage are backend-only.
- Broad public Firestore grants are removed or explicitly isolated from release.
- Source retention and recommendation use require versioned consent.
- Consent withdrawal and account deletion invoke verified cleanup.
- Logs, reports, clients, and built bundles contain no forbidden private material.

### Quality and safety

- All detected face candidates reach preprocessing in memory without public persistence.
- OCR/logo/person/background actions reflect real pixel operations.
- Trait extraction uses a neutralized analysis crop and onboarding gender only.
- Production-like QA uses real required signals and fails to review on model outage.
- Hard rejects never preview; realistic calibration produces nonzero hard passes.

### Operations

- Every execution path uses the same kill switch, budget, retry, and candidate caps.
- Worker invocation, queue retries, deadlines, stale leases, and rollback are verified.
- Current revisions, image digests, rules, App Check, and alert resources are reproducible.
- The temporary bridge has a measured retirement and direct-worker migration plan.

## Live mutation gates

No deploy, IAM/rules change, fixture upload, approval, cleanup, or public Hosting
change is allowed until all of the following are true:

1. Explicit target project and account guard passes.
2. The exact change package and rollback are documented.
3. Local verification for that package passes.
4. Exact UID/photo consent exists for any real-person fixture.
5. The source project is excluded.
6. Public rollout and allowlist removal have separate explicit human approval.

## Evidence boundary

May 2026 smoke reports establish historical wiring evidence only. They do not
prove the current July revisions, Functions inventory, App Check, rules, model
signals, or production safety. Fresh evidence must name its revision, contract
version, cohort, and test command.

The completion report and `out/avatar-production-*-evidence.json` files are final
G007 deliverables. Creating them during G001 would falsely imply implementation,
test, privacy, QA, and cost completion evidence that does not yet exist.
