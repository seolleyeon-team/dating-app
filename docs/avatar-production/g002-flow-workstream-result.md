# G002 Flow Workstream Result

Date: 2026-07-19

## Gate decision

- G002 implementation status: `FLOW_IMPLEMENTATION_READY=true`
- G002 repository checkpoint: ready after independent architecture follow-up
- `FLOW_PRODUCTION_READY=false`
- Overall `production-ready=false`
- Public rollout: not authorized and not executed

G002 closes the local implementation and regression-test work for the mobile,
Festival web, and Functions avatar flow. It does not certify deployed resource
parity or live end-to-end behavior.

## G002 scope completed

- Generation starts only after explicit user action and immediately locks local
  source replacement while the upload result is unknown.
- Complete current source/job state locks replacement; partial state fails
  closed.
- Upload attempts require `clientRequestId` and
  `consentVersion=photo_consent_v3`.
- An uncertain retry may replay only when uid, current source/job, normalized
  image hash, request id, and consent version still match.
- Same-source retry accepts no new image or source identity fields and preserves
  the current source contract.
- Mobile and Festival web reconcile refresh, restart, and local recovery hints
  against authoritative backend status.
- Approved status or an approved URL-only legacy record is permanently locked;
  a missing display URL is repaired or refetched from backend authority rather
  than trusted from a local draft.
- Preview, approval, and public display paths remain free of source references,
  private bucket paths, and persisted signed URLs.
- Festival profile writes bind avatar display fields to the authoritative
  `users/{uid}.avatar.approvedAvatarUrl` value.

## Verification evidence

- Root Functions: `npm test` - 81 passed, 0 failed.
- Root Flutter source-lock flow: targeted suite - 40 passed, 0 failed.
- Root Flutter avatar/display regression suite - 47 passed, 0 failed.
- Root Flutter analysis: no issues.
- Festival Functions: `npm test` - 21 passed, 0 failed.
- Festival Flutter avatar/session/widget/model/display suite - 34 passed,
  0 failed.
- Festival Flutter analysis: no issues.
- Festival release web build: succeeded.
- Media privacy QA: `status=pass`; public and client leakage counts are zero.
- Client forbidden-marker searches: no private symbols, private bucket literals,
  signed URL markers, or raw biometric markers found.
- Changed-file UTF-8 and `git diff --check` validation: passed.
- Independent code review: `RECOMMENDATION: APPROVE` with no actionable finding.

## Explicit G006 handoff

The following are intentionally not part of the G002 repository checkpoint and
remain mandatory in `G006-cross-workstream-integration-and-int`:

- deploy or deployed-source parity checks in `seolleyeon-final`;
- exact-consent fresh UID/photo staging execution;
- live upload, worker processing, preview, approval, permanent lock, and
  same-source retry smoke;
- mobile restart and Festival browser refresh recovery against deployed
  callables;
- Festival bridge/internal Hosting smoke and network payload inspection;
- sanitized live timing, cost, QA, and security evidence.

G006 must not mutate the source project `seolleyeon`, must not perform public
rollout, and must stop if its exact-consent or project guard fails.

## Remaining decision boundary

Completing G002 means the flow implementation is ready for integration. It does
not set `FLOW_PRODUCTION_READY=true`. That flag can be considered only after the
G006 live gates pass and the final G007 `APPROVE` and `CLEAR` reviews accept the
combined system. Until then, allowlists remain in place and production-ready is
false.
