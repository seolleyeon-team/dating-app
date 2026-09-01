# Avatar production onboarding contract — photo requirement v1

Status: implemented in source, not yet deployed (see
`avatar-production-rollout-20260830.md` for gates).
Date: 2026-08-30.

## 1. Product contract

- `MIN_ONBOARDING_SOURCE_PHOTOS = 2` (`functions/src/onboardingPhotoRequirement.ts`).
- 신규/미완료 온보딩 사용자는 서버가 검증한 사진이 2장 이상 있어야
  아바타 생성 admission을 받을 수 있고, 승인된 아바타가 있어야 사진 단계를
  통과한다.
- 이미 온보딩을 완료한 기존 사용자는 재온보딩시키지 않는다. 이 요구는
  photo 단계에 도달하는 신규/미완료 사용자에게만 적용된다(승인된 아바타
  보유자는 `avatar.status == approved`로 통과).
- 어떤 실패(생성 불가, 큐 정지, 예산 소진)도 "사진 없이 통과" 경로로
  대체되지 않는다. 실패는 재시도 가능한 오류 UI로 표면화된다(fail-closed).

## 2. Client enforcement (`lib/features/onboarding/screens/photo_upload_screen.dart`)

- `_minRequiredPhotos`는 상수 2다. 빌드 플래그로 완화할 수 없다
  (`onboarding_feature_flags.dart`는 삭제됨 — 두 dart-define 플래그
  `REQUIRE_ONBOARDING_PHOTOS`, `ENABLE_ONBOARDING_AVATAR_GENERATION`은
  production 바이패스였다: 커밋 `0f6349a9`).
- 다음 버튼: 사진 0~1장 → disabled, 업로드 중 → disabled, 아바타 흐름
  진행 중 → disabled. 승인된 아바타 보유(서버 프로필 파생 `_avatarLocked`)만
  사진 수와 무관하게 진행 가능.
- 사진 pick 시점에는 슬롯별로 `uploadOnboardingPhoto` 콜러블(서버 검증
  업로드)만 수행하고, 아바타 소스 업로드(잠금 시작)는 "다음" 버튼 시점에
  수행한다. 이 순서가 과거 D-001의 "첫 사진 즉시 잠금 → 2장 요구 교착"을
  제거하고 `avatar-state-machine.md`의 "Generate pressed → upload_pending"
  계약과 일치한다.
- "다음" 연타 재진입 가드(`_isHandlingNext`) + 소스 업로드
  `clientRequestId` 고정(`_sourceUploadRequestId`)으로 클라이언트 레이스가
  중복 유료 생성으로 이어지지 않는다.
- `avatar_source_locked` 응답을 받으면 서버 상태를 다시 읽어 기존 job으로
  폴링을 잇는다(새 생성 없음).
- 원본 사진 URL은 클라이언트가 사용자 문서에 기록하지 않는다
  (`OnboardingSaveHelper.savePhotos` 호출 제거 — 해당 쓰기는 rules의
  `onboardingAvatarPhotoFieldsUnchanged` 가드에 의해 이미 거부되고 있었다).
  공개 가능한 값은 승인 시 서버가 쓰는 `onboarding.avatarUrls`뿐이다.

## 3. Server enforcement (`functions/src/onboardingPhotoRequirement.ts`)

- `uploadAvatarSourcePhoto`(= generation admission)가
  `assertMinimumOnboardingPhotoEvidence({userId})`를 호출한다.
- 증거는 Storage의 `users/{uid}/onboarding/photos/` prefix에 있는 객체 중
  size>0, `image/*`, 서버가 찍은 `ownerUid == uid`,
  `uploadKind == onboarding_profile_photo` 메타데이터를 가진 것만 센다.
  클라이언트가 제출한 카운트는 어떤 형태로도 신뢰하지 않는다.
- 미달 시 `failed-precondition` / `avatar_minimum_photos_required`
  (details: requiredPhotos, validPhotos).
- 증거 조회 실패 시 `internal` / `avatar_photo_evidence_unavailable`로
  fail-closed (성공으로 위조하지 않음).
- 기존 admission 계약(1개의 canonical source photo, deterministic
  photoId/jobId, source lock, Cloud Tasks dedup)은 변경하지 않았다.
  두 번째 사진은 온보딩 유효성 증거로만 쓰이며 생성 소스 선택/프롬프트에는
  관여하지 않는다(다중 레퍼런스 생성 알고리즘을 새로 만들지 않음).

## 4. Firestore rules

`users/{uid}.onboarding`의 서버 증거 필드를 클라이언트 쓰기 금지 목록에
추가했다 (`firestore.rules`의 `onboardingAvatarPhotoFieldsAbsent` /
`onboardingAvatarPhotoFieldsUnchanged`):

- `sourcePhotoUploadCount`, `sourcePhotoUploadStatus`,
  `sourcePhotoLastQueuedAt`, `avatarGenerationJobId`,
  `avatarSourceSelectionVersion`

회귀 테스트: `rules_tests/firestore.onboardingphotogate.test.mjs`.

## 5. Resume routing (`lib/services/onboarding_route_resolver.dart`)

사진 단계 통과 조건이 `sourcePhotoUploadCount > 0`(위조 가능, 클라이언트가
쓴 적도 없음)에서 **승인된 아바타 증거**(`avatar.status == approved` 또는
`onboarding.avatarUrls`의 안전한 URL)로 바뀌었다. 생성 진행 중/실패 상태는
사진 화면으로 복귀해 기존 job을 이어간다(중복 생성 없음).

## 6. Error codes (client-visible mapping)

| server code | client message |
| --- | --- |
| `avatar_minimum_photos_required` | 사진을 2장 이상 등록해주세요. |
| `avatar_generation_paused` / `avatar_budget_exceeded` / `avatar_generation_not_open` | 아바타 생성이 잠시 중단되어 있어요. 잠시 후 다시 시도해주세요. |
| `avatar_already_approved` | (서버 상태 재조회 후 진행 또는 잠금 안내) |
| `avatar_source_locked` | (기존 job으로 폴링 재개) |

## 7. Tests

- `test/photo_upload_screen_photo_requirement_test.dart` — 0/1/2장,
  2→1 삭제, 연타 멱등, 대표 원본 소실, 승인된 아바타 재방문.
- `test/photo_upload_screen_avatar_flow_test.dart` — "사진 없이는 다음
  단계로 넘어갈 수 없다"로 반전(과거 바이패스 고정 테스트 제거).
- `test/onboarding_route_resolver_avatar_gate_test.dart` — resume 게이트.
- `functions/src/onboardingPhotoRequirement.test.ts` — 서버 카운트/거부/
  fail-closed + admission wiring 소스 스캔.
- `rules_tests/firestore.onboardingphotogate.test.mjs` — 증거 필드 위조 거부.

## 8. Known limitations (v1)

- 클라이언트에서 사진을 지워도 Storage 객체는 남는다(서버 카운트는 "업로드된
  유효 사진이 존재했는가"를 증명). 객체 삭제 API는 별도 후속 작업.
- 앱 재시작 시 업로드된 사진 URL의 로컬 표시가 복원되지 않아 재선택이
  필요할 수 있다(서버 증거는 유지되므로 요구사항 충족에는 지장 없음).
- 온보딩 "완료"(`initialSetupComplete`) 자체는 여전히 클라이언트 쓰기다.
  resume 라우팅이 사진/아바타 단계를 강제하지만, 완료 플래그의 서버 측
  강제는 후속 하드닝 항목이다.
