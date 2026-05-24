Read ./hermes_goal_prompt.md first and obey it as the autonomous controller.
Then execute this task prompt.

$ultragoal "Diagnose no_deficit_assets_available despite remaining distribution deficit in the Seolleyeon AI profile image pipeline.

You are Hermes operating on the Seolleyeon AI PROFILE IMAGE pipeline.

This is a diagnosis-only task unless a clearly safe non-destructive code patch is proven necessary.

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
Do not clear manual flags.
Do not delete or quarantine files.
Do not modify recommender scripts.
Do not modify Git index.
Do not run file-qa --asset-id.
Do not run contact-sheets unless only inspecting existing report files.
Do not run active-visual-qa-all.
Do not run distribution-audit after planning.
Do not run bounded-chunk-plan again unless explicitly in dry-run/simulation mode and after diagnosis confirms it is safe.
Do not clear manual_review_required.flag.

Repo root:
C:/Users/Mickey/StudioProjects/dating-app-ai_profile_image

Known current blocker:
- OVERALL RESULT: HARD_STOP_NO_ELIGIBLE_ASSETS
- distribution deficits remain:
  - identities deficit: 175
  - images deficit: 525
  - female deficit: 118
  - male deficit: 57
- approvedCompleteIdentities: 65 / 240
- approvedImages: 195 / 720
- femaleApprovedCompleteIdentities: 2 / 120
- maleApprovedCompleteIdentities: 63 / 120
- pending-imagegen: resolved
- unresolved pending: false
- manual flag present:
  ai_image/manifests/manual_review_required.flag
- manual flag reason:
  no_deficit_assets_available
- bounded-chunk-status:
  canRun=false
  reasonCode=current_plan_not_executable
  reasons include:
  - current_plan_not_executable
  - manual_review_required
  - input_hash_changed:distributionAuditJsonSha256
  - input_mtime_newer:distributionAuditJson
  - manual_review_required_newer_than_plan
  - selected_identity_already_approved

Recent failed planner command:
python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --root . --production --max-assets 18 --max_identities 6 --force-replan --abandon-current

Planner failure:
- reasonCode: no_deficit_assets_available
- error: Distribution deficits remain, but no eligible bounded chunk assets are available.

Existing file-complete QA route:
- female_020~female_025 QA completed but no new approvals.
- female_026~female_031 whitelist/contact sheets produced imageCount=0 and empty assetIds.
- These are not actually safe file-complete QA candidates.
- active QA must not run on imageCount=0 / empty assetIds.

Important:
This is not a pending/imagegen infrastructure blocker.
This is not a stale prompt version blocker.
This is a planner/manifest eligibility blocker.

============================================================
1. OBJECTIVE
============================================================

Find the root cause of:

distribution deficit remains
but
bounded chunk planner reports no_deficit_assets_available.

This task should answer:

1. Are active manifests complete and current?
2. Are distribution deficits computed correctly?
3. Which identities/assets remain theoretically needed?
4. Why are candidate identities/assets filtered out?
5. Is the planner over-excluding candidates due to:
   - prior approvals
   - rejected identities
   - abandoned chunks
   - generated but unapproved assets
   - missing final files
   - stale promptTargetingVersion
   - reuse policy
   - gender/faceType/looks distribution constraints
   - imagegen_queue status
   - generation_manifest status
   - manual flag
   - current plan state
6. Is there a valid non-destructive patch to restore planning?
7. Or is operator-level policy decision required?

Allowed outcomes:
- DIAGNOSIS_COMPLETE
- PLANNER_ELIGIBILITY_PATCHED
- MANIFEST_REFRESH_REQUIRED
- DISTRIBUTION_TARGETS_EXHAUSTED
- REJECTED_POOL_EXHAUSTED
- QUEUE_MANIFEST_BUG_FOUND
- MANUAL_POLICY_DECISION_REQUIRED
- BLOCKED

============================================================
2. PREFLIGHT READ-ONLY STATUS
============================================================

Run:

python scripts/run_ai_image_pipeline_v3.py pending-status --root .
python scripts/run_ai_image_pipeline_v3.py bounded-chunk-status --root .
python scripts/run_ai_image_pipeline_v3.py completion-check --root .

Do not run generation.
Do not clear manual flag.

Read manual flag:
- ai_image/manifests/manual_review_required.flag

Record:
- pending unresolved?
- manual flag reason
- current chunkId
- canRun
- reasonCode
- approved counts
- completion failure reasons

If there is any active Hermes/Codex/imagegen process running:
- stop and return BLOCKED_ACTIVE_PROCESS.
- do not diagnose with mutating commands.

============================================================
3. READ REQUIRED FILES
============================================================

Read and summarize:

Core manifests:
- ai_image/manifests/identity_manifest.jsonl
- ai_image/manifests/ai_profile_specs_v3.jsonl
- ai_image/manifests/ai_profile_assets_v3.jsonl
- ai_image/manifests/imagegen_queue.jsonl
- ai_image/manifests/generation_manifest.jsonl
- ai_image/manifests/current_chunk_plan.json
- ai_image/manifests/current_chunk_state.json

QA / approval:
- ai_image/manifests/approved_identity_manifest.jsonl
- ai_image/manifests/rejected_identity_manifest.jsonl
- ai_image/manifests/asset_qa_manifest.jsonl
- ai_image/manifests/identity_qa_manifest.jsonl
- ai_image/manifests/file_qa_manifest.jsonl

Pending/history:
- ai_image/manifests/pending-imagegen.json
- ai_image/manifests/completed_pending_imagegen.jsonl
- ai_image/manifests/pending_resolution_manifest.jsonl
- ai_image/manifests/abandoned_chunk_manifest.jsonl

Distribution:
- ai_image/config/AI_IMAGE_DISTRIBUTION_TARGETS_V3.json
- ai_image/reports/latest_distribution_audit.json
- ai_image/reports/distribution_audit.json
- ai_image/reports/distribution_report.csv

Recent reports:
- ai_image/reports/pipeline_audit/existing_file_complete_qa_blocked_latest.json
- ai_image/reports/pipeline_audit/existing_file_complete_qa_blocked_latest.md
- ai_image/reports/pipeline_audit/hermes_autonomous_hard_stop_latest.json
- ai_image/reports/pipeline_audit/hermes_autonomous_hard_stop_latest.md
- latest v16/v15/v14/v13/v12 reports if present

Planner code:
- scripts/ai_image_pipeline_v3/bounded_batch_executor.py
- scripts/ai_image_pipeline_v3/distribution_selection.py
- scripts/ai_image_pipeline_v3/distribution_prepare.py
- scripts/ai_image_pipeline_v3/distribution_targets.py
- scripts/ai_image_pipeline_v3/cli.py
- scripts/ai_image_pipeline_v3/prepare.py
- scripts/ai_image_pipeline_v3/manifest.py
- scripts/ai_image_pipeline_v3/retry_plan.py

If any file is missing, report exact path.
Do not fabricate.

============================================================
4. BUILD ELIGIBILITY FUNNEL DIAGNOSTIC
============================================================

Construct a full funnel table from active identities/assets.

For each identity, compute:

- profileId
- gender
- faceType
- looksLevelBand
- eyewear
- season
- identity status:
  - approved
  - rejected
  - generated but unapproved
  - file-complete unreviewed
  - missing files
  - never generated
  - abandoned
  - failed
  - pending
  - planned/current
- asset IDs and shot types
- asset manifest exists?
- generation manifest status for each asset
- imagegen_queue status for each asset
- final file exists?
- raw file exists?
- file QA status
- asset QA status
- identity QA status
- approved/rejected manifest status
- promptTargetingVersion
- promptHash status
- whether selected in current/stale/abandoned chunk
- whether eligible for new generation under current planner
- if ineligible, exact reason(s)

Write:
- ai_image/reports/pipeline_audit/no_deficit_assets_eligibility_funnel.csv
- ai_image/reports/pipeline_audit/no_deficit_assets_eligibility_funnel.json

Also build summary counts by:
- gender
- faceType
- looksLevelBand
- eyewear
- status bucket
- ineligible reason
- deficit bucket

Required summary:
- total primary identities
- total reserve identities
- approved identities
- rejected identities
- file-complete unreviewed with real final files
- file-complete false positives with missing/null finalPath
- generated but not approved
- never generated
- eligible for new generation
- excluded by rejected identity
- excluded by abandoned chunk
- excluded by selected_identity_already_approved
- excluded by prompt version mismatch
- excluded by missing manifest row
- excluded by queue exhausted
- excluded by no deficit bucket

============================================================
5. DISTRIBUTION DEFICIT ANALYSIS
============================================================

Using distribution targets and approved manifest, compute current deficits.

Report:
- total approved identities/images
- female/male approved
- per faceType approved/deficit
- per looksLevelBand approved/deficit
- per eyewear approved/deficit
- per season approved/deficit
- combined buckets if planner uses combined constraints

Then compare deficits to candidate pools.

For every deficit bucket, report:
- target count
- approved count
- deficit count
- candidate identity count
- candidate asset count
- why candidates are ineligible

Determine:
- Is the deficit mostly female?
- Are female candidates missing from active manifests?
- Are female candidates all rejected/abandoned?
- Are female candidates in reserve but not active?
- Are candidate assets not in imagegen_queue?
- Are all assets already generated but rejected?
- Does planner refuse to regenerate failed/rejected identities?
- Is there an intended reserve activation path that has not been run?

Write:
- ai_image/reports/pipeline_audit/no_deficit_assets_distribution_gap_table.csv
- ai_image/reports/pipeline_audit/no_deficit_assets_distribution_gap_table.json

============================================================
6. EXISTING FILE-COMPLETE QA ROUTE ANALYSIS
============================================================

Analyze why female_026~female_031 were considered file-complete candidates but contact sheets had imageCount=0 / empty assetIds.

Read:
- ai_image/reports/pipeline_audit/existing_file_complete_qa_whitelist_20260524T1343Z.json
- ai_image/reports/chunks/existing_file_complete_qa_20260524T1343Z/contact_sheets/contact_sheet_index.json

For each female_026~female_031:
- asset manifest rows exist?
- generation manifest rows?
- finalPath present?
- final file exists?
- current_chunk_state asset status?
- file QA evidence?
- why whitelist thought file-complete?
- why contact sheet had empty assetIds?

If this is a bug:
- identify exact whitelist builder or file-complete detector code.
- Do not run QA.
- Patch only if safe and non-destructive.
- Add regression test:
  - file-complete whitelist excludes profiles whose finalPath is null or final file missing.
  - contact sheet imageCount=0 blocks active QA.

============================================================
7. PLANNER ROOT CAUSE CLASSIFICATION
============================================================

Classify root cause as one or more:

A. MANIFEST_REFRESH_REQUIRED
Active manifests/queue are stale or not aligned with latest prompt/version/distribution.

B. ELIGIBILITY_FILTER_TOO_STRICT
Planner excludes valid candidates due over-strict reuse/rejected/abandoned/current-plan logic.

C. RESERVE_POOL_NOT_ACTIVATED
Deficits require reserve identities/assets but planner does not activate reserve.

D. ALL_PRIMARY_CANDIDATES_EXHAUSTED
All available primary identities are approved/rejected/failed/abandoned, and policy disallows reuse/regeneration.

E. FILE_COMPLETE_DETECTOR_BUG
Existing file-complete QA route marks missing-file identities as file-complete.

F. QUEUE_MANIFEST_BUG
imagegen_queue/generation_manifest missing candidate rows despite specs/assets existing.

G. DISTRIBUTION_AUDIT_OR_TARGET_BUG
Distribution deficits are computed incorrectly or against incompatible target set.

H. MANUAL_POLICY_DECISION_REQUIRED
The only way forward requires relaxing policy:
- regenerate rejected identities
- activate reserve pool
- allow new identity creation
- modify distribution targets
- clear/rebuild generated dataset
- manually curate/approve needs_review identities

I. INCONCLUSIVE

For each root cause, provide evidence.

============================================================
8. SAFE PATCH RULES
============================================================

Only patch if the root cause is clearly a non-destructive code bug.

Allowed patch types:
- file-complete whitelist detector excludes missing/null finalPath.
- planner candidate funnel reports exact exclusion reasons.
- planner can activate reserve candidates if an existing reserve activation policy already exists but is not wired.
- imagegen_queue/generation_manifest sync bug, if fixable without deleting evidence.
- no_deficit_assets error report becomes more diagnostic.

Not allowed without operator approval:
- clear manual flag
- delete/quarantine files
- regenerate rejected identities by policy relaxation
- modify distribution targets
- fabricate new identities outside existing prepared manifests
- count needs_review as approved
- count file-QA-only assets as approved
- modify recommender scripts
- reset dataset

If a patch is made:
- add tests
- run py_compile
- run relevant tests
- do not run generation after patch in this task unless the prompt explicitly allows it, which it does not.

Suggested tests:
- tests/test_no_deficit_assets_diagnosis_v3.py
- tests/test_existing_file_complete_whitelist_requires_real_files_v3.py
- tests/test_distribution_candidate_pool_v3.py

Run relevant commands only if patching:
python -m py_compile scripts/ai_image_pipeline_v3/bounded_batch_executor.py scripts/ai_image_pipeline_v3/distribution_selection.py scripts/ai_image_pipeline_v3/contact_sheet.py scripts/ai_image_pipeline_v3/visual_verdict.py
python -m unittest tests.test_no_deficit_assets_diagnosis_v3 -q
python -m unittest tests.test_existing_file_complete_whitelist_requires_real_files_v3 -q
python -m unittest tests.test_distribution_candidate_pool_v3 -q

============================================================
9. REPORTS TO WRITE
============================================================

Write:
- ai_image/reports/pipeline_audit/no_deficit_assets_root_cause_latest.md
- ai_image/reports/pipeline_audit/no_deficit_assets_root_cause_latest.json
- ai_image/reports/pipeline_audit/no_deficit_assets_eligibility_funnel.csv
- ai_image/reports/pipeline_audit/no_deficit_assets_eligibility_funnel.json
- ai_image/reports/pipeline_audit/no_deficit_assets_distribution_gap_table.csv
- ai_image/reports/pipeline_audit/no_deficit_assets_distribution_gap_table.json
- ai_image/reports/pipeline_audit/existing_file_complete_false_positive_analysis.csv
- ai_image/reports/pipeline_audit/existing_file_complete_false_positive_analysis.json

If patched, also write:
- ai_image/reports/pipeline_audit/no_deficit_assets_patch_latest.md
- ai_image/reports/pipeline_audit/no_deficit_assets_patch_latest.json

JSON schema:
{
  "result": "DIAGNOSIS_COMPLETE | PLANNER_ELIGIBILITY_PATCHED | MANIFEST_REFRESH_REQUIRED | DISTRIBUTION_TARGETS_EXHAUSTED | REJECTED_POOL_EXHAUSTED | QUEUE_MANIFEST_BUG_FOUND | MANUAL_POLICY_DECISION_REQUIRED | BLOCKED",
  "currentStatus": {
    "approvedCompleteIdentities": 65,
    "approvedImages": 195,
    "femaleApprovedCompleteIdentities": 2,
    "maleApprovedCompleteIdentities": 63,
    "pendingUnresolved": false,
    "manualFlagReason": "no_deficit_assets_available"
  },
  "deficits": {
    "identities": 175,
    "images": 525,
    "female": 118,
    "male": 57
  },
  "candidateFunnel": {
    "totalPrimaryIdentities": null,
    "eligibleForNewGeneration": null,
    "fileCompleteUnreviewedReal": null,
    "fileCompleteFalsePositive": null,
    "excludedReasons": {}
  },
  "rootCause": {
    "classification": [],
    "summary": null
  },
  "patch": {
    "applied": false,
    "filesChanged": [],
    "testsPassed": null
  },
  "nextRecommendedAction": null
}

============================================================
10. RETURN FORMAT
============================================================

Return:

A. OVERALL RESULT
One of:
- DIAGNOSIS_COMPLETE
- PLANNER_ELIGIBILITY_PATCHED
- MANIFEST_REFRESH_REQUIRED
- DISTRIBUTION_TARGETS_EXHAUSTED
- REJECTED_POOL_EXHAUSTED
- QUEUE_MANIFEST_BUG_FOUND
- MANUAL_POLICY_DECISION_REQUIRED
- BLOCKED

B. CURRENT STATUS
- pending/manual/completion
- approved counts
- deficits

C. CANDIDATE FUNNEL
- total candidates
- eligible count
- main exclusion reasons
- file-complete false positives

D. ROOT CAUSE
- exact classification
- evidence

E. PATCH SUMMARY IF ANY
- files changed
- tests run

F. NEXT SAFE ACTION
- If safe patch fixed planner, recommend planning-only recheck, not generation.
- If manifest refresh required, recommend true dry-run prepare/active refresh.
- If manual policy decision required, list exact decisions needed.
- If reserve activation is needed, propose the safest reserve activation prompt.
- Do not recommend image generation unless a fresh canRun=true plan exists and manual flag is absent.

G. REPORTS WRITTEN

Important:
If image generation is run, report FAIL.
If active visual QA is run on empty contact sheets, report FAIL.
If manual flag is cleared, report FAIL.
If file-QA-only assets are counted as approved, report FAIL.
If protected recommender scripts are modified, report FAIL.
If Git index is modified, report FAIL.