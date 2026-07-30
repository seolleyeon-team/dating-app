# 08 — Season Meeting State Machine (NOT blind)

작성: 2026-07-31

## Scope

In scope: 3:3 **시즌/이벤트 팀 미팅** (`eventTeam*`, `teamMeetingRequest`, roulette).  
Out of scope / protected: `lib/features/event/screens/random_mathcing_screen.dart` (3:3 No-face Blind Date UI).

## Pure guard

```text
functions/src/seasonMeetingStateMachine.ts
functions/src/seasonMeetingStateMachine.test.ts
```

Team meeting request respond path uses `canTransitionTeamMeetingRequest` so accepted/declined cannot reopen.

## Request statuses (server)

```text
pending → accepted | declined
accepted/declined are terminal
```

Evidence: `functions/src/teamMeetingRequest.ts` + tests (idempotent respond, pair lock).

## Remaining gaps (tracked)

| Gap | Status |
|-----|--------|
| Full deposit/noshow/replacement concurrency harness | PARTIAL — stale repair plans escalate money domains to operator_review |
| Wire full SeasonMeetingPhase into Firestore docs | NOT_YET — guard exists; gradual adoption |
| Blind meeting | DEFERRED_PROTECTED_SCOPE — never modify |
