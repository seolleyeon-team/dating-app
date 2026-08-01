# Avatar Full Pipeline Audit Map

Generated: 2026-05-26

Production-ready: false

## Project Guard

- gcloud account: `seolleyeon.official@gmail.com`
- gcloud project: `seolleyeon-final`
- Firebase active project: `seolleyeon-final`
- Production project `seolleyeon`: not deployed to, not mutated.

## Pipeline Stages

1. Flutter source selection
   - `lib/features/onboarding/screens/photo_upload_screen.dart`
   - `lib/services/avatar_source_photo_service.dart`
   - User source photos are queued as `avatar_generation_queued:<jobId>` tokens, not public URLs.

2. Upload callable
   - `functions/src/avatarMedia.ts`
   - Callable: `uploadAvatarSourcePhoto`
   - Authenticates Firebase user, strips EXIF, normalizes JPEG, blocks approved-avatar users, writes private source storage, updates current source/job fields, writes `avatarJobs`, and enqueues Cloud Tasks.

3. Private media state
   - Firestore: `userPrivateMedia/{uid}`
   - Fields: `sourcePhotos[]`, `currentAvatarSourcePhotoId`, `currentAvatarJobId`, `avatarSourceSelectionVersion`, `photoConsent`, `chatRealPhoto`, `clip`.
   - Client read/write denied by `firestore.rules`.

4. Job and queue
   - Firestore: `avatarJobs/{jobId}`
   - Fields: `uid`, `sourcePhotoIds`, `sourcePhotoRefs`, `status`, `queueMode`, `queueStatus`, `avatarSourceSelectionVersion`, `cost`, `sourceAnalysis`, `referencePreprocess`.
   - Queue mode: `cloud_tasks` in staging.
   - Queue: `avatar-generation`, region `asia-northeast3`, max concurrency 1, dispatch rate 1/sec.

5. Worker
   - Cloud Run service: `seolleyeon-avatar-worker`
   - Region: `asia-southeast1`
   - Revision: `seolleyeon-avatar-worker-00033-8gs`
   - Endpoint: `/tasks/avatar-generation`
   - Auth: Cloud Run IAM, task invoker service account.
   - Runtime guardrails: max instances 1, concurrency 1, timeout 900s, dry run false, privacy preprocess true, background neutralization true.

6. Current source/job validation
   - Worker: `lib/ai_recommend_model/avatar_generation/worker.py`
   - Functions boundary: `functions/src/avatarApproval.ts`
   - Contract: requested `jobId` must match `currentAvatarJobId`, job source IDs must include `currentAvatarSourcePhotoId`, current source entry must be active/current, and selection version must match when present.

7. Source analysis
   - `lib/ai_recommend_model/avatar_generation/analysis/`
   - Detects no face, face too small, primary face, small background faces, and multi-primary rejection.
   - Stored fields include `primaryFaceBbox`, `primaryFaceConfidence`, `secondaryFaceCount`, `largeSecondaryFaceCount`, `backgroundFaceRisk`.
   - Raw landmarks and embeddings are not persisted.

8. Trait card
   - `lib/ai_recommend_model/avatar_generation/trait_card/`
   - Florence-2 path is local; validator is enum-only.
   - Onboarding gender overrides image/model inferred gender.
   - Background/location/brand details are not prompt traits.

9. Reference preprocessing
   - `lib/ai_recommend_model/avatar_generation/preprocessing/reference.py`
   - Primary crop, privacy downsample/blur, secondary face neutralization, neutral background, optional SAM.
   - Metadata only: `referencePreprocess.primaryCropApplied`, `cropType`, `backgroundNeutralized`, `secondaryFacesNeutralized`, `textLogoNeutralized`.

10. FLUX generation
    - Worker main path sends privacy-processed reference to FLUX.2-klein-4B.
    - Unsupported `negative_prompt` is filtered.
    - Direct adapter path now applies privacy preprocessing before generation.

11. QA, rerank, preview policy
    - `qa.py`, `rerank.py`, `preview_policy.py`, `adaptive_generation.py`
    - QA statuses: `hard_pass`, `soft_pass`, `needs_review`, `hard_reject`.
    - Hard rejects are never previewed.
    - Soft-pass fill is allowed only through central preview policy.
    - QA fields include `backgroundLeakageRisk`, `secondaryFaceLeakageRisk`, `textLogoWatermarkRisk`, `cropIsolationQuality`, `primaryFaceConfidence`.

12. Candidate storage and preview
    - Candidate docs: `avatarCandidates`
    - Temp bucket: `seolleyeon-final-avatar-temp`
    - Callable: `getAvatarJobCandidates`
    - Response returns only `candidateId`, runtime preview image payload, and safe summary. It does not return source refs, GCS paths, signed source URLs, or hard-reject candidates.

13. Approval
    - Callable: `approveAvatarCandidate`
    - Only owned, preview-allowed candidates from the current job can be approved.
    - Copies temp candidate to approved avatar bucket and writes `users/{uid}.avatar.status = approved`, `approvedAvatarUrl`, `approvedAvatarStoragePath`, `onboarding.avatarUrls`.
    - Approved lock blocks normal upload/change/delete/regenerate.

14. Public display
    - `lib/shared/utils/profile_display_image_resolver.dart`
    - Uses approved avatar URL first and sanitized `onboarding.avatarUrls` fallback only.
    - Does not use `onboarding.photoUrls` or top-level `photoUrls`.
    - Rejects `gs://`, `gcs://`, signed markers, `/source/`, `/jobs/`, `/candidates/`, and private/temp/chat bucket URLs including virtual-hosted forms.

15. Chat real photo
    - Separate backend-authorized flow.
    - `functions/src/chatRealPhoto.ts`
    - Avatar fallback remains approved-avatar based.

## Storage Buckets

- Private source: `seolleyeon-final-private-source-photos`
- Temp candidates: `seolleyeon-final-avatar-temp`
- Approved avatars: `seolleyeon-final-approved-avatars`
- Chat real photo: `seolleyeon-final-chat-profile-photos`

Private/temp/chat buckets had no public IAM binding in the staging read audit. Private/temp source paths are denied to clients by Storage rules.

## Known Staging Evidence

- Worker revision: `seolleyeon-avatar-worker-00033-8gs`
- Authenticated `/readyz`: 200
- Unauthenticated `/readyz`: 403
- Complex background live matrix: `PASS_COMPLEX_BACKGROUND_LIVE_MATRIX`
- Positive preview_ready: 4/4
- Positive approval: 4/4
- Negative two-primary-faces: rejected as multi-face, no approval
- Evidence files:
  - `out/complex_background_matrix_live_report.json`
  - `out/complex_background_matrix_live_report.csv`
  - `out/avatar_full_pipeline_e2e_audit.json`
  - `out/avatar_full_pipeline_e2e_audit.csv`

## Remaining Blockers

- Profile edit can still queue a pre-approval avatar source upload without a local candidate approval UI path. Product decision required: route to onboarding approval flow or disable this profile-edit upload path.
- Fresh live current-source/job A/B supersede smoke was not run because this audit did not have a new exact-consented UID/photo set.
- App Check enforcement mode could not be verified through the REST services endpoint due to HTTP 403.
- Real OCR/logo source-risk detection remains a watch item; current preprocessing consumes coarse risk flags and QA catches leakage.
- Production-ready remains false.
