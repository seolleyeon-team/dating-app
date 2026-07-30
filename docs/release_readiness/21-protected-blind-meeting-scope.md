# 21 — Protected Blind Meeting Scope

작성: 2026-07-31  
브랜치: `release/grok45-integrated-readiness`  
정책: **PROTECTED_READ_ONLY** — 기능 추가·버그수정·UI·리팩터·Rules·Functions·테스트 기대값·문서·dead code 삭제 금지

## Search performed

```text
blindMeeting
blind_meeting
BlindMeeting
블라인드 취향 미팅
3:3 블라인드
blind taste
blind meeting
블라인드
```

Scopes: `lib/`, `functions/src/`, `test/`, `docs/`, `rules_tests/`, `firestore.rules`, `storage.rules`  
Excluded junk: `.tmp/`, `dating-app/`, `node_modules/`

## Dedicated feature folders

| Expected path | Present? |
|---------------|----------|
| `lib/features/blind_meeting/**` | NO |
| `functions/src/blindMeeting/**` | NO |
| `functions/src/blind_meeting/**` | NO |
| `test/features/blind_meeting/**` | NO |
| `test/firestore_rules/blind_meeting_rules.test.js` | NO |

현재 브랜치에는 별도 `blind_meeting` 패키지/폴더가 없다.  
블라인드 취향 미팅 UI는 이벤트 슬롯머신 화면 파일명으로 존재한다.

## Protected exclusive files

| Path | Role | Initial SHA256 | Initial git blob | Final SHA256 | Changed? |
|------|------|----------------|------------------|--------------|----------|
| `lib/features/event/screens/random_mathcing_screen.dart` | 3:3 No-face Blind Date / 슬롯머신(3:3 블라인드 매칭) UI | `94BA62403DB676CF495727F59BCC4B46A6F5620120770879ED3A0CB98E98849C` | clean at HEAD | `94BA62403DB676CF495727F59BCC4B46A6F5620120770879ED3A0CB98E98849C` | **0 (unchanged)** |

## Shared / adjacent paths (NOT exclusive — modify only with blind-regression protocol)

이 경로들은 시즌 미팅·튜토리얼·라우팅과 공유될 수 있다.  
블라인드 동작이 바뀔 가능성이 있으면 공용 변경 보류.

```text
lib/router/app_router.dart                    # imports SlotMachineScreen route
lib/router/route_names.dart                   # slotMachine route
lib/features/event/widgets/event_slot_machine.dart
lib/features/event/widgets/slot_machine_lever.dart
lib/features/event/widgets/slot_reel_controller.dart
lib/features/event/screens/season_meeting_roulette_screen.dart  # SEASON (in-scope)
lib/features/tutorial/screens/slot_machine_tutorial_screen.dart
lib/features/event/screens/event_screen.dart
lib/features/event/screens/team_setup_screen.dart
lib/services/event_team_service.dart
lib/data/repositories/event_repository.dart
lib/data/models/event/event_team_match_model.dart
```

## Allowed vs forbidden

허용:

- 의존성 영향 분석을 위한 읽기
- 전체 회귀 중 기존 블라인드 관련 테스트 실행 (현재 전용 테스트 없음)
- 공용 코드 변경이 블라인드 UI를 깨지 않았는지 검증
- 본 문서 갱신 (checksum/상태)

금지:

- `random_mathcing_screen.dart` 내용 변경
- 블라인드 미팅 기능·매칭·데이터모델·analytics 변경
- 블라인드 전용 dead code 삭제

## DEFERRED_PROTECTED_SCOPE findings

(읽기 중 발견 시 아래에만 기록 — 수정하지 않음)

_없음 — 초기 스냅샷 시점_

## Regression protocol for shared-file edits

```text
1. 변경 전 관련 테스트 실행
2. 영향 경로 조사
3. 블라인드 동작이 바뀌지 않는 최소 수정
4. 변경 후 동일 테스트 재실행
5. 독립 검토자가 diff 확인
6. 동작 변화 가능성 남으면 공용 변경 보류
```
