# 설레연 AI 추천 모델

CLIP, SVD, KNN, RRF 통합 추천 파이프라인. 결과는 Firestore `modelRecs/{uid}/daily/{dateKey}/sources/` 에 저장됩니다.

## Firestore 저장 경로

| 소스 | 경로 |
|------|------|
| SVD | `modelRecs/{uid}/daily/{dateKey}/sources/svd` |
| KNN | `modelRecs/{uid}/daily/{dateKey}/sources/knn` |
| CLIP | `modelRecs/{uid}/daily/{dateKey}/sources/clip` |
| RRF (통합) | `modelRecs/{uid}/daily/{dateKey}/sources/rrf` |

앱은 **rrf → clip → svd** 순으로 폴백하여 피드를 로드합니다.

## 의존성 설치

```bash
cd lib/ai_recommend_model
pip install -r requirements.txt
pip install -r requirements_svd.txt
```

## 전체 파이프라인 실행

```bash
python seolleyeon_run_all.py --firestore_project seolleyeon --date_key 20250309
```

## 개별 실행

```bash
# 1. SVD
python seolleyeon_svd_train_export.py --firestore_project seolleyeon --date_key 20250309 --firestore_events

# 2. KNN
python seolleyeon_knn_train_export.py --firestore_project seolleyeon --date_key 20250309 --firestore_events

# 3. CLIP (torch/transformers 필요)
python seolleyeon_clip_train_export.py --firestore_project seolleyeon --date_key 20250309

# 4. RRF (통합)
python seolleyeon_rrf_export.py --firestore_project seolleyeon --date_key 20250309
```

## 입력 데이터

- **recEvents**: `recEvents/{userId}/events` 서브컬렉션 (open, like, nope 등)
- **users**: `users/{uid}` 문서의 `onboarding.photoUrls` (CLIP용)

## 권장 운영

- Cloud Run Job / VM / 내부 서버에서 **하루 1회** 실행
- `date_key`는 KST 기준 YYYYMMDD
