# Seolleyeon Agent Instructions

## Project identity
Seolleyeon is a university-only, trust-based relationship platform.
It is not a lightweight dating app.
The tone is Quiet Romance / Clear Trust: calm, sincere, safe, campus-based, and serious.

## Current task family
AI profile image generation for the "AI에게 내 취향 알려주기" feature.

These images are synthetic profile assets for cold-start preference learning.
They are not decorative avatars and not face-rating game assets.

## Non-negotiable constraints
- Use `seolleyeon_ai_profile_prompt_v3.py` as the source of metadata-first prompts.
- Preserve profileId, assetId, shotType, storagePath, legacyStoragePath, promptHash, model, size, quality, status.
- Generate realistic adult Korean university student profile photos.
- Avoid childlike appearance, teenager look, school uniform, idol styling, influencer photoshoot, sexualized styling, nightlife, club scene, heavy retouching.
- Save images under `ai_image/`.
- Keep scripts resumable.
- Never overwrite completed images unless `--force` is passed.
- Do not modify recommender scripts unless explicitly asked.
- Do not hardcode API keys.
- Do not commit generated images unless explicitly asked.

## Required QA mindset
A generated image is acceptable only if:
- It looks like a real adult university student profile photo.
- It fits Seolleyeon's trust-based campus relationship tone.
- It does not feel like a Tinder-style face-rating card.
- The shot type is readable:
  - face_card: face and impression are clear.
  - silhouette_card: body frame and proportions are readable.
  - vibe_card: lifestyle and mood are readable.
- The image has no visible school logo, brand logo, watermark, readable text, distorted face, distorted hands, or unsafe styling.

## Preferred pipeline
1. Generate identity metadata and asset prompts.
2. Generate face_card first.
3. Generate silhouette_card and vibe_card using face_card as reference when possible.
4. Save raw images.
5. Run QA.
6. Copy approved images to approved and final gender/id folders.
7. Retry rejected or missing assets.
8. Write manifest and reports.

## Done when
- Dry run works without API calls.
- Smoke test generates 3 images.
- Pilot test generates 24 images.
- Full run generates 720 images.
- QA report exists.
- generation_manifest.jsonl contains every assetId.
- No existing recommender file was changed.
