# 설레연 아바타 이미지 생성 파이프라인 전체 검수 결과

## 1. 결론

- 상태: `PASS_PARTIAL`
- production-ready 여부: 아니오
- internal canary 가능 여부: 제한적으로 가능. 단, profile edit 업로드 경로와 fresh current-source/job live smoke blocker를 먼저 해소하는 편이 안전하다.
- mini calibration 가능 여부: 조건부 가능. 기존 complex-background live matrix는 통과했지만, 새 UID/사진 동의 세트로 current-source/job A/B supersede live smoke가 필요하다.
- 남은 blocker:
  - profile edit에서 승인 UI 없이 avatar source upload/job queue가 가능하다.
  - fresh exact-consented UID/photo 세트가 없어 current-source/job A/B supersede live smoke를 실행하지 못했다.
  - App Check enforcement mode는 REST 403 때문에 live 설정 확인이 incomplete다.
  - OCR/logo source-risk 실검출은 watch item이다.

## 2. 전체 파이프라인 단계별 결과

1. Flutter source selection: PASS
   - 최신 `jobId/photoId/sourceSelectionVersion`을 상태로 보관하고 queued token은 URL이 아니다.
2. `uploadAvatarSourcePhoto`: PASS_LOCAL
   - approved avatar lock, EXIF strip, private source write, current source/job write, queue enqueue가 확인됐다.
3. private source storage: PASS
   - source bucket은 private이며 Flutter public display에 노출되지 않는다.
4. `userPrivateMedia` current source/job: PASS
   - current fields와 selection version contract가 Functions/worker 양쪽에서 검사된다.
5. `avatarJobs` queued: PASS
   - queued doc와 Cloud Tasks enqueue 경로가 확인됐다.
6. Cloud Tasks enqueue: PASS_STAGING_READ
   - `cloud_tasks`, OIDC service account, queue concurrency 1.
7. worker auth/readyz: PASS_STAGING_READ
   - authenticated `/readyz=200`, unauthenticated `/readyz=403`.
8. current source/job validation: PASS_LOCAL
   - stale preview/approval 경계가 차단되도록 Functions를 보강했다.
9. source analysis: PASS_LOCAL
   - primary face, small background face, two-primary rejection test가 통과했다.
10. trait card: PASS_LOCAL
   - enum validator, onboarding gender override, raw landmark/embedding non-persistence 확인.
11. background neutralization: PASS_LOCAL_AND_STAGING_EVIDENCE
   - complex matrix A/B/C/E에서 neutralization metadata와 QA low risk 확인.
12. FLUX generation: PASS_LOCAL
   - main path와 direct adapter path 모두 privacy-processed reference를 사용한다.
13. QA/rerank: PASS_LOCAL
   - hard reject 미노출, soft-pass fill, leakage risk fields 확인.
14. candidate storage: PASS
   - temp bucket candidate만 preview source로 사용한다.
15. preview API: PASS_LOCAL
   - current job만 후보 반환, private refs 미반환.
16. Flutter candidate popup: PASS_LOCAL
   - 1-4 candidates 처리와 approval navigation test 통과.
17. approval: PASS_LOCAL
   - current job candidate만 approved bucket copy 가능.
18. approved avatar public display: PASS_LOCAL
   - approved avatar/onboarding.avatarUrls만 사용.
19. approved lock: PASS_LOCAL_AND_STAGING_EVIDENCE
   - accepted live matrix lock retest rejected.
20. privacy QA: PASS_LOCAL
   - media privacy QA dry-run 통과.

## 3. Staging Live Evidence

- project: `seolleyeon-final`
- worker revision: `seolleyeon-avatar-worker-00033-8gs`
- functions deployed: 이번 audit에서는 배포하지 않음
- E2E jobs: existing complex matrix 5 cases
- preview_ready count: 4/4 positive cases
- approval count: 4/4 positive cases
- lock retest count: 4/4 rejected

## 4. Current Source/Job Contract

- upload A/B supersede result: live not run, BLOCKED_BY_PARTICIPANTS
- stale job rejection: PASS_LOCAL
- current job processing: PASS_LOCAL
- approved lock: PASS_LOCAL_AND_STAGING_EVIDENCE

## 5. Complex Background Matrix

- A simple: PASS, preview_ready, 4 candidates, approved
- B complex: PASS, preview_ready, 4 candidates, approved
- C small background face: PASS, preview_ready, 4 candidates, approved
- D two primary faces: PASS_NEGATIVE, failed safely as multi-face, no approval
- E text/logo: PASS_WITH_WATCH, preview_ready and approved, QA text/logo risk low
- background neutralization: PASS, positive cases `backgroundNeutralized=true`

## 6. QA/Rerank

- hardPass/softPass/needsReview/hardReject: policy path covered locally
- tooIdentifiable: reliable face similarity required for hard reject
- childlike/beautification: QA/rerank tests covered
- background/text/logo risks: fields present and live matrix risk low
- preview policy: hard reject never previewed; soft pass centralized

## 7. Trait Card / MediaPipe / Florence

- MediaPipe availability: worker/source analyzer path covered locally
- raw landmarks stored? false
- expanded trait coverage: PASS_LOCAL
- gender source: onboarding/backend field only
- Florence status: local model adapter path inspected and tested through trait extraction tests
- SAM optional status: optional/fallback path covered locally; live matrix had `samSeconds=0`

## 8. Cost/Timing

- totalWorkerSeconds p50/p95: p50 13.627s, p95 392.749s from existing cost report
- generationSeconds p50/p95: p50 38.095s, p95 38.227s
- estimatedUsd total: 0.745705 for existing report
- cost per approved avatar: 0.186426 USD in existing cost report
- retry/deadline: stale lease, selection-version mismatch, smoke dry-run, and deadline guards covered locally
- cost guard status: kill switch and disable-new-generation paths covered locally

## 9. Privacy/Security

- source refs in Flutter: no unsafe runtime exposure found
- private buckets in Flutter: defensive regex only; display rejects private/temp/chat buckets
- signed URL persistence: no client persistence found
- raw landmarks/embeddings: not stored in public/client scope
- `userPrivateMedia`/`clipEmbeddings`: Firestore rules deny client access
- `onboarding.photoUrls` fallback: removed from public display resolver
- external image API: no real avatar external image API use found
- `qa_media_privacy`: PASS

## 10. Files Changed

- `functions/src/avatarApproval.ts`
- `functions/src/avatarApproval.test.ts`
- `functions/src/avatarMedia.ts`
- `lib/shared/utils/profile_display_image_resolver.dart`
- `test/profile_display_image_resolver_test.dart`
- `lib/features/onboarding/screens/photo_upload_screen.dart`
- `lib/features/onboarding/widgets/avatar_generation_messages.dart`
- `lib/features/onboarding/widgets/avatar_generation_models.dart`
- `lib/features/profile/screens/profile_edit_screen.dart`
- `lib/providers/auth_provider.dart`
- `lib/services/avatar_generation_client.dart`
- `lib/services/push_notification_service.dart`
- `lib/data/models/user/user_profile_model.dart`
- `lib/data/models/matching/match_model.dart`
- `lib/ai_recommend_model/avatar_generation/worker.py`
- `lib/ai_recommend_model/avatar_generation/model_adapters/flux2_klein.py`
- `scripts/avatar_worker_smoke_test.py`
- `scripts/avatar_worker_staging_smoke.py`
- `scripts/staging_avatar_live_setup.ps1`
- `tests/test_avatar_generation_worker.py`
- `tests/test_avatar_trait_card.py`
- `test/avatar_generation_client_test.dart`
- `docs/staging-bootstrap/seolleyeon-final-resource-map.md`
- `out/avatar_full_pipeline_e2e_audit.json`
- `out/avatar_full_pipeline_e2e_audit.csv`

## 11. Commands Run

- `gcloud config get-value account`: PASS
- `gcloud config get-value project`: PASS
- `firebase use`: PASS
- `firebase projects:list`: PASS
- `npm --prefix functions run build`: PASS
- `npm --prefix functions test`: PASS, 51 tests
- `flutter analyze`: PASS
- `flutter test test/photo_upload_screen_avatar_flow_test.dart test/profile_display_image_resolver_test.dart test/chat_profile_photo_service_test.dart test/avatar_source_photo_service_test.dart test/avatar_generation_client_test.dart`: PASS, 46 tests
- `python -m compileall -q lib/ai_recommend_model/avatar_generation scripts tests`: PASS
- `.venv\Scripts\python.exe -m pytest -q tests`: PASS, 330 passed, 6 skipped
- `.venv\Scripts\python.exe scripts\qa_media_privacy.py --dry_run --fail_on_warning`: PASS

## 12. Remaining Blockers And Next Action

- P0 blockers: none found for current local privacy contract after fixes.
- P1 blockers:
  - Decide profile edit behavior: route to onboarding avatar approval flow or disable pre-approval source upload there.
  - Run fresh current-source/job A/B live smoke with exact UID/photo consent.
  - Verify App Check enforcement mode with sufficient IAM.
  - Add real local text/logo risk detector or local Florence risk pass for source analysis.
- calibration needs:
  - PR8.5 mini calibration can proceed only as a limited staging/internal canary after the profile-edit path and fresh current-source/job smoke are handled.
- recommended next PR: PR8.5 mini calibration 10-20 users after the above gates, not production canary.

설레연 아바타 생성은 source upload부터 approved avatar lock까지 currentAvatarSourcePhotoId/currentAvatarJobId 계약을 기준으로 수행되며, hard-reject 후보와 private source 정보는 사용자에게 노출되지 않아야 한다.
