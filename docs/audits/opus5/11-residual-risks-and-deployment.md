# 남은 위험 · Production Readiness · 배포와 롤백

## 1. 남은 위험

### 해소된 항목

| ID | 상태 |
|---|---|
| R-JDK21 | **해소.** `Android Studio1\jbr` 의 JDK 21.0.10 으로 emulator 실행. Firestore 151/151, Storage 23/23 통과 |
| R-CHAT | **해소.** chat_rooms / messages 참가자 제한 + senderId 바인딩. 공격 테스트 15건 통과 |
| R-REPORTS | **해소.** reports 는 client read 전면 차단, 문의는 소유자 스코프. 공격 테스트 11건 통과 |

### 즉시 대응 필요

| ID | 위험 | 근거 | 필요한 조치 |
|---|---|---|---|
| R-UPDATEGATE | **강제 업데이트 장치가 없다.** 규칙을 먼저 배포하면 구버전 앱이 즉시 깨진다 | 저장소에 minimumSupportedBuild 류의 게이트가 없음. 구버전은 사진 업로드에 `signInAnonymously()` 를 쓰고 비인증 `users` 쓰기에 의존 | 최소 지원 버전 게이트를 구현하거나, 앱 강제 업데이트 확산을 확인한 뒤 규칙을 배포한다. **이번 세션에서 구현하지 않았다** |
| R-CHAT-SYSTEM | 클라이언트가 `senderId: 'system'` 으로 시스템 안내 메시지를 쓸 수 있다 | `chat_service.dart:133`, `lib/services/chat_service.dart:129`/`:140`, `user_service.dart:323`. 규칙에서 예외 허용 중 | 시스템 메시지를 서버 발행으로 옮기고 규칙 예외를 제거한다 |

### 배포 전 대응

| ID | 위험 | 조치 |
|---|---|---|
| R-FS-1 | `emailLinkTokens` 는 `get: if true` 유지. 문서 ID 를 아는 사람에게 `email` + `kakaoUserId` 노출 | 구조적으로 필요(웹이 `signInWithEmailLink` 전에 email 을 알아야 함). ID 는 UUIDv4(122비트), 만료 30분. 서버 발급 + hash 저장으로 옮기는 것이 정답 |
| R-FS-2 | 인증 사용자는 다른 사용자의 `studentEmail` 과 onboarding 전체를 읽을 수 있다 | `publicProfiles` 프로젝션 컬렉션 도입 + 서버 trigger 동기화. 스키마 변경·마이그레이션 필요 |
| R-FS-3 | 본인 문서의 `status` 를 스스로 바꿀 수 있어 정지 상태 자체 해제 여지 | 탈퇴·정지 전이를 callable 로 이전. 지금 막으면 회원 탈퇴가 동작하지 않아 보류 |
| R-STORAGE-1 | Storage contentType 을 `image/*` 로만 검사 (엄격한 allowlist 아님) | 클라이언트 MIME 정규화는 이번에 넣었다. 두 화면이 새 앱 버전으로 배포된 뒤 allowlist 로 좁힐 수 있다 |
| R-STORAGE-2 | 단계적 얼굴 공개(블러)가 **클라이언트 전용**. download URL 을 가진 인증 사용자는 원본 취득 가능 | 서버측 블러·썸네일 파생물 생성 + 원본은 소유자·서버만 |
| R-APPCHECK | callable 11개 App Check 미적용 | `enforceAppCheck: true` 적용 + 클라이언트 App Check 활성화 확인 |
| R-LEGACY | 구버전 앱이 삭제된 callable 을 호출 | 아래 "구버전 클라이언트" 참조 |

### 장기 개선

- P1-6 / P1-7 전화번호 해시 (pepper 도입, `matchedUserId` 반환 중단, 소유 증명)
- P1-11 blindMeeting fail-open 게이트를 fail-closed 로
- P2-4 조용한 실패 → 부분 실패를 명시적 상태로
- P2-5 무제한 스캔 → pagination
- P2-8 추천 fallback 정책 정리 (`nope`·신고 필터, UI 라벨링)
- P2-7 `users/{uid}/ai_swipes` 규칙 누락 확인 및 수정
- P3-7 중복 화면 2세트 정리

### 외부 승인 필요

- 운영 Firebase 프로젝트에 대한 규칙 배포
- refresh token 전수 폐기 (사용자 전원 재로그인 발생)
- JDK 21 설치

### 검증 불가능

- iOS 빌드 (macOS 없음)
- 실제 운영 노출 여부 (로그 접근 권한 없음)
- P1-13 Kakao audience 검증 부재의 실제 악용 가능성

---

## 2. Production Readiness

| 대상 | 판정 | 근거 |
|---|---|---|
| Firebase Authentication | READY_WITH_CONDITIONS | P0-1 제거됨. App Check·rate limit 없음 |
| 학교 인증 | READY_WITH_CONDITIONS | 위조 경로 차단. `emailLinkTokens` get 공개는 R-FS-1 |
| Firestore Rules | READY_WITH_CONDITIONS | 151/151 공격 테스트 PASS. 조건: 앱 선배포 + R-UPDATEGATE. R-FS-2 잔존 |
| Storage Rules | READY_WITH_CONDITIONS | 23/23 PASS. 문법 유효성 emulator 로 확인. 조건: 앱 선배포. R-STORAGE-2 잔존 |
| Cloud Functions | READY_WITH_CONDITIONS | lint/build/test(128) PASS. App Check·rate limit 없음, P1-6/P1-7 미수정 |
| 채팅 | READY_WITH_CONDITIONS | 참가자 제한·senderId 바인딩 검증 완료. R-CHAT-SYSTEM 잔존 |
| 신고·차단 | READY_WITH_CONDITIONS | 양쪽 모두 소유자 스코프로 검증. 운영 조회 경로는 Admin SDK 전용 |
| 개인정보 보호 | **NOT_READY** | R-FS-2, R-STORAGE-2 |
| 1:1 추천 | READY_WITH_CONDITIONS | 소유권 제한 적용. fallback 정책은 P2-8 |
| Flutter Android | READY_WITH_CONDITIONS | `flutter build apk --debug` PASS. release appbundle 미검증 (서명 키 필요) |
| Flutter iOS | NOT_ASSESSED | macOS 없음 |
| Flutter Web | READY_WITH_CONDITIONS | `flutter build web` PASS |
| Cloud Run 추천 시스템 | NOT_ASSESSED | `recsys/` 미조사 |
| AI 아바타 파이프라인 | NOT_APPLICABLE | 저장소에 존재하지 않음. `ai_profiles/` 는 배치 업로드된 더미 프로필 |
| 무물 | NOT_ASSESSED | 규칙 노출만 확인 (P1-9) |
| 연락처 차단 | READY_WITH_CONDITIONS | P1-6/P1-7 미수정 |
| 운영 모니터링 / 백업·복구 / CI-CD / dependency security / abuse prevention | NOT_ASSESSED | 미조사 |
| 관리자 기능 | READY | custom claim 기반 (`blindMeeting/ops.ts:46`). 클라이언트 필드 의존 없음 |
| 축제 웹 참가권 / 결제 | NOT_ASSESSED | `payments.ts` 는 가짜 성공을 반환하지 않는다는 점만 확인 |

**종합: NOT_PRODUCTION_READY**

---

## 3. 배포 전 필수 작업 (실행 순서)

1. 규칙 테스트 재확인 (JAVA_HOME 을 `Android Studio1\jbr` 로 설정).
   Gradle 데몬이 떠 있으면 먼저 정리한다.
   ```
   npm --prefix test/firestore_rules run test:firestore   # 151 PASS
   npm --prefix test/firestore_rules run test:storage     # 23 PASS
   ```
2. **R-UPDATEGATE 를 먼저 해결한다.** 최소 지원 버전 게이트 없이 규칙을
   배포하면 구버전 앱의 로그인과 사진 업로드가 즉시 깨진다.
3. 실패하는 항목이 있으면 규칙을 고친다. **테스트를 낮추지 않는다.**
4. `firebase emulators:start --only firestore,storage,auth` 위에서 앱을 띄워
   수동 회귀: 카카오 로그인 → 학생 인증 → 온보딩 사진 업로드 → 프로필 편집 →
   프로필 탐색 → 추천 카드 → 채팅 → 차단 → 알림 → 탈퇴.
   특히 **사진 업로드**(익명 fallback 제거됨)와 **users list fallback 추천** 확인.
6. `npm --prefix functions test`, `flutter test`, `flutter build apk --debug`,
   `flutter build web` 통과 확인.
7. 새 앱 버전을 먼저 배포한다. 순서가 중요하다 (아래).
8. 규칙 배포: `firebase deploy --only firestore:rules,storage`
9. Functions 배포: `firebase deploy --only functions`
   → `createFirebaseCustomTokenFromEmailLinkToken` 이 삭제된다.

### 배포 순서에 대한 경고

규칙을 먼저 배포하고 앱을 나중에 배포하면 **구버전 앱이 즉시 깨진다**:

- 구버전은 사진 업로드 시 `signInAnonymously()` 로 넘어가는데, 새 Storage
  규칙은 익명 uid 를 거부한다 → 업로드 실패
- 구버전은 Firebase 세션 없이 `users` 문서를 쓰는 경로가 있는데, 새 Firestore
  규칙은 `isSelf` 를 요구한다 → 로그인·온보딩 실패

따라서 **앱 배포 → (강제 업데이트 유도) → 규칙 배포** 순서를 지킨다.
강제 업데이트 장치가 없다면 규칙 배포 전에 그것을 먼저 만들어야 한다.

### 구버전 클라이언트와 삭제된 callable

함수를 완전히 삭제하는 편을 택했다. 근거:

- 구버전 클라이언트의 호출은 `not-found` 로 실패하고,
  `AuthService.ensureFirebaseSessionForVerifiedUser` 의
  `on FirebaseFunctionsException` 이 이를 잡아 `ensureFirebaseSessionForKakao`
  로 fall through 한다. 즉 **계정 탈취 없이 정상 경로로 복구된다.**
- fail-closed stub 을 남기면 취약한 함수 이름이 계속 존재해서, 향후 누군가
  본문을 되살릴 위험이 있다.
- 다만 배포 전까지는 운영에 취약한 함수가 그대로 살아 있다. 이것이 배포를
  서둘러야 하는 이유다.

---

## 4. 롤백

| 롤백 대상 | 관련 커밋 | 롤백 명령 | 데이터 영향 | 추가 조치 |
|---|---|---|---|---|
| 인증 callable 제거 | `82cc1461` | `git revert 82cc1461` + `firebase deploy --only functions` | 없음 | **되돌리면 계정 탈취가 다시 열린다.** 사실상 롤백 불가로 취급 |
| Storage 규칙 + 업로드 클라이언트 | `4217f446` | `git revert 4217f446` + 앱 재배포 | 없음 | 이전 파일은 배포 불가 상태였으므로 실질적 롤백 대상은 "직전에 운영에 살아 있던 규칙"이다. 그 내용을 콘솔에서 먼저 확보해 둘 것 |
| Firestore 규칙 | (아래 커밋) | Firebase 콘솔의 규칙 버전 히스토리에서 이전 버전 롤백 | 없음 | 콘솔 롤백이 git revert 보다 빠르다. 배포 직전 버전 ID 를 기록해 둘 것 |
| 서브에이전트 시즌 미팅 작업 | 이 브랜치에 없음 | 필요 시 `audit/opus5-production-hardening` (`0de983e5`) 에서 cherry-pick | 없음 | 미검토·빌드 실패 상태. 검토 후 사용 |

규칙은 데이터를 바꾸지 않으므로 롤백에 마이그레이션이 필요 없다.
단 사진 업로드 클라이언트 변경은 앱 버전에 묶여 있어서, 규칙만 롤백하면
새 앱은 계속 동작하고 구버전 앱도 동작하는 상태로 돌아간다.

---

## 5. 침해 대응 (Incident)

**판정: `COMPROMISE_NOT_CONFIRMED` / `EXPOSURE_POSSIBLE`**

침해 여부를 판단할 근거가 없다. 이 세션에서는 운영 로그에 접근하지 않았고
접근해서도 안 됐다. 침해가 없었다고 추정하지 않는다.

취약 코드가 운영에 배포된 적이 있는지 판단할 저장소 근거:

- `.firebaserc` default 프로젝트가 `seolleyeon` (운영) 하나뿐이다.
- `functions/package.json` 의 `deploy` 스크립트가
  `npm run build && firebase deploy --only functions` 다.
- 취약한 callable 은 `8b782415` 시점까지 `functions/src/index.ts` 에 존재했고
  `storage.rules` 상단 주석은 `⚠ 반드시 배포: firebase deploy --only storage` 라고
  적혀 있다.
- 즉 **배포되었을 가능성이 높다**. 확정하려면 Cloud Functions 배포 이력과
  Firestore 규칙 버전 히스토리를 콘솔에서 확인해야 한다.

### 권장 외부 조치 (사용자 승인 필요, 이 세션에서 수행하지 않음)

1. Cloud Functions 배포 이력에서 `createFirebaseCustomTokenFromEmailLinkToken`
   의 최초 배포 시점 확인 → 노출 기간 확정
2. 해당 함수의 호출 로그 감사. 정상 흐름은 `verificationToken` +
   `studentEmail` + `kakaoUserId` 3개를 모두 보낸다.
   **`verificationToken` 만 담긴 호출은 공격 시그니처다.**
3. `emailLinkTokens` 컬렉션 감사. `lastRecoveredKakaoUserId` 가 있고
   `createdAt` 이 정상 인증 흐름과 맞지 않는 문서, 만료 시각이 없거나
   `expiresAt` 이 timestamp 가 아닌 문서를 찾는다. 이후 만료분 삭제.
4. Firebase Authentication refresh token 전수 폐기 + 강제 재로그인 검토
5. `users` 컬렉션 대량 read/list 접근 패턴 확인
6. `deviceTokens` 에서 소유자 uid 와 무관해 보이는 토큰 등록 감사
7. `blocks` 하위 문서의 비정상 삭제 감사
8. `reports` 접근·변조 감사
9. `isStudentVerified` / `loginDisabled` / `status` 변경 이력 감사
10. Storage `users/*/onboarding/photos/` 의 비정상 업로드·삭제 감사

위 항목 중 어느 것도 이 세션에서 실행하지 않았다.
