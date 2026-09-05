> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](../avatar-production/CURRENT_ARCHITECTURE.md).
>

# seolleyeon-final rules and functions deploy

Generated: 2026-05-19 KST

## SG-2 result

Status: `PARTIAL_BLOCKED_BY_STORAGE_SETUP_AND_BILLING`

## Local verification

Passed:

```sh
npm --prefix functions run build
npm --prefix functions test
```

Function test result: 28 passed.

## Firestore rules

Deployed successfully:

```sh
firebase deploy --only firestore:rules --project seolleyeon-final --non-interactive
```

Evidence:

- `firestore.rules` compiled successfully.
- rules released to `cloud.firestore`.

## Storage rules

Blocked:

```sh
firebase deploy --only storage --project seolleyeon-final --non-interactive
```

Error:

```text
Firebase Storage has not been set up on project 'seolleyeon-final'.
Go to Firebase Console -> Storage -> Get Started.
```

This is consistent with the five required staging buckets being blocked by missing billing.

## Functions deploy readiness

Selective deploy target:

```sh
firebase deploy \
  --only functions:getChatRealProfilePhoto,functions:uploadAvatarSourcePhoto,functions:getAvatarJobCandidates,functions:approveAvatarCandidate \
  --project seolleyeon-final \
  --non-interactive
```

Do not run Functions deploy until:

1. Billing is linked to `seolleyeon-final`.
2. Deployment APIs are enabled.
3. Required staging buckets exist.
4. Bucket-level IAM is granted to the confirmed runtime service account.
5. `functions/.env.seolleyeon-final` exists locally with reviewed staging bucket names.

## Function environment

Created example file:

- `functions/.env.seolleyeon-final.example`

Copy it locally before deployment:

```sh
cp functions/.env.seolleyeon-final.example functions/.env.seolleyeon-final
```

`functions/.env.seolleyeon-final` is gitignored. It must not contain secrets.

Required non-secret staging values:

- `ENVIRONMENT=staging`
- `GCP_PROJECT=seolleyeon-final`
- `SOURCE_PHOTO_BUCKET=seolleyeon-final-private-source-photos`
- `CHAT_PROFILE_PHOTO_BUCKET=seolleyeon-final-chat-profile-photos`
- `APPROVED_AVATAR_BUCKET=seolleyeon-final-approved-avatars`
- `AVATAR_TEMP_BUCKET=seolleyeon-final-avatar-temp`
- `WRITE_LEGACY_ONBOARDING_PHOTO_URLS=false`
- `CHAT_REAL_PHOTO_SIGNED_URL_TTL_SECONDS=300`

## Scripts

Created:

- `scripts/staging_deploy_rules.sh`
- `scripts/staging_deploy_functions.sh`

Dry-run examples:

```sh
bash scripts/staging_deploy_rules.sh --firestore-only
bash scripts/staging_deploy_functions.sh
```

Apply examples after blockers are cleared:

```sh
bash scripts/staging_deploy_rules.sh --apply --firestore-only
bash scripts/staging_deploy_rules.sh --apply --storage-only
bash scripts/staging_deploy_functions.sh --apply
```

## SG-2 handoff

```json
{
  "subagent": "SG-2",
  "status": "partial",
  "source_project": "seolleyeon",
  "target_project": "seolleyeon-final",
  "firebase_alias": "staging",
  "rules_deployed": ["firestore.rules"],
  "functions_deployed": [],
  "test_results": ["functions build pass", "functions test pass"],
  "blocked_by_env": [
    "Firebase Storage is not initialized.",
    "Billing is not linked, so deployment APIs and buckets are blocked."
  ],
  "required_followups": [
    "Link billing to seolleyeon-final.",
    "Create buckets and deploy storage rules.",
    "Enable Cloud Functions/Build/Run/Eventarc/Tasks APIs.",
    "Deploy selective functions with staging env file."
  ]
}
```
