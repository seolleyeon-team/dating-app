# Chat Real Photo P1 Final Handoff

## Summary

P1 prepares staging infrastructure for backend-authorized chat-only real profile photo visibility.

The feature policy remains:

- public/recommendation/pre-chat surfaces use approved avatar only
- active chat participants may receive real photo access only after backend auth
- no signed URL is stored in Firestore
- no private bucket path is exposed to Flutter

## Added Readiness Artifacts

- `scripts/p1_chat_real_photo_common.sh`
- `scripts/p1_check_chat_profile_bucket.sh`
- `scripts/p1_apply_chat_profile_bucket_staging.sh`
- `scripts/p1_verify_chat_profile_bucket_iam.sh`
- `scripts/p1_check_functions_deploy_readiness.sh`
- `scripts/p1_deploy_chat_real_photo_functions_staging.sh`
- `scripts/p1_verify_get_chat_real_profile_photo_callable.sh`
- `scripts/p1_rules_diff_check.sh`
- `scripts/p1_deploy_rules_staging.sh`
- `scripts/p1_chat_real_photo_staging_matrix.py`
- `docs/chat-real-photo-p1-deployment-runbook.md`
- `docs/chat-real-photo-p1-permission-matrix.md`
- `docs/chat-real-photo-p1-staging-verification.md`
- `docs/chat-real-photo-p1-rules-deploy-checklist.md`
- `docs/chat-real-photo-p1-rollback.md`
- `docs/chat-real-photo-p1-monitoring-checklist.md`

## Current Readiness Classification

- Local deploy readiness scripts: ready
- Live staging verification: blocked until a staging project is selected and bucket/function/rules are applied
- Production readiness: not claimed

## Verification Snapshot

- Firebase alias currently points to `seolleyeon`.
- `gcloud config get-value project` returned `seolleyeon`.
- `seolleyeon` is treated as production-like by P1 scripts.
- `gs://seolleyeon-chat-profile-photos` was not found in the current project.
- `uploadAvatarSourcePhoto` is deployed and active in the current project.
- `getChatRealProfilePhoto` was not found in the current deployed Functions list.
- `.venv` privacy QA passed with zero leakage counts.
- Flutter targeted tests passed.
- Functions build/tests passed.
- Review blocker fix: Firebase deploy scripts refuse `GCP_PROJECT != FIREBASE_PROJECT`.
- Review blocker fix: bucket update/IAM scripts verify bucket `projectNumber` before mutation.
- Review blocker fix: staging matrix deny cases require explicit Firebase denial statuses.
- Review blocker fix: staging matrix validates against `CHAT_PROFILE_PHOTO_BUCKET` and rejects source-bucket signed URLs.
- Review blocker fix: IAM verifier checks for direct project-level owner/editor/storage.admin overgrants on the runtime service account.

## Required Live Sequence

1. Set staging env vars.
2. Run bucket check/apply/verify.
3. Run rules diff and deploy.
4. Run functions readiness and selective deploy.
5. Prepare A/B/C staging users and safe fixture media.
6. Run staging matrix.
7. Run privacy QA and device checks.

## Non-goals

- No production data mutation
- No real user photo exposure in public docs
- No recommendation/avatar policy weakening
- No broad IAM grants by default
