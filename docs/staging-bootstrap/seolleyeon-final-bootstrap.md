# seolleyeon-final staging bootstrap

Generated: 2026-05-19 KST

## Goal

Prepare `seolleyeon-final` as the staging Firebase/GCP project for Seolleyeon without copying real user source photos, private media, raw embeddings, temporary avatar candidates, signed URLs, or private bucket paths from `seolleyeon`.

## Immutable safety rules

- Source project `seolleyeon` is read-only for this bootstrap.
- Target project is `seolleyeon-final`.
- Firebase alias is `staging`.
- Public/recommendation display remains approved-avatar-only.
- Chat real profile photo access remains backend-authorized only.
- Do not write signed URLs, source photo URLs, `gcsUri`, `userPrivateMedia`, or `clipEmbeddings` to public client-readable documents.
- Do not commit service account JSON, ID tokens, Firebase refresh tokens, signed URLs, private image paths, or real user image logs.

## Guard state

The SG-0 guard passed after aligning local CLI state:

```sh
gcloud config set project seolleyeon-final
gcloud auth application-default set-quota-project seolleyeon-final
firebase use staging
```

Verified state:

- gcloud account: `seolleyeon.official@gmail.com`
- gcloud project: `seolleyeon-final`
- Firebase project: `seolleyeon-final`
- ADC quota project: `seolleyeon-final`
- target project visible and ACTIVE

## Execution order

1. SG-0: project/account guard and resource map.
2. SG-1: APIs, Firestore database, staging buckets, IAM, resource scripts.
3. SG-2: Firestore/Storage rules and selective Functions deploy.
4. SG-3: Android/iOS Firebase app registration and FlutterFire staging config.
5. SG-4: Cloud Run/recommendation service migration scripts and deployment.
6. SG-5: sanitized Firestore migration script and dry-run/apply.
7. SG-6: staging Auth test users A/B/C.
8. SG-7: final verification, privacy QA, and handoff.

## Current blockers after SG-0

- `seolleyeon-final` has no Firebase Android/iOS apps yet.
- `seolleyeon-final` API/resource bootstrap is not complete yet.
- Firestore default database was not present during SG-0 read-only inspection, and was created during SG-1 in `asia-northeast3`.
- Cloud Run Admin API was not enabled during SG-0 read-only inspection.
- Client Firebase config files still point to `seolleyeon` until SG-3.

## SG-1 status

- Firestore default database: created in `asia-northeast3`, native mode.
- API enable attempt: blocked by missing billing account for paid deployment APIs.
- Staging buckets: creation blocked by missing billing account.
- Guard scripts: created under `scripts/staging_*.sh`.

Billing blocker evidence:

```text
FAILED_PRECONDITION: Billing account for project '810450765203' is not found.
HTTPError 403: The billing account for the owning project is disabled in state absent.
```

After billing is linked, rerun:

```sh
bash scripts/staging_check_project_guard.sh
bash scripts/staging_enable_services.sh --apply
bash scripts/staging_create_buckets.sh --apply
bash scripts/staging_verify_bucket_iam.sh
```
