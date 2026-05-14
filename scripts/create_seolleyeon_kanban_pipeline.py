#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path('C:/Users/Mickey/StudioProjects/dating-app-ai_profile_image')
WORKSPACE = f'dir:{ROOT.as_posix()}'
PROFILES = [
    'imgorch', 'imgprep', 'imgstate', 'imggen', 'imgrecover', 'imgfileqa',
    'imgvisual', 'imgidentity', 'imgaudit', 'imgfinal', 'imgsupervisor',
]

COMMON = r'''
Project constraints:
- Seolleyeon is a university-only trust-based relationship platform.
- AI profile images are synthetic cold-start preference-learning assets, not dating-game cards, decorative avatars, influencer content, or face-rating material.
- Use lib/ai_recommend_model/seolleyeon_ai_profile_prompt_v3_package/seolleyeon_ai_profile_prompt_v3.py as prompt/metadata source.
- Do not rewrite the prompt builder.
- Do not modify recommender scripts unless explicitly requested.
- Keep image pipeline code modular under scripts/ai_image_pipeline_v3/.
- Image generation mode is Codex built-in imagegen only.
- Do not call OpenAI Image API.
- Do not create Batch API JSONL.
- Do not require OPENAI_API_KEY for image generation.
- Use $imagegen for image creation.
- Treat $imagegen as interruptible.
- Always checkpoint pending-imagegen.json before image generation.
- Recover generated images from Codex generated image output before continuing.
- Asset identity is determined by pending-imagegen.json, not visual guesswork.
- Generate face_card before silhouette_card and vibe_card.
- Use completed face_card as same-person reference for other shots when possible.
- Save raw generated images under ai_image/raw/.
- Save final approved images under ai_image/{gender}/{numeric_id}/{shotType}.png.
- Save approved review copies under ai_image/approved/{assetId}.png.
- Save rejected attempts under ai_image/rejected/{assetId}__attemptXX.png.
- Write ai_image/manifests/generation_manifest.jsonl.
- Write ai_image/reports/generation_status.csv.
- Keep every script resumable.
- Never overwrite completed or approved images unless --force is passed.
- Do not hardcode API keys.
- Reject unsafe/off-brand images: childlike/teenager look, school uniform, idol trainee styling, influencer photoshoot, celebrity lookalike, sexualized/revealing outfit, nightlife/club/neon/luxury hotel scene, readable text/logo/watermark, heavy retouching, distorted hands/face/body/proportions.
Worker handoff requirements:
- Start by inspecting the Kanban task/comment thread and current repo state.
- Use terminal/file tools to verify outputs; do not rely on assumptions.
- If blocked by quota, imagegen unavailable, unresolved pending ambiguity, manual review, or destructive overwrite risk, add a clear Kanban comment and block instead of guessing.
- Complete with structured metadata: commands_run, files_verified, counts, status, blockers, next_recommended_task if any.
'''.strip()

TASKS = [
    {
        'key': 'T00', 'title': 'seolleyeon image pipeline T00 preflight and orchestration', 'assignee': 'imgorch', 'parents': [], 'max_runtime': '20m', 'skills': ['kanban-orchestrator'], 'priority': 100,
        'body': '''Run pipeline preflight for the full Seolleyeon AI profile image generation workflow.
Tasks:
1. Confirm current repo root and AGENTS.md constraints.
2. Confirm all required worker profiles exist: imgorch, imgprep, imgstate, imggen, imgrecover, imgfileqa, imgvisual, imgidentity, imgaudit, imgfinal, imgsupervisor.
3. Run and record: python scripts/run_ai_image_pipeline_v3.py supervisor-720 --root .
4. Run and record: python scripts/run_ai_image_pipeline_v3.py completion-check --root .
5. Inspect whether ai_image/manifests/pending-imagegen.json exists and whether it is resolved.
6. Summarize current pipeline state and exact blockers before generation.
Do not perform generation in this task.'''
    },
    {
        'key': 'T01', 'title': 'seolleyeon image pipeline T01 prepare prompt specs manifests queue', 'assignee': 'imgprep', 'parents': ['T00'], 'max_runtime': '30m', 'priority': 95,
        'body': '''Prepare prompt/spec/manifest/queue artifacts for the full image pipeline.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py prepare-720 --root .
2. Verify it uses lib/ai_recommend_model/seolleyeon_ai_profile_prompt_v3_package/seolleyeon_ai_profile_prompt_v3.py through scripts/ai_image_pipeline_v3/prompt_source.py.
3. Verify these files exist and are non-empty where expected:
   - ai_image/manifests/ai_profile_specs_v3.jsonl
   - ai_image/manifests/ai_profile_assets_v3.jsonl
   - ai_image/manifests/identity_manifest.jsonl
   - ai_image/manifests/imagegen_queue.jsonl
   - ai_image/manifests/generation_manifest.jsonl
   - ai_image/reports/generation_status.csv
4. Report specs/assets/manifest row counts.
Do not modify prompt builder or recommender files.'''
    },
    {
        'key': 'T02', 'title': 'seolleyeon image pipeline T02 validate manifest and queue integrity', 'assignee': 'imgprep', 'parents': ['T01'], 'max_runtime': '20m', 'priority': 90,
        'body': '''Validate manifest and queue integrity after preparation.
Tasks:
1. Verify generation_manifest.jsonl has unique assetId values.
2. Verify each profile has required shotTypes: face_card, silhouette_card, vibe_card.
3. Verify face_card sorts before dependent shots.
4. Verify silhouette_card/vibe_card rows have referenceAssetId and referenceLocalPath pointing to the matching face_card final path.
5. Verify required fields are preserved: profileId, assetId, shotType, storagePath, legacyStoragePath, promptHash, model, size, quality, status.
6. Verify imagegen_queue.jsonl has expected queueStatus values and reserve assets are standby unless active.
7. Verify generation_status.csv is consistent with generation_manifest.jsonl.
Block if integrity problems require human decision.'''
    },
    {
        'key': 'T03', 'title': 'seolleyeon image pipeline T03 pending checkpoint and recovery gate', 'assignee': 'imgstate', 'parents': ['T02'], 'max_runtime': '30m', 'priority': 88,
        'body': '''Own the pending checkpoint/recovery gate before generation.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py pending-status --root .
2. If unresolved pending-imagegen.json exists, run recover using the pending payload: python scripts/run_ai_image_pipeline_v3.py recover --root .
3. If pending names a specific asset and global recover is insufficient, run recover with --asset-id.
4. Re-run pending-status and completion-check.
5. Confirm there is no unresolved pending before downstream generation proceeds.
6. If pending is ambiguous, missing generated image output, or asset identity cannot be determined from pending-imagegen.json, block with exact assetId/reason.
Do not identify assets by visual guesswork.'''
    },
    {
        'key': 'T04', 'title': 'seolleyeon image pipeline T04 probe imagegen and visual QA capability', 'assignee': 'imgvisual', 'parents': ['T00'], 'max_runtime': '20m', 'priority': 87,
        'body': '''Probe Codex image input / active visual QA capability before generation/QA.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py active-visual-probe --root .
2. Verify ai_image/prompts visual verdict prompt files exist: VISUAL_VERDICT_ASSET_QA_PROMPT.md, VISUAL_VERDICT_IDENTITY_QA_PROMPT.md, VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md.
3. Report whether active visual QA is available.
4. If imagegen/visual input unavailable, quota-limited, permission denied, or requiring manual setup, block with exact tool output.'''
    },
    {
        'key': 'T05', 'title': 'seolleyeon image pipeline T05 create bounded chunk plan', 'assignee': 'imgaudit', 'parents': ['T03', 'T04'], 'max_runtime': '20m', 'priority': 85,
        'body': '''Create the next bounded generation chunk plan.
Tasks:
1. Run current distribution audit if useful: python scripts/run_ai_image_pipeline_v3.py distribution-audit --root .
2. Run: python scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --root . --production
3. Validate plan: python scripts/run_ai_image_pipeline_v3.py bounded-chunk-validate-plan --root .
4. Verify current_chunk_plan.json/current_chunk_state.json exist.
5. Confirm chunk limits: max 24 identities / 72 assets.
6. Confirm no surplus/forbidden distribution bucket is selected.
Block if plan cannot be safely created.'''
    },
    {
        'key': 'T06', 'title': 'seolleyeon image pipeline T06 run bounded image generation chunk', 'assignee': 'imggen', 'parents': ['T05'], 'max_runtime': '4h', 'priority': 80,
        'body': '''Run bounded image generation for the current chunk.
Tasks:
1. Confirm current_chunk_plan/current_chunk_state exist and are valid.
2. Run: python scripts/run_ai_image_pipeline_v3.py bounded-chunk-run --root .
3. If interrupted, run: python scripts/run_ai_image_pipeline_v3.py bounded-chunk-resume --root .
4. Ensure face_card is generated before silhouette_card/vibe_card.
5. Ensure dependent shots use face_card reference where possible.
6. Ensure every imagegen attempt writes/uses pending-imagegen.json checkpoint.
7. Do not call OpenAI Image API. Do not require OPENAI_API_KEY. Use $imagegen only.
8. If quota/rate limit/imagegen unavailable/manual review occurs, block with exact reason and current assetId.
Do not proceed to QA until generation run status is clear.'''
    },
    {
        'key': 'T07', 'title': 'seolleyeon image pipeline T07 recover generated images from Codex output', 'assignee': 'imgrecover', 'parents': ['T06'], 'max_runtime': '1h', 'priority': 78,
        'body': '''Recover generated images from Codex generated image output.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py recover --root .
2. If the current pending asset needs specific handling, run recover with --asset-id from pending payload.
3. Verify raw images land under ai_image/raw/{assetId}__attemptXX.png.
4. Verify generation_manifest.jsonl localPath/attemptCount/status are updated.
5. Verify completed_pending_imagegen.jsonl receives the recovered pending entry.
6. Re-run pending-status and ensure no unresolved pending remains.
Block if generated image output is missing or ambiguous.'''
    },
    {
        'key': 'T08', 'title': 'seolleyeon image pipeline T08 run file QA and manifest path QA', 'assignee': 'imgfileqa', 'parents': ['T07'], 'max_runtime': '30m', 'priority': 75,
        'body': '''Run file-level QA and manifest/path sanity checks.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py file-qa --root .
2. Verify checks for missing image, minimum file size, decode, format, dimensions, vertical aspect ratio.
3. Verify manifest integrity checks: duplicate assetId, duplicate finalPath, path gender/numericId/shotType mismatch, missing required shot, unresolved pending.
4. Record counts: checked, approved/file_passed, needs_manual_review, rejected, missing.
5. If file_rejected/missing appears, list assetIds and reasonCodes.
Do not perform semantic visual approval here; that belongs to visual QA.'''
    },
    {
        'key': 'T09', 'title': 'seolleyeon image pipeline T09 generate contact sheets for visual QA', 'assignee': 'imgvisual', 'parents': ['T08'], 'max_runtime': '30m', 'priority': 72,
        'body': '''Generate contact sheets for visual QA.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py contact-sheets --root .
2. Verify contact sheet outputs exist under ai_image/reports or configured contact sheet locations.
3. Generate/confirm chunk, identity, or grouped sheets needed for asset/identity/distribution visual QA.
4. Record output paths and image counts in completion metadata.'''
    },
    {
        'key': 'T10', 'title': 'seolleyeon image pipeline T10 run visual asset QA and apply verdicts', 'assignee': 'imgvisual', 'parents': ['T09'], 'max_runtime': '2h', 'priority': 70,
        'body': '''Run visual asset QA and apply verdicts.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py active-visual-asset-qa --root .
2. Run: python scripts/run_ai_image_pipeline_v3.py apply-visual-asset-qa --root .
3. Verify ai_image/manifests/asset_qa_manifest.jsonl is created/updated.
4. Verify ai_image/reports/visual_verdict/asset_qa_latest.json exists if active QA succeeded.
5. Reject or mark needs_review for childlike/teenager, school uniform, idol/influencer, celebrity lookalike, sexualized styling, nightlife/club/neon/luxury hotel, readable logo/text/watermark/school name, heavy retouching, distorted face/hands/body/proportions.
6. Verify shotType readability: face_card face/impression clear, silhouette_card body frame/proportions readable, vibe_card lifestyle/mood readable.
Block if visual judgment cannot be completed without human review.'''
    },
    {
        'key': 'T11', 'title': 'seolleyeon image pipeline T11 run visual identity QA and apply verdicts', 'assignee': 'imgidentity', 'parents': ['T10'], 'max_runtime': '1h', 'priority': 68,
        'body': '''Run identity consistency QA and apply verdicts.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py active-visual-identity-qa --root .
2. Run: python scripts/run_ai_image_pipeline_v3.py apply-visual-identity-qa --root .
3. Verify ai_image/manifests/identity_qa_manifest.jsonl is updated.
4. Verify approved_identity_manifest.jsonl and rejected_identity_manifest.jsonl updates if produced.
5. Confirm each profile's face_card, silhouette_card, vibe_card appear to be the same adult person and maintain Seolleyeon tone.
6. Mark identity approved/rejected/needs_review according to visual verdict outputs.
Block if identity same-person consistency needs manual review.'''
    },
    {
        'key': 'T12', 'title': 'seolleyeon image pipeline T12 run distribution audit', 'assignee': 'imgaudit', 'parents': ['T11'], 'max_runtime': '30m', 'priority': 65,
        'body': '''Run distribution-level QA/audit.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py active-visual-distribution-qa --root .
2. Run: python scripts/run_ai_image_pipeline_v3.py apply-visual-distribution-audit --root .
3. Run: python scripts/run_ai_image_pipeline_v3.py distribution-audit --root .
4. Verify ai_image/reports/latest_distribution_audit.json exists/updates.
5. Report approvedCompleteIdentityCount, approvedImageCount, female/male counts, deficit/surplus buckets, forbidden bucket issues, needsManualReview.
Targets: 240 approved complete identities, 720 approved images, 120 female identities, 120 male identities.'''
    },
    {
        'key': 'T13', 'title': 'seolleyeon image pipeline T13 decide retry reserve or next chunk loop', 'assignee': 'imgaudit', 'parents': ['T12'], 'max_runtime': '30m', 'skills': ['kanban-orchestrator'], 'priority': 62,
        'body': '''Decide whether to retry assets, activate reserve identities, create another chunk cycle, or proceed to finalization.
Tasks:
1. Inspect latest distribution audit, generation_manifest, asset_qa_manifest, identity_qa_manifest, rejected_identity_manifest, retry_manifest if present.
2. Run reconcile if appropriate: python scripts/run_ai_image_pipeline_v3.py bounded-chunk-reconcile --root . --apply
3. If failed/missing/rejected assets are retryable and under max attempts, create follow-up Kanban tasks assigned to imggen/imgrecover/imgfileqa/imgvisual as needed.
4. If target distribution still has deficits, create the next bounded chunk cycle tasks: plan -> run -> recover -> file QA -> contact sheets -> asset QA -> identity QA -> distribution audit -> decision.
5. If reserve activation is needed, create reserve/reconcile task and document target buckets.
6. If manual review is required, block with exact report path and reason.
7. If all targets are satisfied, complete and hand off to finalization.
This task is the loop controller; use kanban_create for follow-up cards rather than trying to do all future chunks in one run.'''
    },
    {
        'key': 'T14', 'title': 'seolleyeon image pipeline T14 final approved copy and finalize', 'assignee': 'imgfinal', 'parents': ['T13'], 'max_runtime': '30m', 'priority': 60,
        'body': '''Finalize approved image outputs.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py bounded-chunk-finalize --root .
2. Verify approved review copies exist under ai_image/approved/{assetId}.png for approved assets.
3. Verify final app-facing files exist under ai_image/{gender}/{numericId}/{shotType}.png.
4. Verify rejected attempts remain under ai_image/rejected/{assetId}__attemptXX.png.
5. Verify generation_manifest.jsonl and generation_status.csv reflect final statuses and paths.
6. Do not overwrite approved/completed images unless --force was explicitly authorized; if force seems needed, block.'''
    },
    {
        'key': 'T15', 'title': 'seolleyeon image pipeline T15 final completion check and supervisor report', 'assignee': 'imgsupervisor', 'parents': ['T14'], 'max_runtime': '20m', 'priority': 58,
        'body': '''Run final completion gate and supervisor report.
Tasks:
1. Run: python scripts/run_ai_image_pipeline_v3.py completion-check --root .
2. Run: python scripts/run_ai_image_pipeline_v3.py supervisor-720 --root .
3. Completion must pass with no unresolved_pending_imagegen, no missing_visual_verdict, no invalid_counted_identity, no distribution_mismatch.
4. Report final counts: approved complete identities, approved images, female/male approved identities, rejected identities, resolved pending count.
5. If completion failed, create or recommend precise follow-up Kanban tasks by failureReason and block/complete accordingly.
6. If completion passed, complete with final artifact paths and summary.'''
    },
]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    print('+', ' '.join(cmd))
    cp = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if cp.stdout:
        print(cp.stdout.rstrip())
    if cp.stderr:
        print(cp.stderr.rstrip(), file=sys.stderr)
    if check and cp.returncode != 0:
        raise SystemExit(cp.returncode)
    return cp


def profile_exists(profile_list_output: str, name: str) -> bool:
    return re.search(rf'(^|\s){re.escape(name)}(\s|$)', profile_list_output) is not None


def safe_key(title: str) -> str:
    return 'seolleyeon-ai-image-v3:' + re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')


def create_task(task: dict, ids: dict[str, str]) -> str:
    body = task['body'].strip() + '\n\n' + COMMON
    cmd = [
        'hermes', 'kanban', 'create', task['title'],
        '--assignee', task['assignee'],
        '--workspace', WORKSPACE,
        '--max-runtime', task['max_runtime'],
        '--priority', str(task.get('priority', 0)),
        '--body', body,
        '--idempotency-key', safe_key(task['title']),
        '--json',
    ]
    for parent_key in task.get('parents', []):
        cmd += ['--parent', ids[parent_key]]
    for skill in task.get('skills', []):
        cmd += ['--skill', skill]
    cp = run(cmd)
    payload = json.loads(cp.stdout)
    return str(payload.get('task_id') or payload['id'])


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    cp = run(['hermes', 'profile', 'list'])
    existing_profiles = cp.stdout
    for profile in PROFILES:
        if profile_exists(existing_profiles, profile):
            print(f'profile exists: {profile}')
        else:
            run(['hermes', 'profile', 'create', profile, '--clone'])
    run(['hermes', 'kanban', 'init'])

    ids: dict[str, str] = {}
    for task in TASKS:
        tid = create_task(task, ids)
        ids[task['key']] = tid
        print(f'{task["key"]}={tid} {task["assignee"]} {task["title"]}')

    manifests = ROOT / 'ai_image' / 'manifests'
    manifests.mkdir(parents=True, exist_ok=True)
    graph_path = manifests / 'kanban_pipeline_task_graph.json'
    graph_path.write_text(json.dumps(ids, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    cp = run(['hermes', 'kanban', 'list', '--json'])
    list_path = manifests / 'kanban_pipeline_task_list_latest.json'
    list_path.write_text(cp.stdout, encoding='utf-8')

    dispatch = run(['hermes', 'kanban', 'dispatch', '--dry-run', '--max', '5', '--json'], check=False)
    dispatch_path = manifests / 'kanban_pipeline_dispatch_dry_run_latest.json'
    dispatch_path.write_text(dispatch.stdout or '', encoding='utf-8')

    print('\nCreated/verified Seolleyeon AI image Kanban pipeline.')
    print(f'Task graph: {graph_path}')
    print(f'Task list: {list_path}')
    print(f'Dispatch dry run: {dispatch_path}')
    print(json.dumps(ids, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
