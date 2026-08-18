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
(생성) ──────────────► awaiting_acceptance      ← createMeetingFromProposal (tx, 6개 신청 원자적 클레임)
awaiting_acceptance ─► awaiting_deposits        ← 전원 수락
awaiting_deposits ───► confirmed                ← 전원 보증금 정산 (transition 먼저, 참가자 write 나중)
confirmed ───────────► chat_open                ← 그룹 채팅 생성 후
chat_open ───────────► schedule_confirmed       ← 전원 투표 or 기한 만료 강제 확정 (일정 필드와 단일 tx)
schedule_confirmed ──► checkin_open             ← 첫 도착 안전도장
checkin_open ────────► in_progress              ← 정원 체크인
in_progress ─────────► completed                ← 전원 체크아웃
completed ───────────► followup_open            ← 종료 15분 후 스케줄러
followup_open ───────► read_only                ← 48시간 후
read_only ───────────► archived (terminal)      ← 7일 후
(모든 비terminal) ───► cancelled (terminal)     ← cancelMeeting
```

`application_open`, `forming`은 현재 코드에서 도달 불가능한 레거시 값이다
(미팅은 `awaiting_acceptance`로 태어난다). 제거하지 않는 이유: 기존 문서
호환. 알 수 없는 status로 파싱 실패 시 `application_open`으로 fallback되어
모든 전이가 막히는 fail-closed 동작이며, 운영자는 cancel만 가능하다.

### 강제 지점

meeting `status`/`serverStatus`의 유일한 사후 writer는
`store.ts transitionMeetingStatus` (트랜잭션 read-modify-write +
`canTransitionMeeting`). 2026-08-18 수정으로:

- `advanceAfterDeposit`: **전이 성공 후에만** 참가자/신청서를 confirmed로
  write (이전엔 1명 결제로 12개 문서가 premature confirm되는 결함),
  `awaiting_deposits` 상태 게이트 추가
- `advanceAfterAcceptance`: 조기 결제자(paid/authorized/confirmed)의
  상태를 pending으로 되돌리지 않음, 전원 기결제 시 즉시 확정 재확인
- `maybeConfirmSchedule`: 일정 필드(slotId/venue/scheduledStartAt)를
  전이와 단일 트랜잭션으로 write (TOCTOU 제거)
- `declineInvitation`: awaiting_acceptance/awaiting_deposits에서만 허용
- `cancelBlindMeetingApplication` → `store.cancelOpenApplication`:
  meetingId가 붙은 신청은 취소 거부 (트랜잭션 게이트)
- replacement 수락 tx: 활성 status 집합에서만 참가자 교체 허용
  (cancelled/completed/archived 미팅 swap 차단, 알 수 없는 상태 fail-closed)

### 참가자/신청서 상태

participant(`participants/{uid}.serverStatus`)와
application(`blindMeetingApplications/{uid}`)은 meeting FSM의 파생 상태로,
서버 orchestrator만 write한다 (클라이언트 write는 rules로 전면 차단).
participant 전이 테이블의 전면 서버 강제는 후속 과제로 남긴다 —
현재는 위의 게이트들(수락/거절/취소/교체/확정)이 진입점을 막는다.

### 검증

- unit: `blindMeeting/__tests__/matching.test.ts` (FSM 4 + 정책 전체),
  `editPolicy.test.ts`, `eligibility.test.ts`
- rules: `rules_tests/firestore.meetings.test.mjs`,
  `test/firestore_rules/blind_meeting_rules.test.js`
- Flutter: `test/features/blind_meeting/` 14개 파일 (FSM 미러 파리티 포함)
