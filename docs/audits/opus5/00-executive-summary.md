# 00 — 총괄 요약 (Opus 5 감사)

작성 시각: 2026-07-27  
최종 갱신: 2026-07-29  
감사 범위: 설레연(Seolleyeon) 저장소 전체 대상 정적 분석 → 에뮬레이터 검증 → 운영 배포

## 전체 판정

```
HARDENING_IN_PROGRESS → P0/P1 핵심 조치 완료
```

초기 감사 시점의 `BLOCKED`(셸 부재·P0 미수정)는 **해소**되었다.
P0 인증/규칙 취약점과 P1 핵심 항목은 코드 수정 후 `seolleyeon-final`에 배포되었다.
남은 작업은 운영 가드 강화(App Check Firestore/Auth ENFORCED 등)와 잔여 residual 정리이다.

## 완료된 핵심 조치 (요약)

| 구간 | 결과 |
|------|------|
| SEC-P0-01~04 | Firestore rules + emailLink exchange 수정·배포 (`b1ab01b`) |
| SEC-P0-05 | 개방 운영 규칙을 저장소본으로 교체 배포 (2026-07-27) |
| SEC-P1-05 | 인증/부트스트랩 callable App Check (`809fa537`) |
| SEC-P1-06 | 배치 recsys Firestore blocks 제외 + 이미지/Jobs (`bc554be8`) |
| SEC-P1-07 | FCM 차단·탈퇴 필터 (`f92408b5`) |
| SEC-P1-08 | 탈퇴 PII + 소셜 residual 정리 (`247d0b64` + comments soft-delete) |
| SEC-P2-01/02, SEC-P3-01 | bamboo 카운터·match race·place_catalog 중복 수정·배포 |
| Ops | 만료 emailLinkTokens 28건 purge, Storage App Check **ENFORCED** |

상세: [04-security-findings.md](04-security-findings.md), [15-needs-verification-results.md](15-needs-verification-results.md).

## 즉시 대응이 필요했던 사항 (초기 감사 — 현재는 수정됨)

### SEC-P0-01 — 비인증 임의 계정 탈취 (당시 최우선)

`emailLinkTokens` 비인증 create + custom token 교환이 맞물려 계정 탈취가
가능했다. **현재는 rules·callable 검증으로 차단**되었다.

### 나머지 P0 (당시)

- SEC-P0-02/03/04: `users` 비인증 생성·이메일 탈취·전체 list — **수정·배포 완료**
- SEC-P0-05: 운영 규칙이 저장소보다 개방 — **rules 재배포로 해소**

## 잔여 / 주의 항목

1. **Firestore·Auth App Check**는 아직 UNENFORCED (웹 reCAPTCHA site key·레거시 클라이언트 리스크).
2. **채팅 메시지 본문**은 탈퇴 시 보존(상대 분쟁·안전 증빙).
3. 만료 `emailLinkTokens` **일일 스케줄 purge**로 재적체 방지.
4. 추천/보안 정책의 상세는 14·15번 문서를 기준으로 한다.

## Production Readiness

현 시점: **조건부 READY** — P0 공개 표면은 닫혔고 P1 핵심 hardening이 운영에 반영됨.
App Check ENFORCED 확대·메시지 retention 정책은 제품/법무 결정 후 진행.
