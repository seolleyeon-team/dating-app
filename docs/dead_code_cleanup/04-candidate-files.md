# Candidate files and deletion gate

## Current decision

`SAFE_TO_REMOVE_CONFIRMED = 0`.

Possible candidates were identified as groups, but no individual file has passed the mandatory deletion gate. The candidate groups together contain far more than 30 possible paths, so the master prompt requires explicit user approval before any deletion. Approval is not requested for the audit documents or backup artifacts; it is required for source/artifact removal.

## Candidate groups

| Group | Approximate scope | Why it looks suspicious | Why it is retained now |
|---|---:|---|---|
| `tmp/**` | 5,975 tracked paths | Temporary/report/build-like names and generated output | Contains operational reports, fixtures, scripts, and possible denied/dynamic consumers; no bulk deletion |
| `.tmp/**` | 810 tracked paths | Temporary-looking directory | Same as above; ownership and recovery use are unproven |
| `festival_web/**` | 9,869 tracked paths | Separate large project may be mistaken for duplicate app | It is first-party-looking with source, tests, scripts, assets, and AI model code; no deletion |
| Generated-like extensions (`.linked`, `.unlinked2`, `.digest`, related) | Included in inventory artifact classification | Often regenerated or cache-like | Some are tracked and may be required by tooling/release/repair; source and consumer audit required |
| `seolleyeon-initial/**`, `seolleyeon-iniitial/**` | Separate/duplicate-looking areas | Similar names suggest old prototypes | Ownership, references, and user intent are not proven; preserve |
| `설레연 프론트 ui 디자인/**` | 57 tracked paths | Design asset directory may look unused | User-provided design assets; asset and product-owner audit required |
| stale workflow paths | 4 absent paths | Diagram labels no longer resolve | Already absent; history/route evidence says intentional replacement or rename, not current deletions |

## Required twelve checks for each candidate

An individual path can only be marked `SAFE_TO_REMOVE_CONFIRMED` after all checks are recorded with evidence:

1. Dart/static import, export, part, symbol, and package reference is zero or safely replaced.
2. String/class/JSON/Firestore collection/function/notification/feature-flag references are zero or safely replaced.
3. Route, route argument, legacy alias, deep-link, email-link, and notification-tap references are zero or safely replaced.
4. Flutter background entry point, `@pragma`, isolate, plugin callback, and web bootstrap references are zero or safely replaced.
5. DI/provider/service locator/controller registration and reflective/annotation references are zero or safely replaced.
6. Firebase Functions export, callable, trigger, Storage/Firestore trigger, Cloud Task, Scheduler, Pub/Sub, and Workflow references are zero or safely replaced.
7. Android/iOS/web registration, MethodChannel, manifest, Info.plist, entitlements, URL scheme, service worker, and build references are zero or safely replaced.
8. Asset, font, audio, Lottie/Rive/JSON, generated resource, and dynamic asset-path references are zero or safely replaced.
9. Tests, fixtures, golden files, emulator rules tests, CI checks, and operational validation references are zero or safely replaced.
10. Workflow labels, current user-flow map, runtime feature manifest, and compatibility aliases do not protect the path.
11. Git history, rename/replacement history, staged/uncommitted WIP, and external ownership have been reviewed.
12. Two independent reviewers agree, a restore target is recorded, and the pre/post gate plan is approved.

## Current candidate disposition

- No candidate currently has all 12 checks.
- No candidate has two independent reviewer approvals.
- No deletion batch was started.
- The four missing workflow paths are not candidate files because they are absent from the working tree.
- The active typo-named `random_mathcing_screen.dart` is explicitly protected and is not a candidate.
- The audit script and docs are retained as reproducible audit artifacts.


## Phase 2 exact-file disposition — 2026-08-04

The user-approved Phase 2 scope narrowed the 45-path pytest_tmp_avatar_qa_escalated/** group to an exact ten-file batch. Reviewer B independently inspected every path and approved only the ten *current pointer files; no wildcard deletion was used. The 34 PNG files and one ttl_report.json remain KEEP_UNCERTAIN/deferred because their exact historical generator bytes and report role were not sufficiently proven.

Batch 001 is therefore the first SAFE_TO_REMOVE_CONFIRMED set. Its exact paths and hashes are in 11-exact-file-review-matrix.md; its deletion and post-gate results are in 07-test-build-comparison.md and 08-removed-files-manifest.md.