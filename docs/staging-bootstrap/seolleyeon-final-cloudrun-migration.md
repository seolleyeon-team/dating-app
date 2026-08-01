# seolleyeon-final Cloud Run migration

Generated: 2026-05-19 KST

## SG-4 result

Status: `DEPLOY_BLOCKED_BY_BILLING_AND_APIS`

Source project `seolleyeon` was inspected read-only. No source project mutation was performed.

## Source inventory

Source Cloud Run jobs in `asia-northeast3`:

| Job | Status |
|---|---|
| `recs-export` | present |
| `recs-clip` | present |
| `recs-svd` | present |
| `recs-knn` | present |
| `recs-rrf` | present |
| `recs-verify` | present |

Source Artifact Registry repositories:

| Repository | Format |
|---|---|
| `gcf-artifacts` | Docker |
| `seolleyeon-repo` | Docker |

Target `seolleyeon-final` inventory is blocked until `run.googleapis.com` and `artifactregistry.googleapis.com` are enabled.

## Repo deployment source

- Recommendation image: `recsys/Dockerfile`
- Cloud Build config: `cloudbuild.yaml`
- Deployment script: `infra/deploy.sh`
- Workflow: `infra/workflows/recs_pipeline.yaml`
- Avatar worker Dockerfile: `lib/ai_recommend_model/avatar_generation/Dockerfile`

`infra/deploy.sh` defaults to `GCP_PROJECT=seolleyeon`; staging commands must set `GCP_PROJECT=seolleyeon-final` explicitly or use the wrapper script.

## Scripts

Created:

- `scripts/staging_inventory_cloudrun_services.sh`
- `scripts/staging_deploy_cloudrun_services.sh`
- `scripts/staging_verify_cloudrun_services.sh`

Dry-run:

```sh
bash scripts/staging_deploy_cloudrun_services.sh
```

Apply after billing/API blockers are cleared:

```sh
bash scripts/staging_enable_services.sh --apply
bash scripts/staging_deploy_cloudrun_services.sh --apply
bash scripts/staging_verify_cloudrun_services.sh
```

## Staging safety requirements

- `SOURCE_PROJECT=seolleyeon` remains read-only.
- `TARGET_PROJECT=seolleyeon-final`.
- `GCP_PROJECT=seolleyeon-final` must be exported for `infra/deploy.sh`.
- `GCS_BUCKET` should be staging-owned, defaulting to `seolleyeon-final-recs`.
- Do not copy production secrets into target.
- Do not point staging jobs at production source buckets or production Firestore.

## Current blockers

- Billing account is not linked to `seolleyeon-final`.
- `run.googleapis.com` is disabled.
- `artifactregistry.googleapis.com` is disabled.
- `cloudbuild.googleapis.com`, `workflows.googleapis.com`, `cloudscheduler.googleapis.com` are disabled.

## SG-4 handoff

```json
{
  "subagent": "SG-4",
  "status": "partial",
  "source_project": "seolleyeon",
  "target_project": "seolleyeon-final",
  "firebase_alias": "staging",
  "cloud_run_services": [
    "recs-export",
    "recs-clip",
    "recs-svd",
    "recs-knn",
    "recs-rrf",
    "recs-verify"
  ],
  "apply_results": [],
  "blocked_by_env": [
    "Billing not linked; required Cloud Run/Build/Artifact Registry APIs disabled."
  ],
  "required_followups": [
    "Enable billing.",
    "Enable deployment APIs.",
    "Run staging Cloud Run deploy wrapper with explicit target project.",
    "Verify jobs and workflow."
  ]
}
```
