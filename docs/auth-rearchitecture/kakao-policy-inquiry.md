# Kakao 소셜 API 정책 서면 문의 (Blocker #1)

상태: `KAKAO_POLICY_EXTERNAL_APPROVAL_BLOCKED` (2026-09-01 기준 저장소 전체에서 Kakao의 서면 승인
artifact 미발견 — infra audit로 재확인). 이 gate는 테스트로 대체할 수 없으며, PASS 전까지
production deploy 금지 (`TECHNICALLY_READY_POLICY_BLOCKED` 상태로 대기).

## Kakao Developers / 고객센터 발송용 문의문 (그대로 사용)

> 카카오톡 친구 목록 API를 통해 확인한 친구 관계를
> 다른 사용자에게 표시하거나 추천 점수 산정에 사용하지 않고,
> 오직 서로 데이팅 추천 결과에서 제외하기 위한 목적으로
> 설레연 내부 사용자 ID 간 관계(pair)만 저장하려고 합니다.
>
> Kakao 프로필, 닉네임, 이메일, 전화번호,
> 원본 친구목록 및 raw Kakao friend identifier 목록은 저장하지 않습니다.
> 친구 관계로 확인된 두 설레연 내부 사용자 ID 간 pair만 저장하고,
> 둘 중 한 사용자가 '카카오 친구 피하기' 기능을 활성화하면
> 서로 추천 후보에서 제외하기 위한 용도로만 사용합니다.
>
> 이와 같이 친구 관계 여부를 내부 exclusion 데이터로
> 저장 및 사용하는 것이 카카오톡 소셜 API 이용정책상 허용되는지
> 서면 확인 부탁드립니다.

## 승인 artifact 수령 시 검증 절차

1. 답변 원문(스크린샷/메일 본문)을 `docs/auth-rearchitecture/artifacts/` 아래에 보관.
2. 답변 문구가 다음 구현 사실과 정확히 일치하는지 대조:
   - 친구 관계/프로필을 사용자에게 미노출, 추천 점수 미사용
   - 내부 appUserId pair + exclusion 상태만 저장 (raw 친구목록·프로필·토큰 미저장)
   - 계정당 1회 snapshot, 피하기 ON 시 상호 제외 목적
3. 일치하면 `KAKAO_POLICY_WRITTEN_APPROVAL_PRESENT`로 gate 갱신 후 production release-gate 재평가.
   불일치·조건부 허용이면 조건을 구현에 반영한 뒤 재평가.
