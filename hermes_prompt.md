Read ./hermes_goal_prompt.md first and obey it as the autonomous controller.
Then execute this task prompt.

$ultragoal "Diagnose the live manual-review blocker no_deficit_assets_available before any further Seolleyeon AI profile image planning or generation.

You are Hermes operating on the Seolleyeon AI PROFILE IMAGE pipeline.

This is a diagnosis-only task unless a clearly safe non-destructive code/reporting patch is proven necessary.

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
Do not run bounded-chunk-plan as a mutating production command in this diagnosis task.
Do not run prepare-720 non-dry-run.

Repo root:
C:/Users/Mickey/StudioProjects/dating-app-ai_profile_image

Live state from the blocked planning preflight:
- pending-imagegen exists but is resolved; unresolved pending=false.
- manualReviewRequired=true.
- manual flag path: ai_image/manifests/manual_review_required.flag.
- manual flag reason: no_deficit_assets_available.
- current chunkId: chunk_20260524T105307Z.
- current chunk status: finalized.
- current chunk selectedIdentityCount: 2.
- current chunk selectedAssetCount: 6.
- current chunk assetStates: 6 file_qa_passed.
- current canRun=false.
- current reasonCode=current_plan_not_executable.
- current staleReasons include input_hash_changed:distributionAuditJsonSha256, input_mtime_newer:distributionAuditJson, manual_review_required_newer_than_plan, selected_identity_already_approved.
- active manifest promptTargetingVersion=face_type_looks_level_targeting_v22 across 840 active asset rows.
- approvedCompleteIdentities=65 / 240.
- approvedImages=195 / 720.
- femaleApprovedCompleteIdentities=2 / 120.
- maleApprovedCompleteIdentities=63 / 120.
- completion-check failureReasons: manual_review_required, distribution_mismatch.

Objective:
Find the root cause of no_deficit_assets_available while distribution deficits remain, and determine the next safe non-destructive path to restore planning. Do not clear the manual flag and do not generate images.

Required preflight commands:
python scripts/run_ai_image_pipeline_v3.py pending-status --root .
python scripts/run_ai_image_pipeline_v3.py bounded-chunk-status --root .
python scripts/run_ai_image_pipeline_v3.py completion-check --root .

Read and inspect, without deleting or mutating:
- ai_image/manifests/manual_review_required.flag
- ai_image/manifests/current_chunk_plan.json
- ai_image/manifests/current_chunk_state.json
- ai_image/manifests/ai_profile_specs_v3.jsonl
- ai_image/manifests/ai_profile_assets_v3.jsonl
- ai_image/manifests/imagegen_queue.jsonl
- ai_image/manifests/generation_manifest.jsonl
- ai_image/manifests/approved_identity_manifest.jsonl
- ai_image/manifests/rejected_identity_manifest.jsonl
- ai_image/manifests/asset_qa_manifest.jsonl
- ai_image/manifests/identity_qa_manifest.jsonl
- ai_image/manifests/file_qa_manifest.jsonl
- ai_image/manifests/abandoned_chunk_manifest.jsonl
- ai_image/reports/latest_distribution_audit.json
- ai_image/reports/distribution_audit.json
- ai_image/reports/distribution_report.csv
- recent ai_image/reports/pipeline_audit/*no_deficit* and existing_file_complete* reports if present

Build a candidate/eligibility diagnostic that answers:
1. Are active manifests complete and current for v22?
2. Are distribution deficits computed correctly?
3. Which remaining identities/assets are theoretically needed?
4. Why are candidates filtered out?
5. Is the blocker due to rejected pool exhaustion, abandoned chunk exclusion, queue/generation manifest mismatch, reserve pool not activated, file-complete false positives, distribution target mismatch, or manual policy?
6. Is there a safe non-destructive patch or only an operator policy decision?

Write:
- ai_image/reports/pipeline_audit/no_deficit_assets_root_cause_latest.md
- ai_image/reports/pipeline_audit/no_deficit_assets_root_cause_latest.json
- ai_image/reports/pipeline_audit/no_deficit_assets_eligibility_funnel.csv
- ai_image/reports/pipeline_audit/no_deficit_assets_eligibility_funnel.json
- ai_image/reports/pipeline_audit/no_deficit_assets_distribution_gap_table.csv
- ai_image/reports/pipeline_audit/no_deficit_assets_distribution_gap_table.json
- ai_image/reports/pipeline_audit/existing_file_complete_false_positive_analysis.csv
- ai_image/reports/pipeline_audit/existing_file_complete_false_positive_analysis.json

Update autonomous loop reports:
- ai_image/reports/pipeline_audit/hermes_autonomous_loop_latest.json
- ai_image/reports/pipeline_audit/hermes_autonomous_loop_latest.md
- ai_image/reports/pipeline_audit/hermes_autonomous_loop_events.jsonl

Allowed outcomes:
- DIAGNOSIS_COMPLETE
- MANIFEST_REFRESH_REQUIRED
- DISTRIBUTION_TARGETS_EXHAUSTED
- REJECTED_POOL_EXHAUSTED
- QUEUE_MANIFEST_BUG_FOUND
- PLANNER_ELIGIBILITY_PATCHED
- MANUAL_POLICY_DECISION_REQUIRED
- BLOCKED

Return format:
A. OVERALL RESULT
B. CURRENT STATUS
C. CANDIDATE FUNNEL
D. ROOT CAUSE
E. PATCH SUMMARY IF ANY
F. NEXT SAFE ACTION
G. REPORTS WRITTEN

Important failure conditions:
If image generation is run, report FAIL.
If active visual QA is run on empty contact sheets, report FAIL.
If manual flag is cleared, report FAIL.
If file-QA-only assets are counted as approved, report FAIL.
If protected recommender scripts are modified, report FAIL.
If Git index is modified, report FAIL.
"
