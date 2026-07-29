# 22 — Final Production Readiness

작성: 2026-07-30

## Verdict

```text
PRODUCTION_READY_WITH_EXTERNAL_ACTIONS
```

코드·테스트·runbook·CI gate는 실행 가능한 범위에서 완료했다.
아래 외부 조치가 끝나기 전에는 `PRODUCTION_READY`를 선언하지 않는다.

## External actions remaining

1. **Firestore / Authentication App Check** Monitor → Enforce (runbook 17)
2. **Functions runtime nodejs22** production redeploy
3. **firestore.indexes.json** new indexes deploy
4. **purgeAccountDeletionRetention** scheduler deploy
5. Storage App Check ENFORCED 재확인
6. Retention 일수 법무 확정 (기본 90일)
7. Secret rotation (해당 시) — 본 세션에서 신규 하드코딩 비밀 미발견 수준의 클라이언트 키만 존재(Kakao JS/native는 클라이언트 공개 키)

## Residual risks (non-actionable in-repo)

- 구버전 앱의 Firestore 직접 접근 (ENFORCED 전)
- 과거 탈퇴 사용자 메시지 백필 migration (승인 필요)
- Device profiler 미측정 UI jank

## Ledger gate

완료 선언 전 `16-grok45-continuation-ledger.md`에서
`NOT_STARTED` / `IN_PROGRESS` / `FIXED_UNVERIFIED` = 0 이어야 한다.
