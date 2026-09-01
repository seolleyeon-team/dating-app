# Kakao Friend Pairs — Coordinated Deploy Runbook & Release-Gate Status

Date: 2026-09-01. Branch `integration/local-consolidation-20260831` @ `246f29e3` (uncommitted working tree).
Companion to `kakao-friend-pairs-contract.md`, `kakao-friend-pairs-rollout.md`, `kakao-policy-inquiry.md`.
NOTHING in this runbook has been executed against any live project. No deploy/commit/push performed.

## 0. Environment reality (verified 2026-09-01)

- **There is NO isolated staging backend.** One Firebase/GCP project (`seolleyeon-final`) serves
  production AND the staging client flavor (`com.yonsei.dating`); separation is per-flavor Firestore
  docs (`appCompatibilityConfig/{production|staging}`), not per-project (docs/security/sec04-bridge-cutover.md).
  `docs/staging-bootstrap/*` describes an obsolete inverted topology — do not follow it.
  ⚠ `scripts/staging_*.sh --apply` deploys to production while logging `[staging]` — do not use for this rollout.
- Deploying Functions/Rules/recsys "to staging" IS a production-backend mutation. Therefore a
  "staging deploy" that satisfies GATE D/G without touching production is impossible today.
- CI has no deploy jobs; all deployment is manual from a workstation with Firebase CLI auth.
- Kakao: single Kakao app / native key shared by both flavors; `com.yonsei.dating` platform
  registration and `friends` scope approval are NOT evidenced in the repo.
- App Check: staging Android app `1:810450765203:android:81ca13cb23027d875c9466` exists in
  `google-services.json` but its App Check registration/debug-token allowlisting is undocumented.

## 1. Release-gate status (as of this run)

| Gate | Status |
|---|---|
| A. Kakao friend-pair storage policy approval | **BLOCKED** — `KAKAO_POLICY_EXTERNAL_APPROVAL_BLOCKED`; inquiry text ready (`kakao-policy-inquiry.md`); intake dir `docs/auth-rearchitecture/artifacts/` reserved |
| B. Collision-safe pairId | **PASS** — sha256 canonical id, dual-format legacy matching, 10k-collision test, dry-run counters |
| C. Toggle partial-failure safety | **PASS** — ON commits preference last / OFF first, generation CAS, fault-injection (700 pairs, fail@300, retry-converge) |
| D. Real Kakao A/B staging E2E | **BLOCKED** — requires deploy (see gate G) + Kakao staging-package registration + friends-scope approval + real A/B Kakao test accounts (none documented) |
| E. Mixed old/new rollout compatibility | **PASS (code)** — legacy ON-sync failure now reverts the preference (no under-exclusion window); ON-mode never sweeps stale pairs (test-pinned) |
| F. Full regression after final edits | see final report (fresh run) |
| G. Staging post-deploy smoke | **BLOCKED** — no isolated staging backend; deploying = production mutation while GATE A is blocked (§38 deployment-target ambiguity) |
| Production | **NO-GO** while A/D/G blocked |

## 2. Unblock prerequisites (external/human actions)

1. **Kakao written policy approval** — send `kakao-policy-inquiry.md` text; archive the reply under
   `docs/auth-rearchitecture/artifacts/`; verify wording matches implementation; flip gate A.
2. **Decide the staging strategy** (pick one):
   a. Create a real `seolleyeon-staging` Firebase/GCP project (opus5 audit recommendation).
      Cost note (GCP 비용 최소화 원칙): Functions+Firestore free-tier scale for test traffic is ~0원,
      but recsys Cloud Run jobs/Scheduler duplication is billable — recommend deploying only
      Functions+Rules to staging and skipping the recsys stack there (serving-side exclusion is
      client+callable; batch defense-in-depth can be validated by emulator/unit tests).
   b. Accept flavor-level staging on the production backend: then GATE G merges into the production
      deploy itself and the rollout must be treated as production from step one (requires gate A first).
3. **Kakao console**: register `com.yonsei.dating` + debug keyhash on the Kakao app; confirm
   `friends` scope (검수) approval status for the app.
4. **App Check console**: register the staging Android app + allowlist the test device debug token
   (per docs/staging_app_check_setup.md pattern, applied to the staging app id).
5. **Real A/B Kakao test accounts**: two real Kakao accounts that are mutual friends, on devices,
   plus two Yonsei-deliverable test mailboxes (email-link flow needs a real inbox; the documented
   `.local` synthetic users cannot receive mail — decide test mailbox strategy).
6. **Capture rollback targets** (required before ANY deploy): current live Functions revision names,
   Firestore rules release timestamp/ID (console), hosting release, storage rules version →
   record in `docs/release/kakao-friend-pairs-predeploy-snapshot.md`.

## 3. Coordinated deploy order (when gates open)

Follow the repo-sanctioned commands (opus5 13-deployment-and-rollback.md; chat-real-photo-p1 runbook pattern):

0. Preflight: `firebase use` + `gcloud config get-value project` printed and confirmed; fresh
   `git diff`, full test matrix green; `node scripts/kakao_friend_pairs_migration_dryrun.mjs`
   (READ-ONLY) → expect `friendPairDocs=0`, `oldFormatPairDocs=0`, record `legacyExclusionDocs`,
   `usersRequiringSnapshot`.
1. `cd functions && npm ci && npm run build` → `firebase deploy --only functions --project seolleyeon-final`
   (selective `--only functions:createKakaoFriendPairsOnce,functions:setKakaoFriendAvoidanceEnabled,...`
   possible; include the modified legacy sync + recommendationRefresh + primaryEmailAuth exports).
   Secrets already provisioned (RESEND_API_KEY/PORTONE_API_SECRET); no new secrets required.
2. Firestore indexes (none new required — verify), then
   `firebase deploy --only firestore:rules --project seolleyeon-final` → 10-minute smoke checklist.
3. `firebase deploy --only storage --project seolleyeon-final` (no changes this rollout — skip unless drifted).
4. Hosting (`public/auth-email-link.html` primary-token branch): `firebase deploy --only hosting --project seolleyeon-final`.
5. recsys: `infra/deploy.sh` (targets seolleyeon-final; NOT idempotent-casual — review IAM/API steps;
   only the container images changed via the python privacy-predicate narrowing).
6. Client release train: staging-flavor build first for smoke, then production flavor per store process.
7. Post-deploy smoke (§35 of the task spec) + observability counters (§36; privacy-safe only).

## 4. Rollback

Per opus5 13-deployment-and-rollback.md: rules rollback is CONSOLE-ONLY (release history) — hence
prerequisite 2.6 above. Functions: revert + redeploy or console traffic shift. Pair documents are
materialized data — never bulk-deleted on rollback. Legacy sync endpoints remain deployed, so a
client rollback alone restores the previous behavior end-to-end.
