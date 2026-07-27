# 14 — 추천 정책 P0 발견 사항 및 수정 (Opus 5 감사)

작성 시각: 2026-07-27
감사 방식: 정적 코드 분석 + 운영 Firestore 컬렉션 목록 읽기 전용 조회 + pytest 검증

이 문서는 1:1 추천 파이프라인(CLIP / SVD / KNN / RRF)의 **정책이 코드에는
구현되어 있으나 실행 경로에서 적용되지 않던** 문제를 다룬다. 앞선 감사에서
반복적으로 나타난 패턴("정책은 있는데 켜지지 않음")의 추천 시스템 사례다.

---

## 요약

| ID | 등급 | 제목 | 상태 |
|----|------|------|------|
| REC-P0-01 | P0 | 후보 정책 필터가 운영에서 완전히 비활성 | **수정 완료** |
| REC-P0-02 | P0 | `profileIndex` 컬렉션 부재 — 정책 필터를 켜면 추천 0건 | **수정 완료** |
| REC-P0-03 | P0 | RRF 품질 게이트(`required_sources`, `min_sources_per_user`) 미적용 | **수정 완료** |
| REC-P0-04 | P0 | 차단·신고가 단방향 — 피차단자에게 차단자가 계속 추천됨 | **수정 완료 (파이썬 파이프라인)** |
| REC-P1-01 | P1 | 클라이언트 `blockAndReportUser`가 단방향으로만 기록 | 확정, 미수정 (후속) |
| REC-P1-02 | P1 | `_fetchFallbackFromUsers`가 정책 무시 프로필을 추천으로 표시 | 확정, 미수정 (후속) |

---

## REC-P0-01 — 후보 정책 필터가 운영에서 완전히 비활성

**영역:** Cloud Run Jobs / Cloud Workflows / 추천 파이프라인

### 근거

후보 정책(인증 여부, 활성 여부, 매너 점수 하한, 선호 나이,
상호성, 동일 대학)은 `seolleyeon_rec_common_v3.passes_policy`에 구현되어
있으나, 모든 v3 학습·익스포트 스크립트에서 `--apply_policy_filters` 플래그가
**꺼져 있을 때는 아예 호출되지 않는다**(`meta = None`이면 정책 검사 블록을
건너뜀).

그리고 운영 실행 경로 어디에서도 이 플래그를 넘기지 않았다.

- `infra/workflows/recs_pipeline.yaml`은 각 Job에 `--step`, `--date-key`,
  `--project`, `--bucket`만 전달한다.
- `recsys/main.py`의 `step_clip` / `step_svd` / `step_knn`은 받은 인자를
  그대로 통과시킬 뿐 정책 인자를 추가하지 않았다.

반면 저장소의 참조 오케스트레이터 `seolleyeon_run_all_v3.py`는
`--apply_policy_filters`를 지원한다. 즉 **정책은 "로컬에서 수동 실행할 때만"
동작하고 운영 배치에서는 한 번도 적용된 적이 없다.**

### 영향

미인증(`isStudentVerified != true`)·비활성·매너 점수 미달 사용자, 선호 나이
범위를 벗어난 사용자, 상호 선호가 성립하지 않는 사용자가 그대로 추천 후보에
포함된다. 동성 제외와 승인 아바타 게이트만 작동하고 있었다.

### 수정

`recsys/main.py`에서 정책 인자를 **기본 활성**으로 구성하고, 인자 조립을
순수 함수 `build_model_script_args` / `build_rrf_script_args`로 분리해
테스트 가능하게 했다. Workflow를 수정하지 않아도(= 인자를 전혀 넘기지 않아도)
필터가 걸리도록 기본값 쪽에 정책을 두었다.

디버깅용 이탈구는 `--no-apply-policy-filters`로 명시해야만 열린다.

---

## REC-P0-02 — `profileIndex` 컬렉션 부재로 정책 필터가 "켜면 전멸"

**영역:** Firestore 데이터 소스

이 항목이 REC-P0-01을 단순히 "플래그만 켜면 됨"으로 처리할 수 없게 만든
핵심 제약이다.

### 근거

`passes_policy`는 조회자·후보 중 하나라도 메타데이터에 없으면 `False`를
반환한다.

```869:882:lib/ai_recommend_model/seolleyeon_rec_common_v3.py
def passes_policy(
    user_id: str,
    cand_id: str,
    meta: Dict[str, Dict[str, Any]],
    *,
    manner_min: float,
    active_within_days: int,
    require_same_university: bool,
    reciprocal: bool,
) -> bool:
    mu = meta.get(user_id)
    mv = meta.get(cand_id)
    if mu is None or mv is None:
        return False
```

메타데이터는 `load_profile_index_from_firestore`가 `profileIndex` 컬렉션에서
읽는다. 그런데 `profileIndex`는 **저장소 전체에서 읽히기만 하고 어디서도
쓰이지 않는다.** Cloud Functions는 `loadCollectionDocsByIds("profileIndex", …)`로
읽기만 하고, Flutter 클라이언트에는 참조 자체가 없다.

2026-07-27 운영 프로젝트 `seolleyeon-final`의 최상위 컬렉션을 읽기 전용으로
조회한 결과, **`profileIndex`는 존재하지 않는다.**

```
ai_profiles, app_inquiries, app_issue_reports, asks, avatarCandidates,
avatarJobs, bamboo_posts, chat_rooms, emailLinkTokens, eventTeamInvites,
eventTeamSetups, friendInvites, friendships, interactions, meetingGroups,
place_catalog_items, place_catalog_meta, recEvents, reports,
userPrivateMedia, users
```

따라서 `--apply_policy_filters`만 켰다면 `meta == {}`가 되어 모든 쌍이
`False`로 떨어지고 **추천이 전량 0건**이 되는데, 스크립트는 이를 오류가 아닌
정상 종료로 처리한다(빈 피드를 export하고 exit 0). 즉 조용한 전면 장애다.

`require_same_university`가 기본 `True`인 점도 같은 함정을 만든다.
`users` 문서에 `universityId`가 없으면 이 검사 하나만으로 전원 탈락한다.

### 수정

1. `build_policy_meta_from_user_docs` — 실제로 존재하는 `users` 컬렉션에서
   동일한 정책 필드를 파생한다. 학교는 `studentEmail` 도메인에서 유도하므로
   (`@yonsei.ac.kr` → `yonsei`) `universityId` 필드가 없어도 동일 대학 검사가
   성립한다.
2. `load_policy_meta_from_firestore` — `profileIndex`를 우선 사용하고, 비어
   있으면 `users`로 폴백하며 어느 소스를 썼는지 반환·로깅한다.
3. `assert_policy_meta_coverage` — **fail-loud 가드.** 메타데이터가 후보
   사용자의 일정 비율(기본 90%, `--policy_min_meta_coverage`)을 덮지 못하면
   빈 피드를 내보내는 대신 예외를 던져 Job을 실패시킨다.

3번이 이 수정의 핵심이다. 상류 데이터가 깨졌을 때 "조용히 0건"이 아니라
"시끄럽게 실패"하도록 만든다.

---

## REC-P0-03 — RRF 품질 게이트 미적용

**영역:** Cloud Run Jobs

### 근거

`seolleyeon_rrf_export.py`의 기본값은 `--required_sources ""`,
`--min_sources_per_user 1`이다. 참조 오케스트레이터는 이를 명시적으로
덮어쓴다.

```96:101:lib/ai_recommend_model/seolleyeon_run_all_v3.py
            "--sources", "clip,svd,knn",
            "--required_sources", "clip",
            "--topn", "400",
            "--max_items_per_source", "400",
            "--min_sources_per_user", "2",
            "--source_weights_json", DEFAULT_RRF_SOURCE_WEIGHTS,
```

`recsys/main.py`의 `step_rrf`는 이 중 어느 것도 넘기지 않았다.

### 영향

CLIP(외모·선호 신호)이 전혀 없고 SVD 협업 신호만 있는 사용자도 "AI 통합
추천(RRF)"으로 내보내진다. 단일 소스 결과가 다중 소스 융합 결과인 것처럼
사용자에게 제시된다.

### 수정

`build_rrf_script_args`가 `required_sources=clip`, `min_sources_per_user=2`,
`topn=400`, `max_items_per_source=400`, 소스 가중치를 기본으로 전달한다.

---

## REC-P0-04 — 차단·신고가 단방향

**영역:** 추천 파이프라인 / 사용자 안전

### 근거

파이썬 파이프라인에서 차단·신고는 **행위자 본인의 negative 이벤트**로만
처리된다. `collapse_pair_events`가 만드는 `neg_df`는 `user_id → item_id`
방향이고, 각 익스포터는 이를 `filter_items` / `exclude`에 넣는다.

따라서 A가 B를 차단하면 A에게 B는 사라지지만, **B에게 A는 계속 추천된다.**
B는 A의 프로필을 보고 like를 보낼 수 있다. 신고자가 신고 대상에게 계속
노출되는 것은 안전 기능의 실패다.

미팅(그룹) 파이프라인에는 이미 대칭 제외가 구현되어 있다
(`seolleyeon_meeting_common_v1.build_cross_user_block_pairs`가
`tuple(sorted((actor, target)))`로 무순서 쌍을 만든다). **1:1 파이프라인에만
이 대응물이 없었다.**

### 수정

`seolleyeon_rec_common_v3.build_mutual_block_index`를 추가했다. `block`과
`report`만 대칭으로 확장하고, 취향 신호인 `nope`는 단방향으로 유지한다.
CLIP·SVD·KNN v3 세 익스포터가 모두 이 인덱스를 후보 생성 단계에서 적용한다.

SVD/KNN은 모델의 `filter_items`와 후보 루프 양쪽에서 제외한다. 모델이
`filter_items`를 어떻게 해석하든 안전 불변식이 후보 루프에 국소적으로
남아 있도록 하기 위함이다.

### 남은 범위

**클라이언트와 Cloud Functions는 아직 단방향이다.** `interaction_service.dart`의
`blockAndReportUser`는 `blocks/{fromUserId}/targets/{toUserId}` 한쪽만 쓰고,
`_fetchBlockedUids`는 자기 목록만 읽는다. 연락처 기반 차단
(`ensureMutualContactBlock`)은 이미 양방향으로 쓰고 있으므로, 신고 기반 차단도
동일하게 서버에서 양방향 기록하도록 맞추는 것이 자연스럽다. REC-P1-01로 분리.

---

## 검증

```
recsys\.venv\Scripts\python.exe -m pytest tests -q
565 passed, 6 skipped in 78.97s
```

신규 테스트 29건:

- `tests/test_recsys_policy_args.py` — Cloud Workflow가 실제로 보내는 인자
  조합(`--step/--date-key/--project/--bucket`)만 파싱했을 때 정책 필터와 RRF
  품질 게이트가 하위 스크립트 인자에 나타나는지 검증한다.
- `tests/test_rec_policy_and_blocks.py` — 대칭 차단 확장, `nope`의 단방향
  유지, `users` 기반 정책 메타 파생, 학교 도메인 유도, 커버리지 부족 시
  예외 발생을 검증한다.

세 익스포트 스크립트는 `--help`로 임포트·파서 정상 동작을 확인했다.

**주의:** 이 저장소에는 `pytest`가 어떤 requirements 파일에도 없었고,
기존 `tests/` 20여 개 파일이 실행된 흔적이 없다. 검증을 위해 `recsys/.venv`에
`pytest`를 설치했다. CI 게이트 구성 시 테스트 의존성을 명시해야 한다.

---

## 배포 시 주의

정책 필터가 기본 활성으로 바뀌므로, **첫 운영 실행 전에 dry-run으로 커버리지와
후보 수 변화를 확인**해야 한다. 확인 없이 배포하면 두 가지 중 하나가 발생한다.

1. 커버리지가 90% 미만 → Job이 의도적으로 실패한다(설계된 동작).
2. 커버리지는 충분하나 `isStudentVerified` 미충족 사용자가 많음 → 추천 후보가
   크게 줄어든다. 이는 정책상 올바른 동작이지만 체감 변화가 크다.

승인 아바타 게이트(`require_approved_avatar_for_candidates`, 기본 `True`)가
이미 `isStudentVerified`·`isActive`·`isProfileComplete`를 강제하고 있으므로
2번의 증분 영향은 제한적일 것으로 보이나, 실측 전에는 단정할 수 없다.
