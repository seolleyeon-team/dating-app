# 22 — Meeting State Machines (Season + Blind)

작성: 2026-08-18
브랜치: `release/grok45-production-readiness-final`

두 상태 머신은 **서로 별개**다. 하나의 enum으로 합치지 않는다.

- 시즌 미팅: `functions/src/seasonMeetingStateMachine.ts` (`SeasonMeetingPhase`)
- 블라인드 취향 미팅: `functions/src/blindMeeting/types.ts` (`BlindMeetingStatus`)

문서와 코드가 어긋나면 코드가 우선이며, 전이 테이블 회귀는
`seasonMeetingStateMachine.test.ts` / `blindMeeting/__tests__/matching.test.ts`
와 source-scan 테스트(`seasonRouletteTransaction.test.ts`)가 잡는다.

---

## A. Season Meeting FSM (`eventThreeVsThreeMatches.seasonPhase`)

### 전이 테이블 (`ALLOWED`, seasonMeetingStateMachine.ts)

| from | to (허용) |
|---|---|
| team_forming | team_ready, cancelled |
| team_ready | exploring, cancelled |
| exploring | request_pending, team_ready, cancelled |
| request_pending | matched, exploring, cancelled |
| matched | deposit_pending, cancelled, replacement_open, **noshow_review**¹ |
| deposit_pending | deposit_paid, cancelled, noshow_review |
| deposit_paid | chat_open, refund_pending, cancelled |
| chat_open | promise_set, refund_pending, cancelled |
| promise_set | safety_start, noshow_review, cancelled |
| safety_start | in_meeting, noshow_review |
| in_meeting | roulette_done, safety_end, noshow_review |
| roulette_done | safety_end |
| safety_end | refund_pending, completed |
| refund_pending | completed, noshow_review |
| completed | (terminal) |
| cancelled | (terminal) |
| noshow_review | replacement_open, refund_pending, cancelled |
| replacement_open | matched, cancelled, team_forming |

¹ 2026-08-18 추가: deposit provider 비활성 동안 phase가 `matched`에 머문 채
실제 만남이 진행되므로 노쇼 신고 전이를 허용한다.

self-transition(from == to)은 항상 허용(idempotent retry).

### 강제 지점 (writer)

| writer | 전이 | 방식 |
|---|---|---|
| `teamMeetingRequest.ts` accept tx | (생성) `seasonPhase: "matched"` | 문서 생성 edge — FSM 예외(초기 생성) |
| `seasonMeetingOperations.ts` `transitionMatchSeasonPhase` | cancel → `cancelled`, noshow → `noshow_review`, deposit → `deposit_pending` | **단일 트랜잭션 + `canTransitionSeasonMeeting` 강제.** 불허 전이는 `failed-precondition: season_phase_transition_rejected`, 알 수 없는 phase는 `season_phase_unknown` (fail-closed, 자동 복구 없음) |

`seasonMeetingOperations.ts`에서 `seasonPhase` 리터럴 직접 write가 다시 생기면
`seasonRouletteTransaction.test.ts`의 source-scan이 실패한다.

### Request 상태 머신 (`eventTeamMeetingRequests.status`)

```
pending → accepted | declined   (accepted/declined는 terminal)
```

`canTransitionTeamMeetingRequest`가 respond 경로에서 강제. 이중 accept는
기존 matchId를 반환하는 idempotent replay.

### Accept 트랜잭션 invariant (teamMeetingRequest.ts)

단일 Firestore 트랜잭션 안에서 (모든 read가 write보다 먼저):

1. request 상태 전이 (`pending → accepted`)
2. pair lock (`eventTeamMeetingRequestLocks/tmpl_*`, 정렬된 pair 기준) 갱신
3. 차단 관계 재검증 (3×3 양방향 `blocks/{uid}/targets/{uid}`)
4. 권위 팀 재검증 (`meetingGroups.memberUids` == 요청 당시 명단)
5. **팀 단위 활성 match 쿼리 가드** — 한 팀은 활성 match 1개만
   (A-B/A-C 동시 수락, 양방향 legacy 요청 동시 수락 방지)
6. match 생성 (`tmm_sha256(requestId)`, deterministic)
7. room 생성 (`season_<matchId>`, deterministic, create-only) + system 메시지

같은 pair의 활성 match가 살아 있으면 다른 날짜의 새 spin 결과로도
재요청이 거부된다 (create tx의 accepted-pair 가드).

### 검증

- unit: `teamMeetingRequest.test.ts`, `seasonMeetingStateMachine.test.ts`,
  `seasonRouletteTransaction.test.ts` (source-scan)
- emulator: `teamMeetingRequest.emulator-test.ts` (race 4종 + 가드 4종),
  `seasonRoulette.emulator-test.ts` (spin→request→accept full flow,
  stale lock 복구)
- rules: `rules_tests/firestore.meetings.test.mjs`

---

## B. Blind 3:3 Preference Meeting FSM (`blindMeetings.serverStatus`)

### 전이 테이블 (`ALLOWED_MEETING_TRANSITIONS`, blindMeeting/types.ts)

```
(생성) ──────────────► confirmed                ← createMeetingFromProposal (tx: 6개 신청 원자적 클레임
                                                   + 참가자/신청서 confirmed + 6인 채팅방 문서, 한 commit)
confirmed ───────────► chat_open                ← openGroupChatForConfirmedMeeting (idempotent; 스케줄러 복구)
[legacy] awaiting_acceptance ─► confirmed       ← legacyAcceptance.ts (2026-09-03 이전 문서 전용, 좌석 6 유지 시)
chat_open ───────────► schedule_confirmed       ← 전원 투표 or 기한 만료 강제 확정 (일정 필드와 단일 tx)
schedule_confirmed ──► checkin_open             ← 첫 도착 안전도장
checkin_open ────────► in_progress              ← 정원 체크인
in_progress ─────────► completed                ← 전원 체크아웃
completed ───────────► followup_open            ← 종료 15분 후 스케줄러
followup_open ───────► read_only                ← 48시간 후
read_only ───────────► archived (terminal)      ← 7일 후
(모든 비terminal) ───► cancelled (terminal)     ← cancelMeeting
```

`application_open`, `forming`, `awaiting_acceptance` 는 현재 코드에서 새로
쓰이지 않는 LEGACY_COMPATIBILITY_ONLY 값이다 (2026-09-03 정책: **매칭 = 확정**,
참가 수락/거절 단계 없음. 미팅은 `confirmed` 로 태어나고 같은 트랜잭션에서
`chat_rooms/blind_{meetingId}` 가 만들어진다). 제거하지 않는 이유: 기존 문서
호환. `awaiting_acceptance` 로 남은 legacy 미팅은 lifecycle tick 의
`legacyAcceptance` 단계가 좌석 6개가 모두 유지된 경우에만 확정하고, 빈 좌석이
있으면 `responseWindows` 단계가 창 만료 후 취소·재오픈한다. 알 수 없는
status 로 파싱 실패 시 `application_open`으로 fallback되어 모든 전이가 막히는
fail-closed 동작이며, 운영자는 cancel만 가능하다.

신청서(`blindMeetingApplications/{uid}`) canonical 단계 (앱
`BlindMeetingApplicationPhase` 와 1:1):

| phase | 서버 판정 | UI |
|---|---|---|
| NOT_APPLIED | 문서 없음 또는 terminal(completed/no_show/restricted/replaced) | [미팅 DNA 작성하기] |
| ACTIVE | status ∈ {applied, waitlisted} ∧ meetingId 없음 (`CANCELLABLE_APPLICATION_STATUSES`) | 매칭 준비 중 + [신청 취소하기] |
| MATCHED | meetingId 있음 ∧ status ∈ MEETING_BOUND (confirmed 등) | "3:3 미팅이 매칭됐어요!" → 채팅 |
| CANCELLED | status/stage = cancelled | 재신청 가능, "진행 중" 표시 없음 |

`isActive` 판정은 문서 존재 여부가 아니라 status/meetingId 로만 한다
(취소 문서를 active 로 오판하던 결함의 수정).

### 강제 지점

meeting `status`/`serverStatus`의 유일한 사후 writer는
`store.ts transitionMeetingStatus` (트랜잭션 read-modify-write +
`canTransitionMeeting`). 2026-08-18 수정으로:

- `createMeetingFromProposal` (2026-09-03, 수락 단계 제거): 매칭 tx 안에서
  미팅 `confirmed` + `confirmedAt` + `groupChatId` + `scheduleVoteDeadlineAt`,
  참가자 6명 `confirmed`, 신청서 6개 `confirmed`/`stage: matched`/`open: false`
  (merge — requestedDateKeys/heartChargeCount 보존), 채팅방 문서를 함께 commit
  한다. 부분 상태(matched-but-no-room / room-but-no-meeting / 5 participants /
  application still waiting)가 존재할 수 없다. 방 id 는 `blind_{meetingId}`
  로 결정적이라 재시도에도 방은 1개다. 3남+3녀·자격·파티 검증은 tx 안에서
  authoritative users 문서로 다시 한다.
- `openGroupChatForConfirmedMeeting` (`meetingConfirmation.ts`): confirmed →
  chat_open 전이, 만남 이력, 알림. idempotent 이며 `groupChatRepair`
  스케줄 단계가 재실행한다.
- `legacyAcceptance.confirmLegacyAwaitingAcceptanceMeeting`
  (LEGACY_COMPATIBILITY_ONLY): `awaiting_acceptance` 로 남은 과거 문서를
  좌석 6개가 모두 invited/accepted/confirmed 일 때만 확정한다 (invited 는
  FSM 대로 accepted 를 거쳐 confirmed). `acceptInvitation` /
  `declineInvitation` / `openBlindMeetingChat` callable 은 제거됐다.
  legacy `awaiting_deposits` 문서는 `legacyDepositStatus.ts` 가 읽기 시점에
  `awaiting_acceptance` 로 정규화하고 `legacyDepositNormalizer.ts` 가
  fail-closed 로 복구한다.
- `maybeConfirmSchedule`: 일정 필드(slotId/venue/scheduledStartAt)를
  전이와 단일 트랜잭션으로 write (TOCTOU 제거)
- `cancelBlindMeetingApplication` → `store.cancelOpenApplication`
  (매칭 전 전용): applied/waitlisted ∧ meetingId 없음일 때만 취소하고
  **같은 트랜잭션에서** 신청에 쓴 하트를 정확히 한 번 환불한다
  (`heartTransactions/{sha256(blind_meeting_heart_refund:uid:chargeCount)}`
  결정적 ledger id, 원 spend ledger 없으면 환불 없음 fail-closed). 매칭 tx 가
  먼저 commit 된 신청은 `CANNOT_CANCEL_ALREADY_MATCHED` (details.code +
  meetingId) 로 deterministic 거부 — 같은 문서를 read-modify-write 하므로
  cancel-vs-match race 는 Firestore 직렬화가 한쪽만 통과시킨다. 이미
  취소된 문서는 idempotent no-op (환불 재발생 없음). 친구 팀 취소
  (`cancelBlindMeetingParty`)도 멤버별로 같은 helper 를 쓴다.
- 매칭 후 참여 불가는 신청 취소가 아니라 `requestCancellation`(참가 취소
  요청, 환불 없음, 대체 충원) 경로만 존재한다. 매칭 후 cancelled/no_show 로
  정산된 신청서(meetingId null)는 `isApplicationCancellableRaw` 게이트 때문에
  파티 취소에서도 건드리지 않고 환불하지 않는다.
- 취소 write 는 `dnaApplicationCompleted: false` 를 함께 쓰고,
  `startPaidBlindMeetingDna` 는 이 플래그를 active 신청에서만 믿는다 (취소 후
  DNA 재진입 시 이어쓰기 초안이 매번 지워져 이중 차감되던 결함 수정).
  재신청은 이전 `heartRefunded*`/`cancelledAt`/`matchedAt` 를 지운다.
- `cancelMeeting` 은 신청서 재오픈과 함께 이 미팅에 배정됐던 friend party 를
  `matched → ready`(meetingId null) 로 되돌린다 (매칭 claim 이 party `ready`
  를 요구하므로, 되돌리지 않으면 팀원이 영영 재매칭되지 않는다).
- `recentlyMet`(`blindMeetingHistory/{uid}/metUsers`) = **실제로 만난 관계**.
  `recordMetUsers` 의 유일한 호출처는 `orchestrator.markSafetyStamp`(meetup
  도착 안전도장)이며, 도착 도장을 찍은 참가자들끼리만 pair 를 기록한다
  (확정·채팅방·약속 확정은 만남이 아니므로 기록하지 않음, 노쇼·취소·대체
  이탈자는 도장을 찍을 수 없어 제외, pair 문서 id 고정 merge 라 재도장에도
  중복 없음). `handleVacancy` 는 긴급 대체 탐색이 도착 도장 이후에도 돌 수
  있어 같은 미팅 좌석원끼리의 관계만 좌석 스냅샷에서 제외한다(후보 자신의
  실제 만남 이력은 그대로 제약).
- 수락 타임아웃 없음 (closure ②): `acceptanceWindowMs` 정책과 스케줄러의
  응답 창 만료 취소 단계는 제거됐다. `legacyAcceptance.repairLegacy
  AwaitingAcceptanceMeetings` 는 legacy `awaiting_acceptance` 미팅을
  온전(inspectLegacyMatch)하면 confirmed → chat_open, 대체 충원 진행 중이면
  replacement FSM 에 맡기고(`replacement_in_progress`), 그 외는 취소 대신
  `legacyRepairRequired` 1회 + 운영 검토 1건(`repair_required` → 이후
  `repair_pending`). 어떤 legacy 상태도 오래된 수락 기한만으로 취소되지 않는다.
- legacy 무결성 검사(`legacyAcceptance.inspectLegacyMatch`)는 신규 매칭 tx 와
  같은 강도다: 좌석 6·uid 중복 없음·팀 3+3·각 팀 단일 성별·두 팀 성별 상이·
  팀 배열이 명부를 정확히 덮음·총원 3남+3녀·좌석별 참가자 문서·신청서 귀속과
  승격 가능 상태(invited/accepted/confirmed). 하나라도 어긋나면 상태 전이
  **이전**에 repair 로 빠지므로 "confirmed 인데 방 없음" 이 생기지 않는다.
  `legacyDepositNormalizer` 도 같은 검사를 쓰고, 대체 충원이 진행 중이면
  `replacement_in_progress` 로 동일하게 유예한다.
- 대체 충원 tx(`respondReplacementOffer`)는 새 좌석 주인의 확정 시점 성별을
  참가자 문서 `gender` 와 미팅 `participantGenders` 양쪽에 기록하고 이탈자
  항목을 지운다. 이게 없으면 대체 참가자만 복구 근거가 현재 프로필(가변)로
  떨어져, 그 사용자가 성별 필드를 지우면 채팅방 복구가 막힌다.
- `recordMetUsers` 는 이번에 도착한 사람이 만드는 pair 만 쓰고, 최초 체크인일
  때만 호출된다. 각 관계의 `metAt` 이 두 사람이 함께 있게 된 시각으로 한 번만
  고정되고(후속 도착·재도장에 갱신되지 않음) 같은 미팅의 write 도
  N*(N-1) 에서 2*(N-1) 로 준다.
- groupChatRepair 복구 정책 (closure ③): 매칭 tx 와 legacy 확정이 미팅 문서에
  `participantGenders`(+참가자 문서 `gender`) 스냅샷을 남긴다.
  `ensureGroupChat` 의 3남+3녀 재검증은 `store.resolveRosterGenderEvidence`
  (미팅 스냅샷 → 참가자 스냅샷 → 현재 프로필) 근거를 쓰므로 사용자가 나중에
  성별 필드를 지워도 복구된다. 근거가 없거나 불변식이 깨지면
  `meetingConfirmation.repairConfirmedMeetingGroupChat` 가 fail-closed 로
  `groupChatRepairRequired`/`groupChatRepairReason` 을 한 번 표시하고
  `group_chat_repair` 운영 검토 1건을 남긴 뒤 다음 tick 부터 건너뛴다
  (`repair_pending`); 일시 오류는 표시 없이 재시도(`retryable_error`).
- replacement 수락 tx: 활성 status 집합에서만 참가자 교체 허용
  (cancelled/completed/archived 미팅 swap 차단, 알 수 없는 상태 fail-closed)

### 참가자/신청서 상태

participant(`participants/{uid}.serverStatus`)와
application(`blindMeetingApplications/{uid}`)은 meeting FSM의 파생 상태로,
서버 orchestrator만 write한다 (클라이언트 write는 rules로 전면 차단).
participant 전이 테이블의 전면 서버 강제는 후속 과제로 남긴다 —
현재는 위의 게이트들(매칭 tx/취소/교체/확정)이 진입점을 막는다.
`invited` / `accepted` 는 LEGACY_COMPATIBILITY_ONLY (신규 write 0건,
`__tests__/noAcceptance.test.ts` 소스 스캔이 고정).

### 검증

- unit: `blindMeeting/__tests__/matching.test.ts` (FSM 4 + 정책 전체),
  `stateMachines.test.ts` (raw serverStatus write allowlist = confirmed ×5 +
  replaced), `noDeposit.test.ts`, `noAcceptance.test.ts` (수락 단계 0 +
  취소 계약 + 하트 환불 순수 판정 + Flutter 수락/거절 UI 0 스캔),
  `editPolicy.test.ts`, `eligibility.test.ts`
- emulator: `blindMeetingFsm.emulator-test.ts` (choke point + 취소/환불 1회 +
  동시 취소 + matched 취소 거부 + 파티 취소 환불 + legacy 수락 정규화),
  `noDepositHappyPath.emulator-test.ts` (매칭 → confirmed+room 한 commit →
  약속 → 도장 → 완료, 매칭 idempotent/방 1개, 대체 합류, cancel-vs-match
  race 3종, DNA/날짜 영속성)
- rules: `rules_tests/firestore.meetings.test.mjs`,
  `test/firestore_rules/blind_meeting_rules.test.js`
- Flutter: `test/features/blind_meeting/` (통합: 매칭→채팅 진입, 취소→환불→
  재신청, 매칭 후 취소 거부 복구, DNA/날짜 prefill, 재진입),
  `test/features/chat/chat_room_tab_test.dart` (1:1 / 3:3 탭 분류)
