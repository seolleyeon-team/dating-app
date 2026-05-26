Read ./hermes_goal_prompt.md first and obey it as the autonomous controller.
Then execute this task prompt.

Diagnosis result: RESERVE_POOL_NOT_ACTIVATED plus manual policy blocker. Do not generate images. Do not run bounded-chunk-run. Do not invoke Image Gen.

Next task: inspect ai_image/reports/pipeline_audit/v24_no_deficit_assets_root_cause_latest.json, obtain/encode safe policy for handling manual_review_required.flag reason no_deficit_assets_available created by the failed no-reserve planning attempt, then perform planning-only recheck with --activate-reserve only. Do not generate unless a fresh canRun=true plan exists and manual flag is absent.

$ultragoal "Diagnose and repair no_deficit_assets_available after v24 active refresh by enabling the safest eligible candidate path: active, reserve, retry, or replacement pool. Do not generate images.

You are Hermes/Codex operating on the Seolleyeon AI PROFILE IMAGE pipeline.

This is a no-generation planner eligibility / candidate-pool repair task.

Do not generate images.
Do not invoke Image Gen.
Do not run hermes-one-asset-loop.
Do not run bounded-chunk-run.
Do not run supervisor-720.
Do not run stale autopilot.
Do not call OpenAI Image API.
Do not call Batch API.
Do not fabricate QA JSON.
Do not approve assets or identities.
Do not delete or quarantine files.
Do not modify recommender scripts.
Do not modify Git index.
Do not run file-qa --asset-id.
Do not run contact-sheets.
Do not run active-visual-qa-all.
Do not run distribution-audit after planning before generation.
Do not clear manual flag blindly.

All Python pipeline commands should be run with the environment cleanup prefix unless impossible:

env -u PYTHONIOENCODING PYTHONUTF8=1 python ...

Reason:
A previous run observed PYTHONIOENCODING pollution causing:
LookupError: unknown encoding: udeclardeclare -x PYTHONUTF8=1...

Repo root:
C:/Users/Mickey/StudioProjects/dating-app-ai_profile_image

Current known state:
- v24 active prepare refresh succeeded.
- generation_manifest.jsonl was refreshed to v24.
- controlled planner command failed:
  env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --root . --production --max-assets 18 --max_identities 6 --force-replan --abandon-current
- failure reason:
  no_deficit_assets_available
- manual flag created:
  ai_image/manifests/manual_review_required.flag
- manualReviewRequired: true
- approvedCompleteIdentities: 74 / 240
- approvedImages: 222 / 720
- femaleApprovedCompleteIdentities: 8 / 120
- maleApprovedCompleteIdentities: 66 / 120
- completion failure reasons:
  - manual_review_required
  - distribution_mismatch
- unresolvedPendingImagegen: false
- missingVisualVerdict: false
- invalidApprovedIdentities: []
- invalidApprovedAssets: []

This blocker is not:
- imagegen failure
- pending corruption
- stale prompt version after refresh
- approved evidence regression

It is:
- planner/candidate availability failure after v24 refresh.

============================================================
1. OBJECTIVE
============================================================

Resolve or classify the no_deficit_assets_available blocker safely.

The pipeline still needs:
- 240 approved complete identities total
- 720 approved images total
- 120 female approved identities
- 120 male approved identities

Current deficit:
- identities: 166
- images: 498
- female: 112
- male: 54

This task should:

1. Confirm current state.
2. Audit all possible candidate pools:
   - active primary pool
   - reserve pool
   - targeted asset retry candidates
   - full identity retry candidates
   - replacement identity pool candidates
3. Determine why bounded planner sees no eligible assets.
4. If a safe candidate path already exists, enable it.
5. If a narrow non-destructive patch is needed, implement it with tests.
6. If replacement pool is needed, prepare or dry-run replacement pool only.
7. Archive/clear manual flag only after a valid eligible candidate path is proven.
8. Create a fresh runnable production plan only after manual flag can be safely cleared.
9. Do not run generation.

Allowed final outcomes:
- NO_DEFICIT_ASSETS_SAFE_REPAIRED_AND_PLAN_READY
- RESERVE_POOL_PLAN_READY
- RETRY_POOL_PLAN_READY
- REPLACEMENT_POOL_PLAN_READY
- REPLACEMENT_POOL_DRY_RUN_READY
- NO_DEFICIT_ASSETS_DIAGNOSED_REQUIRES_PATCH
- NO_DEFICIT_ASSETS_TRUE_EXHAUSTION
- MANUAL_POLICY_DECISION_REQUIRED
- APPROVED_EVIDENCE_REGRESSION
- MANUAL_FLAG_CLEAR_FAILED
- PLAN_FAILED
- BLOCKED

============================================================
2. PREFLIGHT
============================================================

Run:

env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py pending-status --root .
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-status --root .
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py completion-check --root .
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --help

Also inspect active processes:
- Codex
- imagegen
- hermes-one-asset-loop
- bounded-chunk
- run_ai_image_pipeline_v3
- supervisor

Verify:
- no active generation process
- pending unresolved=false
- manualReviewRequired=true
- manual flag reason exactly no_deficit_assets_available
- approvedCompleteIdentities=74
- approvedImages=222
- femaleApprovedCompleteIdentities=8
- maleApprovedCompleteIdentities=66
- no invalid approved evidence
- no unresolved pending
- bounded plan supports or lacks:
  - --activate-reserve
  - retry/replacement flags if any
  - --abandon-current

If active process exists:
- stop and return BLOCKED.

If pending unresolved exists:
- stop and return BLOCKED.

If approved count regresses below 74/222:
- stop and return APPROVED_EVIDENCE_REGRESSION.

If manual flag reason is not no_deficit_assets_available:
- stop and return BLOCKED.

============================================================
3. READ REQUIRED FILES
============================================================

Read:

Manifests:
- ai_image/manifests/identity_manifest.jsonl
- ai_image/manifests/ai_profile_specs_v3.jsonl
- ai_image/manifests/ai_profile_assets_v3.jsonl
- ai_image/manifests/imagegen_queue.jsonl
- ai_image/manifests/generation_manifest.jsonl
- ai_image/manifests/current_chunk_plan.json
- ai_image/manifests/current_chunk_state.json
- ai_image/manifests/approved_identity_manifest.jsonl
- ai_image/manifests/rejected_identity_manifest.jsonl
- ai_image/manifests/asset_qa_manifest.jsonl
- ai_image/manifests/identity_qa_manifest.jsonl
- ai_image/manifests/file_qa_manifest.jsonl
- ai_image/manifests/abandoned_chunk_manifest.jsonl
- ai_image/manifests/manual_review_required.flag

Distribution:
- ai_image/config/AI_IMAGE_DISTRIBUTION_TARGETS_V3.json
- ai_image/reports/latest_distribution_audit.json
- ai_image/reports/distribution_audit.json
- ai_image/reports/distribution_report.csv

Retry/replacement reports if present:
- ai_image/reports/pipeline_audit/rejected_abandoned_reason_taxonomy_latest.json
- ai_image/reports/pipeline_audit/targeted_asset_retry_plan_latest.json
- ai_image/reports/pipeline_audit/full_identity_retry_plan_latest.json
- ai_image/reports/pipeline_audit/retired_identity_plan_latest.json
- ai_image/reports/pipeline_audit/replacement_identity_pool_plan_latest.json
- ai_image/reports/pipeline_audit/reserve_pool_activation_latest.json
- ai_image/reports/pipeline_audit/reserve_pool_plan_latest.json

Recent no-deficit reports:
- ai_image/reports/pipeline_audit/no_deficit_assets_root_cause_latest.json
- ai_image/reports/pipeline_audit/no_deficit_assets_eligibility_funnel.json
- ai_image/reports/pipeline_audit/no_deficit_assets_distribution_gap_table.json

Code:
- scripts/ai_image_pipeline_v3/bounded_batch_executor.py
- scripts/ai_image_pipeline_v3/distribution_selection.py
- scripts/ai_image_pipeline_v3/distribution_prepare.py
- scripts/ai_image_pipeline_v3/distribution_targets.py
- scripts/ai_image_pipeline_v3/retry_plan.py
- scripts/ai_image_pipeline_v3/cli.py
- scripts/ai_image_pipeline_v3/manifest.py
- scripts/ai_image_pipeline_v3/prepare.py
- scripts/ai_image_pipeline_v3/manual_review.py
- scripts/ai_image_pipeline_v3/retry_replacement_policy.py, if present
- scripts/ai_image_pipeline_v3/female_reset.py, if present

Do not fabricate if files are absent.
Record missing files.

============================================================
4. BUILD CANDIDATE POOL FUNNEL
============================================================

Build an updated candidate funnel from active v24 manifests.

For each profile, compute:

- profileId
- gender
- activeForTarget
- isReserve / identityScope
- faceType
- looksLevelBand
- eyewear
- season
- approved status
- rejected status
- abandoned status
- retired status if any
- prepared/never-generated status
- generated but unapproved
- file-complete unreviewed
- targeted retry eligible?
- full identity retry eligible?
- replacement eligible?
- active primary eligible?
- reserve eligible?
- excluded reasons
- promptTargetingVersion
- promptHash status
- asset count
- shot types present
- queue statuses
- generation statuses
- final file presence
- QA statuses

Summaries required:
- total identities
- primary active identities
- reserve identities
- approved complete identities
- rejected identities
- abandoned identities
- retired identities
- never generated prepared identities
- generated unapproved identities
- targeted retry candidates
- full identity retry candidates
- replacement candidates
- eligible active candidates
- eligible reserve candidates
- eligible retry candidates
- eligible replacement candidates
- top exclusion reasons

Write:
- ai_image/reports/pipeline_audit/v24_no_deficit_candidate_funnel.csv
- ai_image/reports/pipeline_audit/v24_no_deficit_candidate_funnel.json

============================================================
5. DECIDE CANDIDATE PATH PRIORITY
============================================================

Use this priority:

1. Active primary candidates if any.
2. Reserve candidates if any.
3. Targeted asset retry candidates if any.
4. Full identity retry candidates if any.
5. Replacement identity pool if needed.
6. Manual policy decision only if none of the above is available.

Do NOT enable rejected/abandoned reuse blindly.
Only use retry candidates classified by taxonomy/policy.

Do NOT alter distribution targets.

Do NOT count file-QA-only images.

============================================================
6. RESERVE PATH CHECK
============================================================

If reserve candidates exist:
- verify --activate-reserve is supported.
- verify candidates are not approved/rejected/abandoned/retired.
- verify promptTargetingVersion=v24.
- verify promptHash mismatches=0.
- verify no 4.4-5.0.
- verify selectedAssetCount=selectedIdentityCount*3.

If valid reserve candidates exist, prefer reserve path.

Potential command:

env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --root . --production --max-assets 18 --max_identities 6 --force-replan --abandon-current --activate-reserve

But do not run this until manual flag is safely cleared or the planner supports planning with flag.

============================================================
7. RETRY PATH CHECK
============================================================

If reserve candidates do not exist or are insufficient, inspect retry plans.

Targeted retry is eligible only if:
- face_card anchor approved/usable
- failed asset is silhouette or vibe
- no hard safety/childlike issue
- current promptTargetingVersion is newer than failure version or contains patch for failure class
- max retry count not exceeded
- reference/final evidence valid

Full identity retry is eligible only if:
- face_card failed or multiple shots failed
- retry policy permits it
- not retired
- no repeated hard safety issue
- prompt version has changed since failure or patch targets failure class
- max full retry count not exceeded

If retry path exists but planner lacks CLI support:
- implement a dry-run planning flag only if safe:
  - --activate-retry
  or
  - --retry-policy targeted|full|mixed
- add tests.
- do not run image generation.

============================================================
8. REPLACEMENT POOL CHECK
============================================================

If active/reserve/retry candidates are insufficient, replacement pool is needed.

Replacement pool rules:
- fill deficits by gender/faceType/looks/eyewear/season.
- preserve target distribution.
- no 4.4-5.0.
- avoid retired unstable target combos where possible.
- generate prepared identity/spec/asset rows only.
- no image generation.
- no approval.
- no final files.
- no collision with existing profile IDs.
- promptTargetingVersion=v24.
- promptHash current.
- each replacement identity has 3 assets.
- activeForTarget=true unless intentionally reserve.
- gender deficit should be prioritized:
  - female deficit is very large.
  - male deficit also remains but smaller.

If replacement pool support exists:
- run replacement dry-run only first.
- If dry-run proves safe, this task may create prepared replacement manifests only if command is explicit and non-destructive.
- If not safe, return REPLACEMENT_POOL_DRY_RUN_READY with exact apply command.

If replacement support does not exist:
- implement replacement pool planner/preparer only if non-destructive and testable.
- add tests.

Likely files if patching:
- scripts/ai_image_pipeline_v3/retry_replacement_policy.py
- scripts/ai_image_pipeline_v3/distribution_selection.py
- scripts/ai_image_pipeline_v3/bounded_batch_executor.py
- scripts/ai_image_pipeline_v3/manifest.py
- scripts/ai_image_pipeline_v3/cli.py
- tests/test_replacement_identity_pool_v3.py
- tests/test_retry_replacement_policy_v3.py

============================================================
9. MANUAL FLAG HANDLING
============================================================

Manual flag may be archived/cleared only if all are true:

- reason exactly no_deficit_assets_available
- pending unresolved=false
- no active generation process
- a valid eligible path has been proven:
  - reserve candidates, or
  - retry candidates, or
  - replacement candidates/prepared pool
- approved count remains stable
- clear is archived with sidecar
- no image generation in same clear step

If supported command exists, use:

env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py clear-manual-review --root . --reason no_deficit_assets_available

If existing clear policy refuses but the eligible path is proven, patch manual_review.py narrowly for this reason:
- only allow clear if no_deficit path is repaired
- archive flag and sidecar
- do not mark visual QA/distribution complete
- do not approve anything
- do not clear other reasons

If manual flag clear fails:
- return MANUAL_FLAG_CLEAR_FAILED or BLOCKED.
- do not plan.

============================================================
10. PLAN CREATION
============================================================

After candidate path and manual flag are resolved, create a fresh production plan.

Choose command based on candidate path.

Reserve:
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --root . --production --max-assets 18 --max_identities 6 --force-replan --abandon-current --activate-reserve

Retry:
Use implemented exact retry flag and report it.

Replacement:
Use implemented exact replacement flag and report it.

After plan, run:

env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py pending-status --root .
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-status --root .
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py completion-check --root .

Do not run distribution-audit after planning.

Validate:
- manualReviewRequired=false
- pending unresolved=false
- current chunk fresh
- canRun=true
- selectedIdentityCount<=6
- selectedAssetCount<=18
- promptTargetingVersion=face_type_looks_level_targeting_v24
- promptHash mismatches=0
- no rejected/abandoned reuse unless retry policy explicitly selected and safe
- no 4.4-5.0 selected
- approvedCompleteIdentities remains 74
- approvedImages remains 222

If plan cannot be created:
- return PLAN_FAILED.

============================================================
11. PATCH / TEST RULES
============================================================

Patch only if needed.

If patching, run relevant py_compile and tests.

Suggested tests based on changes:
- tests.test_reserve_pool_activation_v3
- tests.test_retry_replacement_policy_v3
- tests.test_replacement_identity_pool_v3
- tests.test_no_deficit_assets_diagnosis_v3
- tests.test_bounded_batch_executor_v3
- tests.test_chunk_planner_reuse_rules_v3
- tests.test_distribution_prepare_targets_v3
- tests.test_ai_image_completion_strict_v3

Use commands:
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m py_compile scripts/run_ai_image_pipeline_v3.py scripts/ai_image_pipeline_v3/cli.py scripts/ai_image_pipeline_v3/bounded_batch_executor.py scripts/ai_image_pipeline_v3/distribution_selection.py scripts/ai_image_pipeline_v3/manifest.py scripts/ai_image_pipeline_v3/manual_review.py

env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_reserve_pool_activation_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_retry_replacement_policy_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_replacement_identity_pool_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_bounded_batch_executor_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_chunk_planner_reuse_rules_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_distribution_prepare_targets_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_ai_image_completion_strict_v3 -q

If test files do not exist, report and continue with available relevant tests.

Do not run image generation.

============================================================
12. REPORTS TO WRITE
============================================================

Write:
- ai_image/reports/pipeline_audit/v24_no_deficit_repair_latest.md
- ai_image/reports/pipeline_audit/v24_no_deficit_repair_latest.json
- ai_image/reports/pipeline_audit/v24_no_deficit_candidate_funnel.csv
- ai_image/reports/pipeline_audit/v24_no_deficit_candidate_funnel.json

If patch applied:
- ai_image/reports/pipeline_audit/v24_no_deficit_repair_patch_latest.md
- ai_image/reports/pipeline_audit/v24_no_deficit_repair_patch_latest.json

If plan created:
- ai_image/reports/pipeline_audit/v24_no_deficit_plan_latest.md
- ai_image/reports/pipeline_audit/v24_no_deficit_plan_latest.json

Update autonomous reports:
- ai_image/reports/pipeline_audit/hermes_autonomous_loop_latest.json
- ai_image/reports/pipeline_audit/hermes_autonomous_loop_latest.md
- ai_image/reports/pipeline_audit/hermes_autonomous_loop_last_result.json
- ai_image/reports/pipeline_audit/hermes_autonomous_loop_last_result.md
- ai_image/reports/pipeline_audit/hermes_autonomous_loop_events.jsonl

JSON schema:
{
  "result": "NO_DEFICIT_ASSETS_SAFE_REPAIRED_AND_PLAN_READY | RESERVE_POOL_PLAN_READY | RETRY_POOL_PLAN_READY | REPLACEMENT_POOL_PLAN_READY | REPLACEMENT_POOL_DRY_RUN_READY | NO_DEFICIT_ASSETS_DIAGNOSED_REQUIRES_PATCH | NO_DEFICIT_ASSETS_TRUE_EXHAUSTION | MANUAL_POLICY_DECISION_REQUIRED | APPROVED_EVIDENCE_REGRESSION | MANUAL_FLAG_CLEAR_FAILED | PLAN_FAILED | BLOCKED",
  "before": {
    "approvedCompleteIdentities": 74,
    "approvedImages": 222,
    "femaleApprovedCompleteIdentities": 8,
    "maleApprovedCompleteIdentities": 66,
    "manualFlagReason": "no_deficit_assets_available"
  },
  "candidateFunnel": {
    "activePrimaryEligible": 0,
    "reserveEligible": 0,
    "targetedRetryEligible": 0,
    "fullIdentityRetryEligible": 0,
    "replacementEligible": 0,
    "topExclusionReasons": {}
  },
  "selectedPath": null,
  "patch": {
    "applied": false,
    "filesChanged": [],
    "testsPassed": null
  },
  "manualFlag": {
    "clearedOrArchived": false,
    "archivePath": null
  },
  "plan": {
    "created": false,
    "chunkId": null,
    "canRun": false,
    "selectedIdentityCount": 0,
    "selectedAssetCount": 0,
    "selectedProfiles": [],
    "path": null,
    "promptTargetingVersion": "face_type_looks_level_targeting_v24",
    "promptHashMismatches": 0
  },
  "after": {
    "approvedCompleteIdentities": null,
    "approvedImages": null,
    "manualReviewRequired": null,
    "pendingUnresolved": null
  },
  "nextPromptWritten": false,
  "nextSafeCommand": null
}

============================================================
13. NEXT PROMPT BEHAVIOR
============================================================

If result ends with PLAN_READY:
- write ./hermes_prompt.md for generation of the fresh plan.
- Do not run generation in this task.
- The next prompt should allow exactly:
  env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py hermes-one-asset-loop --root . --mode chunk --max-assets 18 --allow-imagegen --max-pending-attempts 3 --retry-delay-seconds 2 --max-runtime-minutes 180

If result is REPLACEMENT_POOL_DRY_RUN_READY:
- write ./hermes_prompt.md for replacement pool apply/preparation, not generation.

If result requires patch:
- write continuation patch prompt.

If true exhaustion/manual policy:
- write hard stop report and do not generate.

============================================================
14. ALLOWED COMMANDS
============================================================

Allowed:
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py pending-status --root .
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-status --root .
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py completion-check --root .
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --help
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py clear-manual-review --root . --reason no_deficit_assets_available
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --root . --production --max-assets 18 --max_identities 6 --force-replan --abandon-current --activate-reserve
env -u PYTHONIOENCODING PYTHONUTF8=1 python scripts/run_ai_image_pipeline_v3.py --help

Allowed if patching:
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m py_compile scripts/run_ai_image_pipeline_v3.py scripts/ai_image_pipeline_v3/cli.py scripts/ai_image_pipeline_v3/bounded_batch_executor.py scripts/ai_image_pipeline_v3/distribution_selection.py scripts/ai_image_pipeline_v3/manifest.py scripts/ai_image_pipeline_v3/manual_review.py
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_reserve_pool_activation_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_retry_replacement_policy_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_replacement_identity_pool_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_bounded_batch_executor_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_chunk_planner_reuse_rules_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_distribution_prepare_targets_v3 -q
env -u PYTHONIOENCODING PYTHONUTF8=1 python -m unittest tests.test_ai_image_completion_strict_v3 -q

Allowed:
- inspect JSON/JSONL/CSV/reports
- inspect planner/retry/replacement code
- write reports
- write next ./hermes_prompt.md

Forbidden:
- image generation
- Hermes native image_generate
- Codex $imagegen
- hermes-one-asset-loop
- bounded-chunk-run
- supervisor-720
- stale autopilot
- active-visual-qa-all
- contact-sheets
- distribution-audit after planning before generation
- OpenAI Image API
- Batch API
- file-qa --asset-id
- deleting files
- quarantining files
- modifying recommender scripts
- modifying Git index
- manual flag blind clear
- rejected/abandoned blind reuse
- QA threshold weakening
- file-QA-only approval counting

============================================================
15. RETURN FORMAT
============================================================

Return:

A. OVERALL RESULT
One of:
- NO_DEFICIT_ASSETS_SAFE_REPAIRED_AND_PLAN_READY
- RESERVE_POOL_PLAN_READY
- RETRY_POOL_PLAN_READY
- REPLACEMENT_POOL_PLAN_READY
- REPLACEMENT_POOL_DRY_RUN_READY
- NO_DEFICIT_ASSETS_DIAGNOSED_REQUIRES_PATCH
- NO_DEFICIT_ASSETS_TRUE_EXHAUSTION
- MANUAL_POLICY_DECISION_REQUIRED
- APPROVED_EVIDENCE_REGRESSION
- MANUAL_FLAG_CLEAR_FAILED
- PLAN_FAILED
- BLOCKED

B. PREFLIGHT
- pending
- manual flag
- approved counts
- current blocker

C. CANDIDATE FUNNEL
- active primary eligible
- reserve eligible
- targeted retry eligible
- full retry eligible
- replacement eligible
- top exclusion reasons

D. SELECTED PATH
- active / reserve / retry / replacement / manual policy
- why

E. PATCH SUMMARY IF ANY
- files changed
- tests

F. MANUAL FLAG RESULT
- cleared/archived?
- archive path
- reason

G. PLAN RESULT
- created?
- chunkId
- canRun
- selected profiles
- promptTargetingVersion
- promptHash mismatches

H. NEXT PROMPT WRITTEN
- whether ./hermes_prompt.md updated
- next action summary

I. REPORTS WRITTEN

Important:
If image generation is run, report FAIL.
If manual flag is cleared before candidate path is proven, report FAIL.
If approved count drops below 74/222, report FAIL.
If distribution-audit is run after planning, report FAIL.
If recommender scripts are modified, report FAIL.
