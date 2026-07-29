---
name: seolleyeon-ai-profile-imagegen
description: Use this skill for Seolleyeon AI profile image generation, prompt asset batching, ai_image folder output, OpenAI Image API scripts, QA, retry, manifest, and synthetic profile asset workflows.
---

# Seolleyeon AI Profile Image Generation Skill

## Role
You are implementing and operating the Seolleyeon AI profile image generation pipeline.

This is for the "AI에게 내 취향 알려주기" feature.
The images are synthetic profile assets for recommendation cold-start preference learning.
They are not game assets, not influencer portraits, and not lightweight dating-app cards.

## Source of truth
Use `seolleyeon_ai_profile_prompt_v3.py`.
Do not replace the prompt builder unless explicitly asked.
It emits metadata-first identity specs and asset records for:
- face_card
- silhouette_card
- vibe_card

## Target count
Default target is 720 images:
- 240 identities
- 3 shots per identity

Default split:
- female_count = 120
- male_count = 120

## Output folder
All generated artifacts must live under `ai_image/`.

Required structure:
- ai_image/raw
- ai_image/approved
- ai_image/rejected
- ai_image/female
- ai_image/male
- ai_image/manifests
- ai_image/reports
- ai_image/references

## Required scripts
Implement or maintain:
- scripts/prepare_ai_image_assets_v3.py
- scripts/generate_ai_images_v3.py
- scripts/retry_ai_images_v3.py
- scripts/qa_ai_images_v3.py
- scripts/summarize_ai_images_v3.py
- scripts/upload_ai_images_firebase_v3.py
- scripts/run_ai_image_pipeline_v3.py

## Generation strategy
Prefer a 2-pass pipeline:
1. Generate face_card first.
2. Generate silhouette_card and vibe_card as same-person variations using the generated face_card as reference when the API supports reference image edits.

If the user explicitly asks for independent images or maximum throughput, use Batch API for `/v1/images/generations`.

## Image quality rules
Every prompt and script must preserve these constraints:
- realistic adult Korean university student
- natural smartphone profile photo
- campus-based trust platform tone
- no childlike appearance
- no teenager look
- no school uniform
- no idol trainee styling
- no influencer photoshoot
- no sexualized styling
- no swimsuit or lingerie
- no nightlife or club scene
- no readable university name
- no visible school logo
- no watermark

## Manifest requirements
Every asset must record:
- profileId
- numericId
- gender
- shotType
- assetId
- prompt
- promptHash
- model
- size
- quality
- outputPath
- rawPath
- finalPath
- legacyPath
- status
- error
- attempt
- createdAt

## Resume rules
- Skip existing completed files unless `--force` is set.
- Failed or missing assets must be retryable.
- Do not overwrite approved images unless `--force` is set.
- Keep generation_manifest.jsonl append-safe or rebuild-safe.

## Acceptance checks
Before full generation:
- dry run with 3 assets must pass
- smoke generation with 3 images must pass
- pilot generation with 24 images should pass
- QA report must be generated
