# seolleyeon-final basic resources

Generated: 2026-05-19 KST

## SG-1 result

Status: `PARTIAL_BLOCKED_BY_BILLING`

Live mutation was attempted only after the SG-0 guard passed for:

- gcloud project: `seolleyeon-final`
- Firebase project: `seolleyeon-final`
- active account: `seolleyeon.official@gmail.com`
- ADC quota project: `seolleyeon-final`

## APIs

Already enabled:

- `firebase.googleapis.com`
- `firestore.googleapis.com`
- `datastore.googleapis.com`
- `firebaserules.googleapis.com`
- `firebasehosting.googleapis.com`
- `storage.googleapis.com`
- `pubsub.googleapis.com`
- `fcm.googleapis.com`
- `identitytoolkit.googleapis.com`
- `logging.googleapis.com`
- `monitoring.googleapis.com`

Enable attempt for deployment APIs failed because the project has no linked billing account:

- `cloudfunctions.googleapis.com`
- `run.googleapis.com`
- `cloudbuild.googleapis.com`
- `artifactregistry.googleapis.com`
- `iamcredentials.googleapis.com`
- `cloudtasks.googleapis.com`
- `cloudscheduler.googleapis.com`
- `secretmanager.googleapis.com`
- `workflows.googleapis.com`
- `eventarc.googleapis.com`

Retry after billing is linked:

```sh
bash scripts/staging_enable_services.sh --apply
```

## Firestore

Default database was created successfully:

- database: `(default)`
- location: `asia-northeast3`
- type: Firestore Native
- edition: Standard
- delete protection: disabled
- PITR: disabled

This project should now be usable for rules/index deploys and staging test documents once rules are deployed.

## Buckets

Required buckets:

- `gs://seolleyeon-final-private-source-photos`
- `gs://seolleyeon-final-chat-profile-photos`
- `gs://seolleyeon-final-approved-avatars`
- `gs://seolleyeon-final-avatar-temp`
- `gs://seolleyeon-final-firestore-migration`

Creation failed for all five because project billing is absent. The failed command class was:

```text
gcloud storage buckets create ... --project=seolleyeon-final --uniform-bucket-level-access --public-access-prevention
```

Retry after billing is linked:

```sh
bash scripts/staging_create_buckets.sh --apply
bash scripts/staging_verify_bucket_iam.sh
```

## IAM

Visible service account:

- `firebase-adminsdk-fbsvc@seolleyeon-final.iam.gserviceaccount.com`

Functions runtime service account is not confirmed yet because Functions/Cloud Run bootstrap is blocked by billing and no target functions are deployed.

Do not grant broad project-level Storage Admin by default. Prefer bucket-level object permissions after the runtime service account is confirmed.

## Scripts

Created:

- `scripts/staging_common.sh`
- `scripts/staging_check_project_guard.sh`
- `scripts/staging_enable_services.sh`
- `scripts/staging_create_buckets.sh`
- `scripts/staging_verify_bucket_iam.sh`

Dry-run verification:

```sh
bash -n scripts/staging_common.sh scripts/staging_check_project_guard.sh scripts/staging_enable_services.sh scripts/staging_create_buckets.sh scripts/staging_verify_bucket_iam.sh
bash scripts/staging_check_project_guard.sh
bash scripts/staging_enable_services.sh
bash scripts/staging_create_buckets.sh
```

`staging_verify_bucket_iam.sh` currently fails as expected because buckets do not yet exist.

## SG-1 handoff

```json
{
  "subagent": "SG-1",
  "status": "partial",
  "source_project": "seolleyeon",
  "target_project": "seolleyeon-final",
  "firebase_alias": "staging",
  "resources_created_or_verified": [
    "Firestore default database created in asia-northeast3",
    "staging guard scripts created",
    "bucket/API dry-run scripts created"
  ],
  "blocked_by_env": [
    "Billing account is not linked to seolleyeon-final, blocking deployment APIs and bucket creation."
  ],
  "required_followups": [
    "Link billing account to seolleyeon-final.",
    "Run scripts/staging_enable_services.sh --apply.",
    "Run scripts/staging_create_buckets.sh --apply.",
    "Confirm Functions runtime service account, then add bucket-level IAM."
  ]
}
```
