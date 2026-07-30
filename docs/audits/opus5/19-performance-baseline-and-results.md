# 19 — Performance Baseline and Results

작성: 2026-07-30  
방법: 정적 병목 조사 + 로컬 명령 측정. Profiler 장치 측정이 없는 항목은 추측하지 않음.

---

## 1. Baseline commands

| Metric | Method | Before | After | Notes |
|--------|--------|--------|-------|-------|
| Functions unit suite | `npm test` in `functions/` | 181 pass / ~12.4s | 181 pass / ~12.4s | Node engines→22 (로컬 Node 24에서 실행) |
| App Check policy tests | `flutter test test/app_check_provider_policy_test.dart` | 4 tests | 8 pass | 정책 확장 |
| Avatar auth pytest | `pytest tests/test_avatar_exact_replay_auth.py` | — | 11 pass / 9.0s | 미커밋 완화 포함 |
| Flutter startup / frame time | device profiler | **UNMEASURED** | **UNMEASURED** | 실기기/DevTools 세션 없음 |
| CupertinoIcons font (release tree-shake) | `flutter build apk --analyze-size` (partial) | 257628 B | **17000 B (−93.4%)** | Gradle assembleRelease 중 관측 |
| MaterialIcons font (release tree-shake) | same | 1645184 B | **8756 B (−99.5%)** | same |
| APK total / Web bundle size | full `--analyze-size` | **UNMEASURED** | **INCOMPLETE** | arm64 release Gradle가 28분+ 정체되어 중단. 재실행: `flutter build apk --release --target-platform android-arm64 --analyze-size` |
| Firestore read count (recs/chat) | production metrics | **UNMEASURED** | code-level N+1 review | 운영 메트릭 접근 없음 |

---

## 2. Code-level bottlenecks addressed / noted

| Area | Finding | Action |
|------|---------|--------|
| Account deletion event team query | Wrong field `memberUids` → zero hits, wasted cleanup path | Fixed to acceptedUserIds/leader/pending |
| Chat message anonymize | Unbounded history risk | Paged `pageSize=200` batches |
| Retention purge | collectionGroup + composite index | Index added to `firestore.indexes.json` (deploy = external) |
| Duplicate FCM / auth listeners | Known residual | Tracked L-16; targeted fixes when found |
| Recommendation N+1 | Prior Opus fix for blocks | Verified defaults in `recsys/main.py` |
| Silent catch / legacy stubs / IAP | Release risk | Logged catches; stub fail-closed; purchase gated |
| Heart charge fake purchase | Empty onTap / TODO pay | Shows "결제 준비 중" until `ENABLE_IN_APP_PURCHASE` + real billing |

---

## 3. Follow-up measurements (external / local device)

```bash
flutter run --profile
# DevTools → Performance / Memory on: matching feed, chat room, profile

flutter build apk --analyze-size
flutter build web --analyze-size
```

운영 Firestore:

```text
Console → Usage → Reads by collection (modelRecs, chat_rooms, users)
```

---

## 4. Verdict on performance claims

측정 없는 “문제 없음” 판정은 하지 않는다.  
본 세션에서 **증명된** 개선은 탈퇴 cleanup 쿼리 정확성(무효 쿼리 제거)과 메시지 페이지 배치, 인덱스 선언이다. UI jank/APK 크기 개선은 **UNMEASURED**.
