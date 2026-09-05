> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](avatar-production/CURRENT_ARCHITECTURE.md).
>

# Chat Real Photo P1 Deployment Runbook

This runbook prepares staging infrastructure for chat-only real profile photo visibility.
It does not change the public/recommendation avatar-only policy.

## Scope

- Callable: `getChatRealProfilePhoto`
- Upload callable: `uploadAvatarSourcePhoto`
- Chat profile bucket: `seolleyeon-chat-profile-photos`
- Source bucket: `seolleyeon-private-source-photos`
- Rules: `firestore.rules`, `storage.rules`

## Required Environment

Set these in the shell before live staging operations:

```sh
export GCP_PROJECT="<staging-project>"
export FIREBASE_PROJECT="<staging-project>"
export GCP_LOCATION="asia-northeast3"
export FUNCTIONS_REGION="asia-northeast3"
export FUNCTIONS_RUNTIME_SERVICE_ACCOUNT="<runtime-sa>@<project>.iam.gserviceaccount.com"
export CHAT_PROFILE_PHOTO_BUCKET="seolleyeon-chat-profile-photos"
export SOURCE_PHOTO_BUCKET="seolleyeon-private-source-photos"
export APPROVED_AVATAR_BUCKET="seolleyeon-approved-avatars"
export AVATAR_TEMP_BUCKET="seolleyeon-avatar-temp"
export CHAT_REAL_PHOTO_CALLABLE="getChatRealProfilePhoto"
export USE_CHAT_PROFILE_SIGNED_URL="true"
export CHAT_REAL_PHOTO_SIGNED_URL_TTL_SECONDS="300"
```

The scripts refuse mutation on production-like project names unless `ALLOW_PRODUCTION=true` is set after explicit approval.
For Firebase deploy scripts, `FIREBASE_PROJECT` must match `GCP_PROJECT`; cross-project deploys are refused.
For existing GCS buckets, scripts verify the bucket `projectNumber` before update or IAM mutation.
Use an environment-specific bucket name for a true staging/prod split when possible. If a global bucket name is already owned by another project, the scripts must not update it.

## Preflight

```sh
firebase use
gcloud config get-value project
npm --prefix functions run build
npm --prefix functions test
flutter analyze
python scripts/qa_media_privacy.py --dry_run --fail_on_warning
python scripts/migrate_chat_real_photo_visibility.py --dry_run
```

## Bucket Preparation

Dry-run/check:

```sh
bash scripts/p1_check_chat_profile_bucket.sh
bash scripts/p1_verify_chat_profile_bucket_iam.sh
```

Apply in staging only:

```sh
bash scripts/p1_apply_chat_profile_bucket_staging.sh --apply
```

If signed URL generation fails with `signBlob` permission errors in staging, grant Token Creator only on the runtime service account resource:

```sh
GRANT_SIGN_BLOB=true bash scripts/p1_apply_chat_profile_bucket_staging.sh --apply
```

## Rules

```sh
bash scripts/p1_rules_diff_check.sh
bash scripts/p1_deploy_rules_staging.sh --apply
```

Wait for rules propagation before running live device/callable checks.

## Functions

```sh
bash scripts/p1_check_functions_deploy_readiness.sh
bash scripts/p1_deploy_chat_real_photo_functions_staging.sh --apply
bash scripts/p1_verify_get_chat_real_profile_photo_callable.sh
```

The deploy script is selective and targets:

- `functions:getChatRealProfilePhoto`
- `functions:uploadAvatarSourcePhoto`
- optional `functions:$CHAT_REAL_PHOTO_CLEANUP_FUNCTION`

## Staging Matrix

Provide Firebase Auth ID tokens as environment variables. Do not write tokens to files or commit logs.

```sh
export STAGING_USER_A_UID="..."
export STAGING_USER_B_UID="..."
export STAGING_USER_C_UID="..."
export STAGING_USER_A_ID_TOKEN="..."
export STAGING_USER_C_ID_TOKEN="..."
export STAGING_CHAT_ROOM_ID="..."
export STAGING_CHAT_ROOM_ID_CONSENT_TRUE="$STAGING_CHAT_ROOM_ID"
export STAGING_USER_B_UID_CONSENT_TRUE="$STAGING_USER_B_UID"

python scripts/p1_chat_real_photo_staging_matrix.py --live
```

The matrix script redacts returned signed URLs, requires explicit Firebase auth denial codes for deny cases, checks signed URL TTL shape, and never mutates Firestore.

## Current Local Observation

During local readiness audit, the Firebase target was `seolleyeon`. The chat-profile bucket and callable may not yet be live in that target. Treat that environment as production-like unless the team explicitly designates it as staging.
