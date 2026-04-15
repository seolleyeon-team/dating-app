# Seolleyeon Recommendation Pipeline — Cloud Run Jobs

## 버전 구분

| 영역 | 권장 버전 | 코드 위치 | 비고 |
|------|-----------|-----------|------|
| **1:1 피드 추천** | **v3** | `lib/ai_recommend_model/seolleyeon_*_v3.py`, `seolleyeon_rec_common_v3.py`, `seolleyeon_run_all_v3.py` | CLIP을 앵커로 두고 SVD/KNN은 보조; RRF는 `seolleyeon_rrf_export.py`로 병합 |
| **3:3 미팅(그룹) 추천** | **v1** | `lib/ai_recommend_model/seolleyeon_meeting_*_v1.py` | `meetingGroupIndex` → `meetingModelRecs` → `meetingDailyRecs` |

아래 **Cloud Run / `recsys.main`** 은 배포 편의를 위해 **접미사 없는 레거시 스크립트**(`seolleyeon_svd_train_export.py` 등)를 호출합니다. **운영·실험 기준 1:1 로직은 v3**를 보시면 됩니다. 상세 실행은 `lib/ai_recommend_model/README.md` 참고.

## Architecture

```
Cloud Scheduler (매일 04:00 KST)
  → Workflows (recs-pipeline)
      → [1] recs-export      (recEvents → GCS CSV)
      → [2] recs-clip / recs-svd / recs-knn  (병렬)
      → [3] recs-rrf         (RRF merge → modelRecs)
      → [4] recs-verify      (health check)
```

단일 Docker 이미지 + 6개 Cloud Run Job + 1개 Workflow + 1개 Scheduler.

## File Structure

```
semisemifinal/
├── recsys/
│   ├── main.py                  # 통합 entrypoint (--step 디스패처)
│   ├── requirements.txt         # Python 의존성 (통합)
│   ├── Dockerfile               # Multi-stage (CPU PyTorch + CLIP 모델 포함)
│   ├── README.md                # 이 문서
│   └── jobs/
│       ├── common.py            # 로깅, GCS 헬퍼, 날짜 유틸
│       ├── export_job.py        # Firestore recEvents → GCS CSV
│       └── verify_job.py        # 파이프라인 결과 검증
├── lib/ai_recommend_model/      # ML 스크립트 (레거시 1:1 / v3 1:1 / 미팅 v1)
│   │                            # — recsys.main·Docker는 아래 레거시 파일명 호출
│   ├── seolleyeon_svd_train_export.py
│   ├── seolleyeon_knn_train_export.py
│   ├── seolleyeon_clip_train_export.py
│   ├── seolleyeon_clip_embedder.py
│   ├── seolleyeon_rrf_export.py
│   ├── seolleyeon_run_all.py
│   │                            # — 권장 1:1 v3
│   ├── seolleyeon_rec_common_v3.py
│   ├── seolleyeon_clip_train_export_v3.py
│   ├── seolleyeon_svd_train_export_v3.py
│   ├── seolleyeon_knn_train_export_v3.py
│   ├── seolleyeon_run_all_v3.py
│   │                            # — 3:3 미팅 v1
│   ├── requirements_meeting.txt
│   ├── seolleyeon_meeting_common_v1.py
│   ├── seolleyeon_meeting_group_index_export_v1.py
│   ├── seolleyeon_meeting_recommend_export_v1.py
│   ├── seolleyeon_meeting_daily_recs_export_v1.py
│   ├── seolleyeon_meeting_verify_v1.py
│   ├── seolleyeon_meeting_eval_v1.py
│   └── seolleyeon_meeting_run_all_v1.py
├── infra/
│   ├── workflows/recs_pipeline.yaml   # Workflows 정의
│   └── deploy.sh                      # 원클릭 배포 스크립트
├── cloudbuild.yaml              # Cloud Build 설정
└── .dockerignore                # Docker 빌드 컨텍스트 필터
```

## Data Flow

### Cloud Run / `recsys.main` 경로 (GCS CSV 경유)

```
[Firestore]                    [GCS]                      [Firestore]
recEvents/{uid}/events  →  gs://bucket/recs/{date}/  →  modelRecs/{uid}/daily/{date}/sources/
                            events.csv                    ├── svd
                                                          ├── knn
users/{uid}  ─────────────────────────────────────────→   ├── clip
                                                          └── rrf
```

### 1:1 v3 직접 실행 시 (선택)

`seolleyeon_run_all_v3.py`는 SVD/KNN/CLIP이 Firestore `recEvents`를 **`--firestore_events`로 직접 읽는 경로**를 씁니다(GCS 없이도 동작). RRF는 위와 동일하게 `modelRecs/.../sources/rrf`에 기록됩니다.

앱은 **rrf → clip → svd** 순으로 폴백하여 피드를 로드합니다.

### 3:3 미팅 (v1) — Firestore

| 단계 | 컬렉션 / 경로 (기본값) |
|------|-------------------------|
| 그룹 인덱스 | `meetingGroups` → `meetingGroupIndex/{groupId}` |
| 그룹 랭커 출력 | `meetingModelRecs/{actorGroupId}/daily/{dateKey}/sources/group_ranker` |
| 최종 일별 추천 | `meetingDailyRecs/{actorGroupId}/days/{dateKey}` |

이벤트는 `recEvents`에서 `targetType == meeting_group` 등으로 집계합니다 (`seolleyeon_meeting_common_v1.py` 참고).

## 1:1 추천 (v3) — 로컬 실행

### 의존성

```bash
cd lib/ai_recommend_model
pip install -r requirements.txt
pip install -r requirements_svd.txt
```

(CLIP/SVD/KNN/RRF에 필요한 패키지가 겹칩니다. 미팅만 할 때는 `requirements_meeting.txt`를 추가로 쓰면 됩니다.)

### 전체 파이프라인 (한 번에)

실행 순서: **CLIP → SVD → KNN → RRF** (`seolleyeon_run_all_v3.py`).

```bash
cd c:\Users\samsung\StudioProjects\semisemifinal\lib\ai_recommend_model
python seolleyeon_run_all_v3.py --firestore_project seolleyeon --date_key 20260413
```

선택 인자:

- `--firestore_database <ID>` — 기본 DB가 아닐 때
- `--lookback_days 120` — 이벤트 룩백(기본 120)
- `--events_layout auto|top_level|user_subcollections` — `recEvents` 레이아웃
- `--apply_policy_filters` — 정책 필터 적용
- `--skip_clip` / `--skip_svd` / `--skip_knn` / `--skip_rrf` — 단계 스킵

인증: `gcloud auth application-default login` 또는 서비스 계정 JSON.

### v3 설계 요약 (`seolleyeon_run_all_v3.py` 주석 기준)

- **CLIP**을 앵커 소스로 두고, **SVD/KNN**은 warm-user·pruned 협업 보조로 사용
- **RRF**: `clip` 필수(`--required_sources clip`), 보수적 가중치(기본 `{"clip":1.0,"svd":0.35,"knn":0.25}`), `seolleyeon_rrf_export.py`에서 `topn` / `max_items_per_source` / `min_sources_per_user`로 제한

### 개별 스크립트 (v3)

공통으로 `--firestore_project`, `--date_key`, `--firestore_events` 및 위와 동일한 옵션을 씁니다.

```bash
python seolleyeon_clip_train_export_v3.py --firestore_project seolleyeon --date_key 20260413 --firestore_events
python seolleyeon_svd_train_export_v3.py  --firestore_project seolleyeon --date_key 20260413 --firestore_events
python seolleyeon_knn_train_export_v3.py  --firestore_project seolleyeon --date_key 20260413 --firestore_events
python seolleyeon_rrf_export.py --firestore_project seolleyeon --date_key 20260413 --sources clip,svd,knn --required_sources clip --topn 400 --min_sources_per_user 2 --source_weights_json "{\"clip\":1.0,\"svd\":0.35,\"knn\":0.25}"
```

SVD/KNN v3는 `--events_csv`로 GCS export CSV를 줄 수도 있습니다(Cloud Run export 단계와 연동 시).

## 3:3 미팅 추천 (v1) — 로컬 실행

### 의존성

```bash
cd lib/ai_recommend_model
pip install -r requirements_meeting.txt
```

주요 패키지: `numpy`, `pandas`, `scipy`, `google-cloud-firestore`, `torch`, `transformers`, `Pillow`, `requests` 등.

### 전체 파이프라인

```bash
cd c:\Users\samsung\StudioProjects\semisemifinal\lib\ai_recommend_model
python seolleyeon_meeting_run_all_v1.py --firestore_project seolleyeon --date_key 20260413
```

내부 순서:

1. `seolleyeon_meeting_group_index_export_v1.py` — `meetingGroupIndex` 빌드  
2. `seolleyeon_meeting_recommend_export_v1.py` — 그룹 랭커 → `meetingModelRecs`  
3. `seolleyeon_meeting_daily_recs_export_v1.py` — `meetingDailyRecs` 최종 문서  
4. `seolleyeon_meeting_verify_v1.py` — 산출물 검증 요약  

스킵 플래그: `--skip_group_index`, `--skip_recommend`, `--skip_daily`, `--skip_verify`.

### 오프라인 평가 (선택)

```bash
python seolleyeon_meeting_eval_v1.py --firestore_project seolleyeon --date_key 20260413
```

(인자로 소스 컬렉션 `meeting_daily_recs_collection` / `meeting_model_recs_collection` 등 조정 가능.)

## Local Development (`recsys.main`, 레거시 1:1)

Cloud Run Job과 동일한 디스패처로 **export → svd/knn(csv) → clip → rrf**를 돌릴 때 사용합니다. **`recsys.main`이 호출하는 스크립트는 v3 파일명이 아닙니다.**

### 1. 가상환경 + 의존성

```bash
cd recsys
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. 인증 (로컬)

```bash
gcloud auth application-default login
set GOOGLE_APPLICATION_CREDENTIALS=path\to\service-account.json   # 또는
```

### 3. 단계별 실행

```bash
cd c:\Users\samsung\StudioProjects\semisemifinal

# Export (GCS 버킷 필요)
python -m recsys.main --step export --project seolleyeon --bucket seolleyeon-recs

# SVD (GCS에서 CSV 다운로드 → 학습 → Firestore 저장)
python -m recsys.main --step svd --project seolleyeon --bucket seolleyeon-recs

# KNN
python -m recsys.main --step knn --project seolleyeon --bucket seolleyeon-recs

# CLIP (Firestore에서 직접 읽기)
python -m recsys.main --step clip --project seolleyeon

# RRF merge
python -m recsys.main --step rrf --project seolleyeon

# Verify
python -m recsys.main --step verify --project seolleyeon

# 날짜 지정
python -m recsys.main --step export --date-key 20260309 --project seolleyeon --bucket seolleyeon-recs

# Dry-run (Firestore/GCS 쓰기 없이 건수만 확인)
python -m recsys.main --step export --dry-run --project seolleyeon --bucket seolleyeon-recs

# 유저 수 제한 (테스트용)
python -m recsys.main --step export --limit-users 10 --project seolleyeon --bucket seolleyeon-recs
```

#### SVD: 특정 유저 필터 전(raw) 순위 보기

`recsys`가 받은 `events.csv`로 스크립트를 직접 돌릴 때 `--dump_raw_user`를 쓰면, 동성/AI 더미/정책 필터 **적용 전** `recommend_for_user` 순위가 JSON으로 출력됩니다.

(`python -m recsys.main --step svd`는 이 인자를 넘기지 않음 → CSV 준비 후 아래처럼 직접 실행.)

**프로젝트 루트에서 붙여넣기 (PowerShell, 한 줄)** — `--events_csv`만 실제 CSV 경로로 바꿀 것:

```powershell
cd lib\ai_recommend_model; python seolleyeon_svd_train_export.py --events_csv "C:\경로\events_20260320.csv" --firestore_project seolleyeon --date_key 20260320 --dump_raw_user 4705828086 --dump_raw_topk 50 --dump_raw_out raw_svd.json
```

**CMD에서 붙여넣기 (한 줄):**

```bat
cd /d lib\ai_recommend_model && python seolleyeon_svd_train_export.py --events_csv "C:\경로\events_20260320.csv" --firestore_project seolleyeon --date_key 20260320 --dump_raw_user 4705828086 --dump_raw_topk 50 --dump_raw_out raw_svd.json
```

- `date_key`는 CSV/학습 기준 날짜(`YYYYMMDD`)와 맞출 것.
- `raw_svd.json`은 위 `cd` 후 폴더(`lib\ai_recommend_model`)에 생성됨. 다른 위치에 두려면 `--dump_raw_out "D:\원하는\경로\raw_svd.json"` 처럼 전체 경로 지정.

v3에서 동일 진단이 필요하면 `seolleyeon_svd_train_export_v3.py`의 `--dump_raw_user` 등 인자 지원 여부를 확인할 것.

### 4. 기존 스크립트 직접 실행 (변경 없음, 레거시 1:1)

```bash
cd lib/ai_recommend_model
python seolleyeon_run_all.py --firestore_project seolleyeon --date_key 20260309
```

## Cloud Run Deployment

### 원클릭 배포

```bash
chmod +x infra/deploy.sh
./infra/deploy.sh
```

### 수동 단계별

```bash
# 1. 이미지 빌드 + 푸시
gcloud builds submit --config=cloudbuild.yaml \
  --substitutions=_REGION=asia-northeast3,_REPO=seolleyeon-repo,SHORT_SHA=$(git rev-parse --short HEAD)

# 2. Job 생성 (예: recs-export)
gcloud run jobs create recs-export \
  --image=asia-northeast3-docker.pkg.dev/seolleyeon/seolleyeon-repo/recs-pipeline:latest \
  --region=asia-northeast3 \
  --cpu=1 --memory=2Gi --task-timeout=600 \
  --service-account=seolleyeon-recs-sa@seolleyeon.iam.gserviceaccount.com \
  --args="--step=export,--project=seolleyeon,--bucket=seolleyeon-recs"

# 3. Workflow 배포
gcloud workflows deploy recs-pipeline \
  --source=infra/workflows/recs_pipeline.yaml \
  --location=asia-northeast3
```

### 수동 실행

```bash
# 전체 파이프라인 (Workflow)
gcloud workflows run recs-pipeline \
  --location=asia-northeast3 \
  --data='{"date_key": "20260309"}'

# 개별 Job
gcloud run jobs execute recs-export --region=asia-northeast3 \
  --args="--step=export,--project=seolleyeon,--bucket=seolleyeon-recs,--date-key=20260309"
```

### 로그 확인

```bash
gcloud logging read 'resource.type=cloud_run_job' --limit=50 --project=seolleyeon
```

## Cloud Run Job Specifications

| Job | CPU | Memory | Timeout | 용도 |
|-----|-----|--------|---------|------|
| `recs-export` | 1 | 2Gi | 10min | Firestore → GCS CSV |
| `recs-clip` | 2 | 8Gi | 60min | CLIP 임베딩 + 추천 |
| `recs-svd` | 2 | 4Gi | 30min | SVD/ALS 행렬 분해 |
| `recs-knn` | 2 | 4Gi | 30min | Item-KNN |
| `recs-rrf` | 1 | 2Gi | 10min | RRF 병합 |
| `recs-verify` | 1 | 1Gi | 5min | 결과 검증 |

## IAM / Service Account

**Service Account**: `seolleyeon-recs-sa@seolleyeon.iam.gserviceaccount.com`

| Role | 용도 |
|------|------|
| `roles/datastore.user` | Firestore 읽기/쓰기 |
| `roles/storage.objectAdmin` | GCS 읽기/쓰기 |
| `roles/run.invoker` | Workflow → Cloud Run Job 실행 |
| `roles/logging.logWriter` | Cloud Logging |
| `roles/workflows.invoker` | Scheduler → Workflow 실행 |

## Environment Variables

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GCP_PROJECT` | `seolleyeon` | GCP 프로젝트 ID |
| `GCS_BUCKET` | (none) | GCS 버킷 이름 |
| `FIRESTORE_DATABASE` | (none) | Firestore DB ID (기본 DB면 생략) |
| `AI_MODEL_DIR` | (auto) | ML 스크립트 경로 |
| `CLIP_MODEL_ID` | `openai/clip-vit-large-patch14` | CLIP 모델 |
| `ALLOWED_IMAGE_HOSTS` | `firebasestorage.googleapis.com,...` | SSRF 방지 |

## GPU 분리 판단

**결론: GPU 불필요, 단일 CPU 이미지로 충분**

- 모델: `openai/clip-vit-base-patch32` (~350MB, ViT-B/32) 등 CPU 추론 위주 구성
- 추론 대상: 유저별 프로필 사진 1-3장
- 현재 유저 규모: 수백 명 수준
- CPU inference 시간: 유저당 ~1-2초 → 500명 기준 ~15분
- Cloud Run Job timeout 60분이면 수천 명까지 커버 가능
- GPU Job은 비용이 3-5배 높고 cold start 오래 걸림

## Idempotency

- 같은 `date_key`로 재실행 시 GCS CSV는 덮어쓰기
- Firestore modelRecs는 `merge=True`로 upsert
- 안전하게 재실행 가능

## Smoke Test 절차

```bash
# 1. 이미지 빌드 확인
docker build -f recsys/Dockerfile -t recs-pipeline .

# 2. 로컬 dry-run
python -m recsys.main --step export --dry-run --limit-users 5 \
  --project seolleyeon --bucket seolleyeon-recs

# 3. Cloud Run 단일 job 실행
gcloud run jobs execute recs-export --region=asia-northeast3

# 4. GCS 확인
gsutil ls gs://seolleyeon-recs/recs/$(date +%Y%m%d)/

# 5. Verify 실행
gcloud run jobs execute recs-verify --region=asia-northeast3

# 6. 전체 Workflow 실행
gcloud workflows run recs-pipeline --location=asia-northeast3 --data='{}'
```

## TODO / 가정 사항

- [ ] GCS 버킷 `seolleyeon-recs` 생성 필요 (`deploy.sh`가 자동 생성)
- [ ] Cloud Scheduler는 date_key 없이 trigger → 각 Job이 KST 오늘 날짜 사용
- [ ] 유저 수 1만명 초과 시 CLIP timeout 증가 또는 배치 분할 필요
- [ ] Secret Manager는 현재 불필요 (API key 등 없음, ADC로 인증)
- [ ] dailyRecs 컬렉션 생성은 별도 Cloud Function 또는 앱에서 처리
- [ ] Cloud Run 1:1 파이프라인을 **v3 스크립트**로 통일하려면 `recsys/main.py`의 `_run_script` 대상 파일명과 인자(`--firestore_events`, lookback 등)를 v3에 맞게 조정해야 함
