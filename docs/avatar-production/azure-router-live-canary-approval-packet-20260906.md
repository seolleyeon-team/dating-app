# Azure GPT Image 2 router live-canary approval packet

Status: **BLOCKED — no live-call approval requested**

Inventory date: 2026-09-06 (Asia/Seoul)  
Router main merge: `f0c611baf00d11774bfd8ab7efb48af7ea78b38b`  
PR: `#80`

No Azure image generation, Secret Manager write/IAM change, Cloud Run revision or
traffic change, Cloud Tasks update, or queue pause/resume was performed while
preparing this packet.

## Read-only inventory

### GCP production

| Resource | Observed state |
|---|---|
| Cloud Run worker | `seolleyeon-avatar-worker-00116-nal`; timeout 1800s; request concurrency 1; min 0; max instances 1 |
| Production contract | `ENVIRONMENT=production`; `AVATAR_WORKER_MODE=azure_gpt_image_2`; staging heuristic preview `false`; new generation disabled flag `false` |
| Candidate contract | initial 2; extra 2; max 4; extra threshold 2 |
| Face detector | enabled; `mediapipe` |
| Existing Azure binding | one `foundry_v1` endpoint; deployment `gpt-image-2`; API version `preview`; configured 2 RPM; provider concurrency 1; timeout 90s |
| Existing endpoint hostname | `seolleyeon-ai-staging-01.services.ai.azure.com` |
| Cloud Tasks | `avatar-generation`, asia-northeast3; **RUNNING**; max concurrent 1; 1 dispatch/s; max attempts 3; 30s–600s backoff |
| Firestore | `(default)`, Native mode, asia-northeast3 (previously verified; re-confirm before live approval) |
| Media buckets | source/temp/approved present; public access prevention enforced; uniform bucket-level access enabled |

The queue was expected to be PAUSED by the task brief but was observed RUNNING in
two independent read-only describes. This process did not change it. Do not assume
the queue is safe for a canary until ownership and intended state are reconciled.

### Multi-endpoint config and secrets

The production revision contains only the legacy single-endpoint variables. It has
no `AZURE_OPENAI_ENDPOINT_IDS`, no per-endpoint quota map, and no EP1–EP5 bindings.

| Logical ID | Cloud Run config | Secret exists | Enabled version | Worker accessor | Result |
|---|---:|---:|---:|---:|---|
| EP1 | absent | no | no | no | `CREATE_REQUIRED` |
| EP2 | absent | no | no | no | `CREATE_REQUIRED` |
| EP3 | absent | no | no | no | `CREATE_REQUIRED` |
| EP4 | absent | no | no | no | `CREATE_REQUIRED` |
| EP5 | absent | no | no | no | `CREATE_REQUIRED` |
| Legacy single endpoint | present | yes | yes | yes | current revision only |

Secret values were never read. The required future secret resource names are
`seolleyeon-avatar-azure-ep1-api-key` through
`seolleyeon-avatar-azure-ep5-api-key`.

### Azure authority

Azure CLI authentication was available for one enabled subscription, `Azure for
Students`. That subscription exposed zero Azure OpenAI resources. Consequently the
following cannot currently be verified from Azure authority:

- ownership of the currently bound `seolleyeon-ai-staging-01` resource;
- five endpoint resource names and regions;
- deployment status/model/SKU/capacity;
- deployment type (`DataZoneStandard` versus `GlobalStandard`);
- actual per-deployment RPM; and
- supported API version/style for each endpoint.

The configured 2 RPM value is not proof of Azure-side quota. Microsoft currently
documents different GPT Image 2 defaults by deployment type, so the Azure resource
and deployment inventory must be the authority before any call.

### Privacy/region comparison

Current technical behavior sends a privacy-processed image reference to an external
Azure endpoint. The current public privacy notice and in-app legal text list
Firebase/Google Cloud, Kakao, PortOne, and identity-verification providers, but do
not list Microsoft/Azure. They also do not specify an Azure region set or a
cross-border transfer destination, fields, purpose, or retention contract.

This is a configuration/policy mismatch report, not a legal opinion. Product/privacy
owners must document and approve the allowed Azure region/deployment type and the
required user-facing disclosure before a multi-region canary.

## Required preconditions

All of the following are required before Phase 0:

1. Identify an Azure subscription/tenant that exposes every intended GPT Image 2
   resource to read-only inventory.
2. Map five opaque IDs to verified resource, region, endpoint, deployment, model,
   SKU, deployment type, API style/version, provisioning status, and actual RPM.
3. Resolve whether a staging-named Azure resource is intentionally used by the
   production worker.
4. Create EP1–EP5 secrets, add enabled versions, and grant only the worker service
   account accessor — each is a separately approved mutation.
5. Prepare a no-traffic staging revision with explicit `ENVIRONMENT=staging` and
   the multi-endpoint config. Production must explicitly use
   `ENVIRONMENT=production` and heuristic preview `false`.
6. Reconcile the unexpected RUNNING production queue state. Do not use that queue
   as a staging rate limiter and do not resume it as part of this packet.
7. Obtain product/privacy approval for the exact Azure region/deployment set.
8. Approve a per-image price `P` and a hard canary cost ceiling.

## Canary phases and maximum exposure

`P` is the approved worst-case price of one provider generation request. It is left
symbolic until billing SKU/quality/size are verified. Every test job retains the
exact initial 2 + optional extra 2 = maximum 4 logical provider-call contract.
Pre-send routing attempts do not increase that logical maximum; ambiguous outcomes
stop without failover.

| Phase | Approved cohort | Max provider calls | Max cost | Cloud Run max instances | Request concurrency | Task concurrency | Traffic |
|---|---:|---:|---:|---:|---:|---:|---|
| 0 | no identities | 0 | 0 | 1 | 1 | 0 | no-traffic revision; readiness/simulation only |
| 1 | 1 test identity / 1 job | 4 | `4 × P` | 1 | 1 | 1 | explicitly targeted staging task only |
| 2 | 2 identities / 2 jobs | 8 | `8 × P` | 2 temporary | 1 | 2 | staging only |
| 3 | 5 identities / 5 jobs | 20 | `20 × P` | 5 temporary | 1 until measured safe | 5 | staging only |
| 4 | separately approved `M` jobs | `4 × M` | `4 × M × P` | calculator output pending | measured | calculator output pending | latency/throughput measurement |
| 5 | separately approved cohort | separately capped | separately capped | measured recommendation | measured | measured recommendation | final staging validation |

The values 1, 2, and 5 are temporary checkpoints, not production ceilings. Phase 4
uses measured provider p50/p95/p99, end-to-end job p95, and safe per-container
request concurrency with `scripts/avatar_azure_capacity_plan.py`.

For total provider rate `R` calls/minute and provider latency `W` seconds:

`provider in-flight concurrency = ceil((R / 60) × W)`

Task concurrency is independently calculated from job throughput and end-to-end job
p95. Cloud Run max instances is then calculated from task concurrency divided by
measured-safe container request concurrency. Endpoint count is never used as the
Cloud Run ceiling.

## Deadline envelope

The current conservative planner budgets:

- two-call path: 410 seconds;
- four-call path: 720 seconds;
- worker request/job default: 900 seconds; and
- draft staging Cloud Run/dispatch deadline: 1800 seconds, internal job budget 1500
  seconds.

Staging must measure provider and job p50/p95/p99 plus remaining deadline margin.
If p95 approaches the envelope, do not raise concurrency as a substitute for
changing task boundaries or deadlines.

## Measurements required

- provider latency and achieved RPM by opaque endpoint ID;
- reservation wait/slot age, transaction attempts/contention, duplicate slots;
- 429 rate and exact `Retry-After`/`retry-after-ms` behavior;
- pre-send, definite-rejected, ambiguous, and success counts;
- initial-only versus extra-round frequency and actual calls per job;
- artifact recovery hits, invalid-manifest review cases, and duplicate paid-call
  evidence;
- end-to-end job latency, cold start, CPU/memory/QA utilization, and deadline margin;
- Cloud Tasks schedule delay/attempts/concurrent dispatches; and
- Azure billing cost reconciled to provider request metrics.

## Immediate stop conditions

Stop the canary and shift staging traffic back to the prior revision on any of:

- duplicate paid generation;
- ambiguous outcome followed by any failover;
- endpoint RPM violation or duplicate reservation;
- pathological Firestore contention/failure;
- unexpected 429 semantics or unsafe `Retry-After` handling;
- insufficient deadline margin;
- artifact recovery/hash/manifest mismatch;
- required QA component unavailable;
- secret binding/access error; or
- wrong environment, endpoint, project, deployment, or region.

Rollback is: stop new staging dispatch, keep or return traffic to the previous
revision, preserve deterministic artifacts/router state for reconciliation, and
review ambiguous jobs. Never refund reservations, delete ambiguous artifacts, or
automatically regenerate. This packet intentionally contains no production queue
resume command.

## Approval boundary

Current verdict: `BLOCKED_AZURE_ENDPOINT_CONFIGURATION`.

An independent `BLOCKED_PRIVACY_REGION_POLICY` condition also exists until the exact
region set and documented policy are reconciled. No phase may make an Azure image
request until both conditions and the unexpected queue-state issue are cleared and
the user separately approves the finite live-call/cost budget.
