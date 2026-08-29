# 00 — 총괄 요약 (Fable 5 감사, 2026-08-28)

> **상태 갱신 (Tier 1·2 이후)**: 이 문서의 최초 판정은 "감사만, 코드수정 없음"
> 이었으나 이후 Tier 1(SEC-05/11/18)과 Tier 2(SEC-03/08/09/P3-01) source 수정이
> working tree 에 적용되었다(커밋·배포 없음). SEC-04 는 대규모 데이터
> 마이그레이션 결정 대기. 현재 상태의 정본은 `09-change-log.md`(Tier 1·2) 와
> `10-verification-results.md`. 아래 원문은 최초 스냅샷으로 보존한다.

## 전체 판정

```
최초:   BLOCKED (감사·검증 완료 / 코드 수정 승인 대기)
현재:   TIER1+TIER2 SOURCE-REMEDIATED (working tree, 미커밋·미배포)
        · Tier1: SEC-05/11/18 FIXED_IN_WORKTREE, LOCAL_VERIFIED
        · Tier2: SEC-08/09/P3-01 SOURCE_FIXED+LOCAL_VERIFIED, NOT_DEPLOYED
                 SEC-03 강제 불변식 확정+테스트, 근본은 코드회전(EXTERNAL)
                 SEC-04 DECISION / DATA_MIGRATION_REQUIRED (미적용)
        · EXTERNAL: 배포·IAM·시크릿회전·코드회전·데이터마이그레이션 전부 미수행
```

전체 저장소를 6개 도메인 병렬 read-only 감사 → 기준선 측정 → 상위 발견 메인 재검증까지 완료했다. 이후 Tier 1·2 에서 저위험·범위내 source 수정을 RED→GREEN 으로 적용했다(커밋/배포 없음). 남은 blocker 는 §Blocker.

## 기준선 (2026-08-28 실측)

| 검증 | 결과 |
|---|---|
| flutter analyze | No issues (0) |
| flutter test | 656 pass |
| functions npm test / lint / build | 431 pass / pass / pass |
| recsys pytest | 181 pass |
| **tests/ pytest** | **921 pass / 16 fail** — 전부 미커밋 아바타 WIP |
| rules emulator (main) | 72 pass |
| festival rules emulator | 없음 (미구성) |

## 핵심 발견 (상세 [04](04-security-findings.md), [05](05-correctness-performance-fallback.md))

- **P0 개인정보/git (SEC-01/02)**: 실 UID↔얼굴사진 동의증빙 3파일 + 실사용자 recEvents CSV가 git 추적 중. 과거 PII 사고 재발 클래스.
- **P1 festival 티켓 탈취 (SEC-03)**: rules가 `lastUid` 재바인딩 허용 → 로그인 사용자가 커밋된 코드로 남의 티켓/프로필/채팅 점유. 축제 웹은 rules 테스트 0건. → *Tier2: 규칙이 이미 타인 명의 위조는 차단함을 확인, festival rules 테스트 19건 신설. 근본(공개 bearer 코드)은 코드 회전(EXTERNAL).*
- **P1 대나무숲 익명성 붕괴 (SEC-04)**: 실 authorId 저장 + 로그인이면 read 가능 → 학교인증 커뮤니티 고백글 작성자 특정. → *Tier2: 재검증 CONFIRMED. 대규모 데이터 마이그레이션 필요(STOP #3) — 설계+dry-run 스크립트만 산출, 미적용.*
- **P1 blindMeeting fail-open (SEC-05)**: 차단·제재 로드 실패 시 통과 → fail-closed 규칙 위반.
- **P1 FCM 토큰 수명주기 (SEC-06/COR-01)**: 로그아웃 시 미삭제(이전계정 푸시 지속), 로그인 시 미등록(재시작 전 푸시 불가).
- **P1 avatar WIP 고착 (SEC-07/COR-02)**: Azure claim 만료·복구 없음, `needs_review` dead-end → 사용자 영구 잠김. 미커밋 델타에서 유입.
- **P2**: festival 사진 대량 스크래핑, festival 공개 관리자 엔드포인트, 채팅 차단/매칭 미검증, App Check 2개 디스패처 누락, 추천 banned 미제외·클라 타임스탬프 위조, avatar 워커 IAM 단일계층, staging이 프로덕션 PII 접근.
- **제품결정(수정 전 사용자 확인 필수)**: 성인인증(SEC-14)·안전스탬프(SEC-15) 릴리스 비활성 — 의도적 토글로 보이며, 임의 되돌리면 의도한 런칭 구성 파손 가능.

## Blocker (수정 진행을 막는 조건 — §22)

1. **작업 트리에 대규모 미커밋 사용자 변경**: staged 삭제 5,868건 + 아바타 WIP 32파일(+1,717/−279)에 **RED 테스트 16건**. 이 상태에 내 수정을 얹으면 사용자 WIP와 엉켜 논리적 단위 커밋 불가·`사용자 미커밋 작업 함께 커밋 금지` 위반.
2. **제품결정 항목**: SEC-14/15는 의도적 비활성 토글 — 되돌림 여부는 사용자 판단.
3. **외부 승인 필요**: SEC-01/02 history rewrite, App Check 강제, 배포는 §금지목록.
4. **협업 방식**: 사용자는 통상 Codex에 단일 markdown block으로 위임(메모리) — 대량 자동수정이 워크플로와 불일치할 수 있음.

## 권장 수정 우선순위 (승인 시)

[08-remediation-plan.md](08-remediation-plan.md) 참조. 요약: 즉시 SEC-01/02(git 추적해제) → SEC-05·SEC-11(서버 fail-closed, 저위험) → SEC-03/04/08/09(festival+커뮤니티, rules+테스트) → SEC-06/COR-01(FCM) → SEC-07/COR-02(avatar, 단 WIP 소유자와 조율).
