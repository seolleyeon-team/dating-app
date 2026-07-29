# Avatar Production Decision Log

## D-001: One primary source per avatar submission

Decision: `avatar_state_v2` requires one local primary photo. The legacy two-photo
gate is removed from the avatar flow. The same source may feed recommendation
only with explicit consent; additional recommendation media is a separate future
contract.

Alternatives: retain two photos and add an atomic multi-image submission; upload
multiple CLIP sources before locking. Both add request-size, concurrency, consent,
and cleanup complexity without a current backend consumer contract.

Consequence: fixes the first-photo deadlock with the smallest privacy-preserving
state machine.

## D-002: Root Functions are canonical

Decision: root `functions/src` owns avatar callables. Festival copies cannot be
edited independently. Remove them, generate them, or enforce a contract/diff CI
gate before integration.

Evidence: root and festival avatar backend files have different hashes and line
counts while exposing the same callable names.

## D-003: Approved-only public display

Decision: public display requires approved status and a safe approved URL.
`onboarding.avatarUrls` is a backend-written mirror only, never an unapproved
fallback. `onboarding.photoUrls` is never displayed.

## D-004: Production bridge equals production safety

Decision: `production_bridge` receives the same preprocessing, real QA, model
outage, App Check, IAM, cost, and logging rules as production. Fixture-only
heuristic preview is forbidden there.

## D-005: App Check is a server gate

Decision: client activation is insufficient. Production-like avatar/media
callables enforce App Check server-side, with explicit internal test mechanisms
that cannot be enabled in public configuration.

## D-006: Critical QA uncertainty cannot preview

Decision: missing required model signals or low-confidence isolation yields
`needs_review` or safe failure. It cannot be converted into synthetic safety
signals. Soft pass is allowed only after all absolute safety signals pass.

## D-007: Consent is versioned and purpose-specific

Decision: source retention and recommendation extraction are not implicitly true.
The server records explicit versioned consent, and withdrawal/account deletion
invoke verified idempotent cleanup.

## D-008: Cost guard is shared by every execution path

Decision: direct Cloud Tasks, drain/batch, retry, and adaptive extra generation
call one cost policy before expensive work. Concurrency one is not a cumulative
spend control.

## D-009: Historical smoke is not current deployment evidence

Decision: May reports prove prior wiring only. On 2026-07-19 the read-only live
inventory returned zero festival Functions despite older deployment documents.
Release evidence must be revision- and time-bound.

## D-010: Public rollout is a separate human action

Decision: even if all implementation gates pass, allowlist removal, live Hosting,
or public rollout is not executed without explicit human authorization.
## Decision evidence and implementation matrix

| Decision | Evidence | Alternative and trade-off | Consequence and implementation instruction |
| --- | --- | --- | --- |
| D-001 | Mobile requires two photos but uploads and locks the first immediately; the backend/worker current contract processes one source. | Atomic multi-photo submission preserves two photos but adds request, consent, cleanup, and race complexity without a current consumer. | Make one local primary slot authoritative; upload only on Generate and reuse it for recommendation only after explicit consent. |
| D-002 | Root and festival callable files expose the same APIs but differ in hash and line count. | Manual duplication is quickest but drifts; a shared package is cleanest but larger. | Deploy one canonical root package first; add contract/diff CI before removing copies. |
| D-003 | Flutter and root backend resolve unapproved `onboarding.avatarUrls`; festival web is stricter. | Legacy fallback preserves old images but violates approved-only display. | Use a placeholder and backend migration report; update all resolvers and tests together. |
| D-004 | Worker classifies bridge as production-like while QA/preprocessing retain bridge exceptions. | Fixture exceptions improve smoke success but weaken safety equivalence. | Move fixture behavior to a non-production environment that cannot target festival data. |
| D-005 | Client App Check is active; inspected callables do not enforce it server-side. | Auth/allowlist-only rollout is simpler but leaves automated abuse exposure. | Add monitoring, verify tokens, then enforce under allowlist with rollback. |
| D-006 | Historical candidates were soft-passed with unavailable or synthetic signals. | Default unknown risk to low improves preview rate but hides uncertainty. | Centralize required signal availability and test every outage as review/no-preview. |
| D-007 | Upload defaults retention/recommendation consent true; explicit UI is only confirmed for chat disclosure. | Bundled consent is vague; immediate deletion breaks consented recommendation use. | Add purpose-specific UI and server validation; test withdrawal and repeated cleanup. |
| D-008 | Lease/drain use full cost evaluation; direct task execution checks pause flags only. | Per-path guards are simpler but permit sequential overspend and drift. | Extract one cost decision function and call it before every expensive entry point. |
| D-009 | Current live inventory reports zero festival Functions while May docs report deployments. | Trusting docs preserves history; trusting live state protects releases. | Preserve both, but regenerate live resource inventory before every release gate. |
| D-010 | The brief and all smoke reports keep public rollout false. | Automatic rollout is faster but cannot supply launch and incident judgment. | Tooling may prepare exact commands and rollback, but must stop before public mutation. |
