# Seolleyeon Recommendation Pipeline — Cloud Run Jobs

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
├── lib/ai_recommend_model/      # 기존 ML 스크립트 (수정 없음)
│   ├── seolleyeon_svd_train_export.py
│   ├── seolleyeon_knn_train_export.py
│   ├── seolleyeon_clip_train_export.py
│   ├── seolleyeon_clip_embedder.py
│   ├── seolleyeon_rrf_export.py
│   └── seolleyeon_run_all.py
├── infra/
│   ├── workflows/recs_pipeline.yaml   # Workflows 정의
│   └── deploy.sh                      # 원클릭 배포 스크립트
├── cloudbuild.yaml              # Cloud Build 설정
└── .dockerignore                # Docker 빌드 컨텍스트 필터
```

## Data Flow

```
[Firestore]                    [GCS]                      [Firestore]
recEvents/{uid}/events  →  gs://bucket/recs/{date}/  →  modelRecs/{uid}/daily/{date}/sources/
                            events.csv                    ├── svd
                                                          ├── knn
users/{uid}  ─────────────────────────────────────────→   ├── clip
                                                          └── rrf
```

## Local Development

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

### 4. 기존 스크립트 직접 실행 (변경 없음)

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
| `CLIP_MODEL_ID` | `openai/clip-vit-base-patch32` | CLIP 모델 |
| `ALLOWED_IMAGE_HOSTS` | `firebasestorage.googleapis.com,...` | SSRF 방지 |

## GPU 분리 판단

**결론: GPU 불필요, 단일 CPU 이미지로 충분**

- 모델: `openai/clip-vit-base-patch32` (~350MB, ViT-B/32)
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
