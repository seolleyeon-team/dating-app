# 20 — Observability and Alerting

작성: 2026-07-30

**Production alert 리소스는 생성하지 않는다.** 아래는 IaC/콘솔 절차 초안이다.

---

## 1. Structured log events (PII-free)

| Event | Source | Fields |
|-------|--------|--------|
| App Check bootstrap | Flutter `[AppCheckTelemetry]` | status, platform, debug, blocked, errorSummary |
| emailLink token purge | `purgeExpiredEmailLinkTokens` | scanned, deleted, skipped |
| deletion retention purge | `purgeAccountDeletionRetention` | messages{}, teams{} |
| avatar cleanup | `cleanupAvatarMedia` | sanitized counts only |
| push suppress | FCM filter helpers | recipient eligibility reasons (hashed ids) |
| callable App Check reject | Cloud Functions | code=`failed-precondition` |

금지: email, phone, raw token, raw storage URL, message body in logs.

---

## 2. Recommended SLOs

| Service | SLO | Alert |
|---------|-----|-------|
| Login + bootstrap callables | 99.5% success / 5m | error rate > 1% |
| App Check activate (release) | 99% success / 1h | platform failure > 5% |
| Account deletion cleanup | 99% complete within 15m | retryable failures > 10/day |
| Retention purge scheduler | ≥1 success / day | miss 2 consecutive runs |
| Recs batch job | success within timeout | job duration p95 > budget |
| Rules deny spike | baseline ±50% | investigate client bug vs attack |

---

## 3. Alert setup procedure (manual / Terraform later)

```text
Cloud Monitoring → Alerting → Create Policy
1) Log-based metric: AppCheckTelemetry blocked=true
2) Cloud Functions execution error rate (asia-northeast3)
3) Cloud Scheduler job failure for purge* schedules
4) Notification: on-call email/Slack (secret not in repo)
```

Rollback: disable policy; do not delete historical metrics.

---

## 4. Correlation

Prefer `requestId` / idempotency key already used in avatar cleanup.
Flutter: include `status` only; never uid in App Check telemetry.
