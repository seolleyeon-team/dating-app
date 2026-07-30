# G006 Cross-Workstream Integration Result

Date: 2026-07-28

## Decision

- Repository integration: `PASS`
- Staging configuration deployment: `PASS_WITH_CLI_POSTCHECK_WARNING`
- Internal live avatar generation: `BLOCKED_BY_APP_CHECK`
- Overall G006 status: `PASS_PARTIAL`
- Production ready: false
- Public rollout: not authorized and not executed

The approved workstream changes are integrated in the root mobile app, Functions,
worker, rules, indexes, operations tooling, and privacy checks. The active account
and project now match `seolleyeon-final`. Storage Rules and Firestore indexes were
selectively deployed to staging. No Functions or production deployment occurred.

## Confirmed Integration Repairs

1. `TeamMeetingRequestService` now uses authenticated callables for backend-owned
   writes and maps backend errors to fixed safe messages.
2. Storage Rules recognize the festival approved-avatar bucket while preserving
   deny-by-default behavior for private source, temporary candidate, and chat-photo
   buckets.
3. The three participant-scoped team-meeting composite indexes are declared.
4. Profile edit is avatar display-only and cannot upload or remove avatar media.
5. `PushNotificationService` resolves Firebase clients lazily and safely exits when
   Firebase is unavailable in tests.
6. The root chat service no longer contains the legacy client system-message writer.
7. Runtime logs now fingerprint IDs/paths and summarize exceptions without raw
   identifiers, URLs, tokens, exception messages, or stack traces.
8. The app widget test uses an explicit Firebase-free test home while production
   continues to use the normal splash route.
9. Analyzer root exclusions prevent generated evidence, nested repositories, and
   Python environments from stalling Flutter analysis.

## Verification

| Matrix | Result |
| --- | --- |
| Functions TypeScript build | pass |
| Functions tests | 120/120 pass using Node no-isolation mode; default child isolation is sandbox-blocked |
| Python full suite | 539 passed, 6 skipped |
| Python compileall | pass |
| Dart analysis server | all `lib` and `test` files analyzed; zero compile errors after one missing import repair |
| Flutter full suite | prior run 93 pass, 7 fail; affected static tests were repaired, but final engine rerun is blocked by the active global Flutter SDK lock/sandbox native-tool spawn restriction |
| Privacy log scanner | zero findings using the exact test scanner logic |
| Privacy QA | pass; 238 files, every leakage counter zero |
| Diff hygiene | pass; line-ending warnings only |

The remaining Flutter rerun blocker is environmental, not a source parse error. Two
stale `flutter.bat` invocations are spinning on the SDK lock held outside this task.
The IDE Dart processes were not terminated. A direct analysis-server run verified
that the current Dart source has no compile errors.

## Staging Evidence

- Account: `seolleyeon.official@gmail.com`
- gcloud project: `seolleyeon-final`
- Firebase active project: `seolleyeon-final`
- Worker revision: `seolleyeon-avatar-worker-00047-9qx`
- Exact consent: 10/10 matched, missing 0, unexpected 0
- Current small-face preflight: 7/10 eligible, 3/10 independently blocked for low quality
- Storage Rules: compiled and released to `seolleyeon-final`
- Firestore indexes: deployed to the default staging database
- Deploy CLI: printed `Deploy complete`; process exit was nonzero only because the
  local Firebase credential/update-check store is not writable and reauthentication
  warning was emitted after deployment
- Live avatar uploads in this gate: 0
- Live blocker: callable App Check token exchange/admin path remains 403; no bypass
  was used

## Contract Result

- Mobile keeps the source locked after generation starts and polls only the
  authoritative current job.
- Same-source retry accepts no replacement image bytes.
- Functions enforce Auth/App Check, source/job/version, approved lock, and sanitized
  responses.
- Worker revision 00047 keeps full-range face detection, overlapping tile fallback,
  primary-face selection, expanded crop, crop FaceLandmarker, privacy preprocessing,
  and hard-reject exclusion.
- Public display remains approved-avatar only; chat real-photo delivery remains a
  separate backend-authorized flow.
- No private source refs, private bucket paths, signed URLs, raw landmarks, or raw
  embeddings were added to client or evidence output.

## Remaining Blockers

1. Resolve staging App Check 403 through an authorized debug/device attestation path.
2. Stop the stale global Flutter SDK lock holder outside this task and rerun the full
   Flutter suite plus web debug build.
3. Run the 7 eligible exact-consented staging rows through upload, worker, preview,
   approval, and approved-lock retest.
4. Keep the existing operations blockers: nine legacy retryables, no bound alert
   notification channel, worker p95 latency above target, and temporary bridge.

Production ready remains false.