# G005 Live Evidence And Blockers

Date: 2026-07-27

## Project Guard

- Account: expected staging operator account verified.
- Active gcloud project: `seolleyeon-final`.
- Active Firebase project: `seolleyeon-final`.
- Source project `seolleyeon`: untouched.
- Production/public rollout: not executed.

## Current Read-Only And Staging Evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| Worker deploy | PASS | revision `00047-9qx`, 100% staging traffic |
| Worker auth | PASS | authenticated 200, unauthenticated 403 |
| Release inventory | PASS | complete; worker private; three buckets have no public IAM principals |
| Live preflight | PASS | zero blockers, one avatar-only optional warning |
| Observability apply | PASS | 29/29 resources applied |
| Observability verify | PASS | 29/29 in sync, zero mutations |
| Rollback verify | PASS | zero mutations, source aggregate unchanged |
| Queue active backlog | PASS | queued/running/stale all zero |
| Queue legacy retryables | WATCH | 9 old retryable records, strict alerts fired |
| Cost | WATCH | USD 0.06026 per approved avatar; worker p95 530.454s |
| Fresh live upload | BLOCKED | App Check exchange 403; upload/job count zero |

## Sanitized Artifacts

- `out/g005_final_release_inventory_00047_v4.json`
- `out/g005_final_rollback_verify_00047_v5.json`
- `out/g005_final_observability_apply_00047_v4.json`
- `out/g005_final_observability_verify_00047_v4.json`
- `out/g005_final_queue_health_00047.json`
- `out/g005_final_queue_health_strict_00047.json`
- `out/g005_final_cost_report_00047.json`
- `out/pr85_small_face_validation_00047_20260727.json`
- `out/pr85_small_face_runner_apply_00047_20260727.json`

The artifacts omit UID values, source object paths, tokens, signed URLs, raw
landmarks, embeddings, and command stderr.

## Blockers And Owners

| ID | State | Required action |
| --- | --- | --- |
| OPS-APP-CHECK | blocked external | Obtain an authorized staging App Check debug token or approved device flow; do not bypass enforcement |
| OPS-QUEUE-LEGACY | watch | Review lineage for 9 old retryable jobs and explicitly authorize retry or terminalization |
| OPS-NOTIFY | watch | Bind an owner-approved notification channel to installed staging alert policies |
| OPS-LATENCY | watch | Diagnose model load/trait/QA p95 before changing deadline or timeout |
| OPS-BRIDGE | blocked production | Complete or formally approve the festival bridge exit plan |

`PRODUCTION_OPERATIONS_READY=false` remains mandatory.