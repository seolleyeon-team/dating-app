# seolleyeon-final final handoff

Generated: 2026-05-19 KST

## Status

Final status: `PASS_STAGING_PARTIAL`

Production-ready: no.

Staging project guard and Android/iOS Firebase app configuration are ready. Firestore default database exists and Firestore rules have been deployed. The remaining live deployment work is blocked by the missing billing account on `seolleyeon-final`, which prevents required APIs and buckets from being created.

## Completed

- gcloud account/project aligned to `seolleyeon.official@gmail.com` / `seolleyeon-final`.
- Firebase alias `staging` points to `seolleyeon-final`.
- ADC quota project set to `seolleyeon-final`.
- Firestore default database created in `asia-northeast3`.
- Firestore rules deployed to `seolleyeon-final`.
- Android Firebase app registered and config downloaded.
- iOS Firebase app registered and config downloaded.
- `lib/firebase_options.dart` regenerated for Android/iOS staging.
- Source Cloud Run recommendation jobs inventoried read-only.
- Sanitized Firestore migration script created and dry-run passed.
- Staging Auth A/B/C creation script created and dry-run passed.
- Privacy QA passed locally.

## Blocked

- Billing account is not linked to `seolleyeon-final`.
- Required paid/deployment APIs cannot be enabled:
  - Cloud Functions
  - Cloud Run
  - Cloud Build
  - Artifact Registry
  - Cloud Tasks
  - Cloud Scheduler
  - Secret Manager
  - Workflows
  - Eventarc
  - IAM Credentials
- Required staging buckets do not exist.
- Firebase Storage is not initialized, so Storage rules cannot deploy yet.
- Functions are not deployed to `seolleyeon-final`.
- Cloud Run jobs/workflow/scheduler are not deployed to `seolleyeon-final`.
- Auth test users were not applied because `firebase_admin` is not installed in `.venv`.

## Immediate next commands after billing is linked

```sh
bash scripts/staging_check_project_guard.sh
bash scripts/staging_enable_services.sh --apply
bash scripts/staging_create_buckets.sh --apply
bash scripts/staging_verify_bucket_iam.sh
firebase deploy --only storage --project seolleyeon-final --non-interactive
cp functions/.env.seolleyeon-final.example functions/.env.seolleyeon-final
bash scripts/staging_deploy_functions.sh --apply
bash scripts/staging_deploy_cloudrun_services.sh --apply
```

Install Auth script dependency before creating users:

```sh
.venv/Scripts/python.exe -m pip install firebase-admin
.venv/Scripts/python.exe scripts/create_staging_auth_test_users.py --target_project seolleyeon-final --apply --create_firestore_fixtures
```

Only apply sanitized Firestore migration after reviewing the dry-run report:

```sh
.venv/Scripts/python.exe scripts/migrate_firestore_sanitized_to_staging.py --source_project seolleyeon --target_project seolleyeon-final --apply --sanitize_ack --report_json out/staging_migration_apply.json
```

## Verification summary

Passed:

- `bash scripts/staging_check_project_guard.sh`
- `npm --prefix functions run build`
- `npm --prefix functions test`
- `flutter analyze`
- `flutter test test/chat_profile_photo_service_test.dart test/avatar_source_photo_service_test.dart test/profile_display_image_resolver_test.dart`
- `.venv/Scripts/python.exe scripts/qa_media_privacy.py --dry_run --fail_on_warning`
- `.venv/Scripts/python.exe scripts/migrate_firestore_sanitized_to_staging.py --source_project seolleyeon --target_project seolleyeon-final --dry_run --max_docs_per_collection 2`
- `.venv/Scripts/python.exe scripts/create_staging_auth_test_users.py --target_project seolleyeon-final --dry_run`

Expected failures:

- `bash scripts/staging_verify_bucket_iam.sh`: buckets do not exist.
- `bash scripts/staging_verify_cloudrun_services.sh`: `run.googleapis.com` is disabled due billing blocker.
- `firebase deploy --only storage`: Firebase Storage is not initialized.

## Privacy notes

- No production user source photos were migrated.
- No `userPrivateMedia` or `clipEmbeddings` were migrated.
- No signed URLs were written to Firestore.
- Flutter Dart code has no direct references to private media collections, source buckets, chat-profile buckets, or signed URL generation.
- Sanitized migration denies private collections and drops image/private/signed fields recursively.

## Final handoff JSON

```json
{
  "status": "PASS_STAGING_PARTIAL",
  "production_ready": false,
  "source_project": "seolleyeon",
  "target_project": "seolleyeon-final",
  "firebase_alias": "staging",
  "completed": [
    "project guard",
    "Firestore database",
    "Firestore rules deploy",
    "Android/iOS Firebase app config",
    "Cloud Run source inventory",
    "sanitized migration dry-run",
    "Auth user dry-run",
    "privacy QA"
  ],
  "blockers": [
    "billing not linked",
    "deployment APIs disabled",
    "staging buckets missing",
    "Firebase Storage not initialized",
    "functions/cloud run not deployed"
  ]
}
```
