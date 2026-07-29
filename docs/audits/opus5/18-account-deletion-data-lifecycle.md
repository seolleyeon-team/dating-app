# 18 — Account Deletion Data Lifecycle

작성: 2026-07-30  
구현: `functions/src/accountDeletion*.ts`, `avatarCleanup.ts`

---

## 1. 정책 요약

법적·제품 정책이 최종 확정되기 전 **파괴적 즉시 전체 삭제**를 피하고, configurable retention을 기본으로 한다.

| 데이터 | 탈퇴 시 처리 | Retention |
|--------|--------------|-----------|
| 프로필 PII / private | purge (기존 SEC-P1-08) | 즉시 |
| 원본/아바타 입력 이미지 | cleanupAvatarMedia | 즉시 |
| FCM deviceTokens | 삭제 | 즉시 |
| blocks / reports | 최소 보존 (양방향 차단 유지) | 운영 |
| bamboo 글/댓글 | soft-delete | 즉시 마스킹 |
| 채팅방 membership snapshot | `탈퇴한 사용자` + closed | 즉시 |
| 채팅 메시지 본문 | **보존** + 작성자 익명화 | 기본 90일 후 purge |
| 채팅 첨부/미디어 필드 | 즉시 필드 삭제 | 즉시 |
| 이벤트 팀 | acceptedUserIds/leader/pending 정리 | 빈 팀 30일 후 purged |
| legalHold=true | purge 제외 | 수동 해제 전 |

법무 확정 시 retention 일수만 조정하면 된다 (`DEFAULT_DELETED_MESSAGE_RETENTION_DAYS`).

---

## 2. 채팅 메시지 수명주기

코드: `accountDeletionChatLifecycle.ts`

1. `closeChatRoom` — participantInfo 익명화, status=closed  
2. `anonymizeChatMessages` — `senderId` → `deleted_<hash16>`, displayName=`탈퇴한 사용자`, media 필드 delete, `purgeAfter` 설정  
3. 스케줄 `purgeAccountDeletionRetention` (매일 04:30 KST) — retention 경과 & `legalHold!=true` → 본문 `[삭제된 메시지]`

금지 사항 준수:
- 상대방 문서에 이메일/실명/학교인증 잔류 없음 (PII cleanup)
- 공개 Storage URL 유지 금지 (media 필드 삭제; GCS 오브젝트는 avatar cleanup 경로)
- FCM 토큰 유지 금지
- 삭제 실패를 성공으로 반환하지 않음 (avatarCleanup partial retry)

---

## 3. 이벤트 팀 정리

코드: `accountDeletionEventTeamCleanup.ts`

**버그 수정:** 기존 구현이 `memberUids` array-contains만 조회했으나 실제 스키마는 `acceptedUserIds` / `leaderUserId` / `pendingInviteeIds`.

동작:
1. 세 쿼리로 팀 로드
2. 멤버/pending에서 uid 제거
3. leader 탈퇴 시 남은 accepted[0]으로 transfer, 없으면 empty
4. pending invite cancel (`cancelledReason=account_deletion`)
5. empty → `status=purge_pending` + 30일 TTL → scheduler가 `purged`

상태: `forming | active | cancelled | completed | empty | archived | purge_pending | purged`

---

## 4. Orchestration

- Idempotent: `authorDeleted` / soft-delete / cleanup request id
- Partial failure: avatarCleanup retryable
- Dry-run: anonymize/purge helpers `dryRun` 옵션
- Repair: 동일 callable 재실행
- Production migration: **실행하지 않음** (신규 탈퇴부터 적용; 과거 메시지 백필은 외부 승인)

---

## 5. 테스트

- `accountDeletionSocialCleanup.test.ts` — plan, anonymize patch, event team transfer/empty, purge gates
- `avatarCleanup.test.ts` — PII + social counts
- 권장 추가(에뮬레이터): 중간 실패 재시도, legal hold, orphan cleanup

---

## 6. 외부 blocker

```text
BLOCKER_EXTERNAL
ID: L-22
영역: retention 일수 / 신고 증거 보존 기간
원인: 개인정보처리방침·법무 명시적 확정 필요
완료된 준비: configurable 90일 기본 + legalHold + purge scheduler
실행에 필요한 외부 조치: 법무/제품 승인 후 상수 조정 및 약관 반영
```
