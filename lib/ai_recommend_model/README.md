# 설레연 AI 추천 모델

1:1 피드 추천과 3:3 미팅(그룹) 추천 파이프라인이 `lib/ai_recommend_model`에 있습니다.

| 구분 | 권장 버전 | 요약 |
|------|-----------|------|
| **1:1 피드** | **v3** | CLIP / SVD / KNN → RRF. 공통 로직은 `seolleyeon_rec_common_v3.py`, 오케스트레이션은 `seolleyeon_run_all_v3.py` |
| **1:1 (레거시)** | 비 v3 | `seolleyeon_run_all.py`, `seolleyeon_*_train_export.py` — Cloud Run `recsys.main`이 호출하는 이름과 동일 |
| **3:3 미팅** | **v1** | `seolleyeon_meeting_*_v1.py`, `seolleyeon_meeting_run_all_v1.py`, 의존성은 `requirements_meeting.txt` |

Cloud Scheduler·Docker·Workflow로 돌리는 배포 경로는 **`recsys/README.md`** 를 참고하세요(현재 `recsys.main`은 레거시 1:1 스크립트를 호출합니다).

---

## 1:1 피드 — Firestore 저장 경로

결과는 Firestore `modelRecs/{uid}/daily/{dateKey}/sources/` 아래에 저장됩니다.

| 소스 | 경로 |
|------|------|
| SVD | `modelRecs/{uid}/daily/{dateKey}/sources/svd` |
| KNN | `modelRecs/{uid}/daily/{dateKey}/sources/knn` |
| CLIP | `modelRecs/{uid}/daily/{dateKey}/sources/clip` |
| RRF (통합) | `modelRecs/{uid}/daily/{dateKey}/sources/rrf` |

앱은 **rrf → clip → svd** 순으로 폴백하여 피드를 로드합니다.

---

## 의존성 설치

### 1:1 v3 / 레거시 1:1 (공통 기본)

```bash
cd lib/ai_recommend_model
pip install -r requirements.txt
pip install -r requirements_svd.txt
```

### 3:3 미팅 v1 (추가)

CLIP·torch 등이 포함되어 있어 1:1만 돌릴 때는 생략 가능합니다.

```bash
pip install -r requirements_meeting.txt
```

---

## 1:1 추천 v3 — 실행 지침

### 전체 파이프라인 (권장)

순서: **CLIP → SVD → KNN → RRF** (`seolleyeon_run_all_v3.py`).  
마지막 RRF 단계는 리포지토리 공용 **`seolleyeon_rrf_export.py`** 를 호출합니다.

```bash
cd lib/ai_recommend_model
python seolleyeon_run_all_v3.py --firestore_project YOUR_PROJECT --date_key 20260413
```

자주 쓰는 옵션:

- `--firestore_database ID` — 기본 DB가 아닐 때
- `--lookback_days 120` — 상호작용 룩백 일수
- `--events_layout auto|top_level|user_subcollections` — `recEvents` 저장 레이아웃
- `--apply_policy_filters` — 정책 필터 적용
- `--skip_clip` / `--skip_svd` / `--skip_knn` / `--skip_rrf` — 단계 생략

인증: `gcloud auth application-default login` 또는 서비스 계정 JSON.

### v3 개별 스크립트

Firestore에서 이벤트를 읽을 때는 `--firestore_events` 를 붙입니다.

```bash
python seolleyeon_clip_train_export_v3.py --firestore_project YOUR_PROJECT --date_key 20260413 --firestore_events
python seolleyeon_svd_train_export_v3.py  --firestore_project YOUR_PROJECT --date_key 20260413 --firestore_events
python seolleyeon_knn_train_export_v3.py  --firestore_project YOUR_PROJECT --date_key 20260413 --firestore_events
```

SVD/KNN v3는 **`--events_csv`** 로 GCS 등에서 내려받은 CSV를 넣을 수도 있습니다(Cloud Run `export` 단계와 맞출 때).

RRF 예시(`seolleyeon_run_all_v3.py` 마지막 단계와 동일한 취지):

```bash
python seolleyeon_rrf_export.py --firestore_project YOUR_PROJECT --date_key 20260413 --sources clip,svd,knn --required_sources clip --topn 400 --max_items_per_source 400 --min_sources_per_user 2 --source_weights_json "{\"clip\":1.0,\"svd\":0.35,\"knn\":0.25}"
```

### 레거시 1:1 일괄 실행 (비 v3)

```bash
python seolleyeon_run_all.py --firestore_project seolleyeon --date_key 20250309
```

개별 단계는 기존과 동일하게 `seolleyeon_svd_train_export.py` 등 파일명 **접미사 없음**.

```bash
python seolleyeon_svd_train_export.py --firestore_project seolleyeon --date_key 20250309 --firestore_events
python seolleyeon_knn_train_export.py --firestore_project seolleyeon --date_key 20250309 --firestore_events
python seolleyeon_clip_train_export.py --firestore_project seolleyeon --date_key 20250309
python seolleyeon_rrf_export.py --firestore_project seolleyeon --date_key 20250309
```

---

## 3:3 미팅 추천 v1 — 실행 지침

미팅 파이프라인은 **그룹 인덱스 → 그룹 랭커 → 일별 최종 추천 → 검증** 순입니다.

| 단계 | 스크립트 | 기본 출력(요약) |
|------|-----------|-----------------|
| 1 | `seolleyeon_meeting_group_index_export_v1.py` | `meetingGroupIndex` |
| 2 | `seolleyeon_meeting_recommend_export_v1.py` | `meetingModelRecs` (그룹 랭커) |
| 3 | `seolleyeon_meeting_daily_recs_export_v1.py` | `meetingDailyRecs` |
| 4 | `seolleyeon_meeting_verify_v1.py` | 검증 로그 / 요약 |

### 한 번에 실행

```bash
cd lib/ai_recommend_model
pip install -r requirements_meeting.txt

python seolleyeon_meeting_run_all_v1.py --firestore_project YOUR_PROJECT --date_key 20260413
```

선택: `--firestore_database`, `--skip_group_index`, `--skip_recommend`, `--skip_daily`, `--skip_verify`.

### 오프라인 평가 (선택)

```bash
python seolleyeon_meeting_eval_v1.py --firestore_project seolleyeon --date_key 20260413
```

컬렉션 이름·소스 종류는 스크립트의 CLI 도움말(`--help`)을 참고하세요.

---

## 입력 데이터 (요약)

### 1:1

- **recEvents**: `recEvents/{userId}/events` (또는 레이아웃에 따라 상위 컬렉션) — open, like, nope 등
- **users**: `users/{uid}` 의 `onboarding.photoUrls` 등 (CLIP용)

### 미팅 v1

- **meetingGroups**, **recEvents** (`targetType` 등은 `seolleyeon_meeting_common_v1.py` 참고)

---

## 권장 운영

- 배치 서버 / Cloud Run Job / VM에서 **하루 1회** 등 스케줄 실행
- `date_key`는 **KST 기준 YYYYMMDD**
- 1:1 v3와 Cloud Run 레거시 파이프라인의 차이·GCS export 여부는 **`recsys/README.md`** 의 「버전 구분」「Data Flow」 참고
