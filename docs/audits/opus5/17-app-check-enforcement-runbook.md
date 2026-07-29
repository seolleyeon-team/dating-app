# 17 — App Check Enforcement Runbook

작성: 2026-07-30  
대상 프로젝트: `seolleyeon-final`  
코드 준비 브랜치: `audit/grok45-final-hardening`

**이 문서는 절차·검증·롤백만 정의한다. Production ENFORCED 전환은 운영자 승인 후 실행한다.**

---

## 1. 현재 enforcement 상태 (코드/문서 기준)

| 표면 | 코드 | 콘솔 (2026-07-29 감사) | 비고 |
|------|------|------------------------|------|
| Callable Functions | `enforceAppCheck: true` (`withAppCheck`) | N/A (코드 강제) | Auth/bootstrap 포함 |
| Storage | `storage.rules` write deny + App Check | **ENFORCED** | 재확인만 필요 |
| Firestore | Rules auth 기반 | **UNENFORCED** | 본 runbook 대상 |
| Authentication | 클라이언트 SDK | **UNENFORCED** | 본 runbook 대상 |

공식 Firebase 콘솔에서 Firestore / Authentication App Check enforcement를 지원한다.
존재하지 않는 API나 플래그를 가정하지 말 것.

---

## 2. 앱 버전별 준비 상태

| 플랫폼 | Provider (release) | Provider (debug/local) | 필수 dart-define |
|--------|--------------------|------------------------|------------------|
| Android | Play Integrity | Debug / debug-signed | 스토어 빌드에 `FORCE_APP_CHECK_DEBUG` 금지 |
| iOS | App Attest | Debug | 동일 |
| Web | reCAPTCHA v3 | (debug provider 미사용) | `APP_CHECK_WEB_RECAPTCHA_SITE_KEY` |

코드:
- `lib/main.dart` → `_activateAppCheck()`
- `lib/shared/utils/app_check_provider_policy.dart`
- `lib/services/app_check_bootstrap.dart` (`lastAppCheckInitResult`)

구버전 앱: App Check 미초기화 시 callable이 이미 실패한다. Firestore/Auth ENFORCED 전에는 직접 REST 접근이 가능하므로 **ENFORCED 전에 강제 업데이트 비율을 확인**한다.

---

## 3. Staging 검증 방법

1. Staging 프로젝트(또는 `seolleyeon-final` staging alias)에서 App Check debug token 등록.
2. Debug 빌드 + Debug Integrity/App Attest/reCAPTCHA 각각으로:
   - 로그인 / Kakao bootstrap callable
   - emailLink exchange
   - avatar / chat / team callables
3. 의도적 실패:
   - App Check 토큰 제거 → callable 403
   - Web site key 미설정 → `skippedWebMissingKey` + callable 실패
4. 성공 기준:
   - 정상 클라이언트 성공률 ≥ 99.5%
   - 플랫폼별 App Check 실패율 < 1% (24h)
5. 로그 키워드 (PII 없음):
   - `[AppCheckTelemetry] status=...`
   - Functions `failed-precondition` / App Check reject

---

## 4. Production 적용 순서 (canary)

```text
1) Storage ENFORCED 유지 확인
2) Callable enforceAppCheck 이미 배포됨 확인
3) Firestore App Check: Monitor → (24~72h) → Enforce
4) Authentication App Check: Monitor → (24~72h) → Enforce
5) 구버전 강제 업데이트 / 스토어 롤아웃과 동기화
```

### Firestore

```bash
# 콘솔: App Check → APIs → Cloud Firestore → Enforce
# 또는 현재 Firebase CLI/콘솔 워크플로를 따른다.
# 실제 명령은 콘솔 UI가 권위. 아래는 점검용.
firebase apps:sdkconfig ANDROID --project seolleyeon-final
```

### Authentication

```bash
# 콘솔: App Check → APIs → Firebase Authentication → Enforce
```

Monitor 모드가 제공되면 최소 24시간 관측 후 Enforce.

---

## 5. 관측 지표

| 지표 | 허용 | 비고 |
|------|------|------|
| App Check token exchange 실패율 | < 1% | 플랫폼별 |
| Callable `app-check` 거부율 | < 0.5% (신버전) | 구버전 별도 |
| 로그인 성공률 | 기준선 ±2%p | Auth ENFORCED 전후 |
| Firestore Rules deny spike | 비정상 +50% 금지 | 클라이언트 버그 구분 |
| Web reCAPTCHA score / missing key | Web 로그인 차단 0 (신버전) | site key 배포 필수 |

---

## 6. Rollback 조건

다음 중 하나면 즉시 UNENFORCED로 되돌린다.

- 신버전(강제 업데이트 완료 빌드) 로그인 성공률 5%p 이상 하락
- App Check 실패율 > 5% (어느 한 플랫폼)
- 스토어 리뷰/CS 폭주 (App Check 관련)
- Web site key 장애

### Rollback

```text
Firebase Console → App Check → APIs
→ Cloud Firestore → Off / Unenforced
→ Firebase Authentication → Off / Unenforced
```

Callable `enforceAppCheck`는 코드 배포 롤백이 필요하므로 Firestore/Auth보다 먼저 끄지 않는다.
긴급 시 Functions 이전 버전으로 롤백:

```bash
# 예시 — 실제 버전 ID는 배포 이력에서 확인
# gcloud functions deploy ... --(사용 금지: 본 작업에서 실행하지 않음)
# Firebase Console → Functions → 이전 revision
```

---

## 7. 사용자 영향 / 구버전

| 사용자군 | Firestore ENFORCED | Auth ENFORCED |
|----------|--------------------|---------------|
| 최신 앱 (App Check OK) | 정상 | 정상 |
| 구버전 (App Check 없음) | 직접 Firestore 실패 | 인증 실패 가능 |
| Web (site key 없음) | callable/직접 접근 실패 | 로그인 실패 |

조치: Play/App Store 최소 버전 강제 후 ENFORCED.

---

## 8. 플랫폼별 주의점

- **Android**: Play Integrity는 Play 배포 서명 필요. 사이드로드 release는 `FORCE_APP_CHECK_DEBUG` 로컬 전용.
- **iOS**: App Attest는 실기기/프로비저닝 필요. 시뮬레이터는 debug provider.
- **Web**: reCAPTCHA v3 site key를 CI/CD dart-define에 주입. 키 누락은 보안 우회가 아니라 **로그인 불가**.

---

## 9. 외부 blocker

```text
BLOCKER_EXTERNAL
ID: L-10 / L-12 / L-23
영역: App Check production enforcement
원인: 운영 콘솔 변경 권한·승인 필요
완료된 준비: 코드 enforceAppCheck, Flutter bootstrap, 본 runbook, telemetry
실행에 필요한 외부 조치: Staging Monitor→Enforce → Production canary
정확한 실행 명령: 콘솔 App Check APIs Enforce (위 §4)
검증 방법: §5 지표
롤백 방법: §6
다른 작업 진행 여부: 계속
```
