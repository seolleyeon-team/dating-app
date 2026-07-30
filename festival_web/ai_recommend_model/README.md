# Festival Web 추천 파이프라인

설레연 메인 앱(`lib/ai_recommend_model/`)의 CLIP → RRF 구조를 **페스티벌 웹**(`seolleyeon-festival`)에 맞게 단순화한 버전입니다.

## 데이터 흐름

```
[입력]
  festivalTickets/{ticketId}/tasteSwipes     — AI 카드 like/dislike (호감도 원천)
  festivalTickets/{ticketId}.preferenceVector — 취향 완료 후 CLIP preference (선택)
  festivalTickets/{ticketId}.aiProfileAffinities — AI 프로필별 0/1 호감 맵
  festivalAiEmbeddings/{code}                — AI 카드 CLIP 벡터 (f1..f20, m1..m20)
  festivalProfileEmbeddings/{ticketId}     — 실제 참가자 프로필 CLIP 벡터
  festivalProfiles/{ticketId}                — 추천 후보 메타 (성별, MBTI 등)

[배치 출력]
  festivalModelRecs/{ticketId}/daily/{YYYYMMDD}/sources/clip

[웹 앱]
  FestivalRecommendationEngine → festivalModelRecs 읽기 (없으면 라이브 계산)
```

## 메인 앱 파이프라인과의 차이

| 항목 | 메인 앱 (`seolleyeon`) | 페스티벌 웹 (`seolleyeon-festival`) |
|------|------------------------|-------------------------------------|
| 사용자 키 | Firebase `uid` | 입장 코드 `ticketId` |
| 이벤트 | `recEvents` | `tasteSwipes` + (확장) |
| 출력 | `modelRecs/.../sources/{clip,svd,knn,rrf}` | `festivalModelRecs/.../sources/clip` |
| 실행 | Cloud Run Jobs + Workflows (매일 04:00 KST) | Cloud Functions 스케줄 (매일 17:00 KST) + 웹 라이브 폴백 |
| 알고리즘 | CLIP + SVD + KNN + RRF | CLIP 중심 (v1) |

## 스크립트

| 파일 | 설명 |
|------|------|
| `festival_export_ai_embeddings.py` | AI 카드 40장 CLIP 임베딩 → `festivalAiEmbeddings` |
| `festival_export_profile_embeddings.py` | 참가자 프로필 사진 임베딩 → `festivalProfileEmbeddings` |
| `festival_clip_recommend.py` | 전체 ticket 대상 CLIP 추천 → `festivalModelRecs` |
| `festival_run_all.py` | 위 3단계 일괄 실행 |

## 로컬 실행 예시

```bash
cd festival_web/ai_recommend_model
pip install -r requirements.txt

export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export FIREBASE_STORAGE_BUCKET=seolleyeon-festival.firebasestorage.app

python festival_run_all.py \
  --project seolleyeon-festival \
  --date_key 20260527
```

## Cloud Functions (서버 배치)

`festival_web/functions/src/festival_recommendations.ts`

- `onFestivalTasteCompleted` — 취향 학습 완료 시 해당 ticket 추천 생성
- `generateFestivalDailyRecommendations` — 매일 17:00 KST 전체 재생성
