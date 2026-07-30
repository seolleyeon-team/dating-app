#!/usr/bin/env bash
# ===========================================================
# Seolleyeon Recommendation Pipeline — Full Deployment Script
#
# Prerequisites:
#   - gcloud CLI authenticated and configured
#   - APIs enabled: run.googleapis.com, workflows.googleapis.com,
#     cloudscheduler.googleapis.com, artifactregistry.googleapis.com,
#     cloudbuild.googleapis.com, firestore.googleapis.com
#
# Usage:
#   chmod +x infra/deploy.sh
#   ./infra/deploy.sh
#
# Override defaults with env vars:
#   GCP_PROJECT=my-project GCP_REGION=us-central1 ./infra/deploy.sh
# ===========================================================
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-seolleyeon}"
REGION="${GCP_REGION:-asia-northeast3}"
REPO="seolleyeon-repo"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/recs-pipeline:latest"
SA_NAME="seolleyeon-recs-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET="${GCS_BUCKET:-${PROJECT_ID}-recs}"
WORKFLOW_NAME="recs-pipeline"
SCHEDULER_NAME="recs-daily-trigger"

echo "=============================================="
echo " Seolleyeon Recommendation Pipeline Deployment"
echo "=============================================="
echo " Project : ${PROJECT_ID}"
echo " Region  : ${REGION}"
echo " Image   : ${IMAGE}"
echo " Bucket  : ${BUCKET}"
echo " SA      : ${SA_EMAIL}"
echo "=============================================="
echo ""

# -------------------------------------------------------
# Helper: create-or-update a Cloud Run Job
# -------------------------------------------------------
create_or_update_job() {
  local JOB_NAME="$1"
  shift
  if gcloud run jobs describe "${JOB_NAME}" \
       --region="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "  ↻ Updating job: ${JOB_NAME}"
    gcloud run jobs update "${JOB_NAME}" \
      --region="${REGION}" --project="${PROJECT_ID}" "$@"
  else
    echo "  ✚ Creating job: ${JOB_NAME}"
    gcloud run jobs create "${JOB_NAME}" \
      --region="${REGION}" --project="${PROJECT_ID}" "$@"
  fi
}

# -------------------------------------------------------
# 1. Enable required APIs
# -------------------------------------------------------
echo "--- 1. Enabling APIs ---"
gcloud services enable \
  run.googleapis.com \
  workflows.googleapis.com \
  cloudscheduler.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  --project="${PROJECT_ID}" --quiet

# -------------------------------------------------------
# 2. Artifact Registry repository
# -------------------------------------------------------
echo "--- 2. Artifact Registry ---"
if ! gcloud artifacts repositories describe "${REPO}" \
     --project="${PROJECT_ID}" --location="${REGION}" &>/dev/null; then
  gcloud artifacts repositories create "${REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --description="Seolleyeon ML Pipeline"
fi

# -------------------------------------------------------
# 3. GCS bucket for intermediate data
# -------------------------------------------------------
echo "--- 3. GCS Bucket ---"
if ! gsutil ls -b "gs://${BUCKET}" &>/dev/null; then
  gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${BUCKET}"
fi

# -------------------------------------------------------
# 4. Service Account
# -------------------------------------------------------
echo "--- 4. Service Account ---"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" \
     --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="Seolleyeon Recommendation Pipeline" \
    --project="${PROJECT_ID}"
fi

# -------------------------------------------------------
# 5. IAM roles (minimum privilege)
# -------------------------------------------------------
echo "--- 5. IAM Roles ---"
ROLES=(
  "roles/datastore.user"          # Firestore read/write
  "roles/storage.objectAdmin"     # GCS read/write
  "roles/run.developer"           # Workflows → Cloud Run Job (run.jobs.runWithOverrides)
  "roles/logging.logWriter"       # Structured logging
  "roles/workflows.invoker"       # Scheduler → Workflow
)
for ROLE in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" \
    --quiet --no-user-output-enabled
done
echo "  Granted: ${ROLES[*]}"

# -------------------------------------------------------
# 6. Build & push Docker image (Cloud Build)
# -------------------------------------------------------
echo "--- 6. Build & Push Image ---"
SHORT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "manual")
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --config=cloudbuild.yaml \
  --substitutions="_REGION=${REGION},_REPO=${REPO},SHORT_SHA=${SHORT_SHA}" \
  .

# -------------------------------------------------------
# 7. Cloud Run Jobs
# -------------------------------------------------------
echo "--- 7. Cloud Run Jobs ---"

COMMON_ARGS=(
  --image="${IMAGE}"
  --service-account="${SA_EMAIL}"
  --max-retries=1
  --set-env-vars="GCP_PROJECT=${PROJECT_ID},GCS_BUCKET=${BUCKET}"
)

create_or_update_job recs-export "${COMMON_ARGS[@]}" \
  --cpu=1 --memory=2Gi --task-timeout=600 \
  --args="--step=export,--project=${PROJECT_ID},--bucket=${BUCKET}"

create_or_update_job recs-clip "${COMMON_ARGS[@]}" \
  --cpu=2 --memory=8Gi --task-timeout=3600 \
  --args="--step=clip,--project=${PROJECT_ID}"

create_or_update_job recs-svd "${COMMON_ARGS[@]}" \
  --cpu=2 --memory=4Gi --task-timeout=1800 \
  --args="--step=svd,--project=${PROJECT_ID},--bucket=${BUCKET}"

create_or_update_job recs-knn "${COMMON_ARGS[@]}" \
  --cpu=2 --memory=4Gi --task-timeout=1800 \
  --args="--step=knn,--project=${PROJECT_ID},--bucket=${BUCKET}"

create_or_update_job recs-rrf "${COMMON_ARGS[@]}" \
  --cpu=1 --memory=2Gi --task-timeout=600 \
  --args="--step=rrf,--project=${PROJECT_ID}"

create_or_update_job recs-verify "${COMMON_ARGS[@]}" \
  --cpu=1 --memory=1Gi --task-timeout=300 \
  --args="--step=verify,--project=${PROJECT_ID}"

# -------------------------------------------------------
# 8. Workflow deployment
# -------------------------------------------------------
echo "--- 8. Workflow ---"
gcloud workflows deploy "${WORKFLOW_NAME}" \
  --source=infra/workflows/recs_pipeline.yaml \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --service-account="${SA_EMAIL}"

# -------------------------------------------------------
# 9. Cloud Scheduler (daily 04:00 KST)
# -------------------------------------------------------
echo "--- 9. Cloud Scheduler ---"
WORKFLOW_URI="https://workflowexecutions.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/workflows/${WORKFLOW_NAME}/executions"

if gcloud scheduler jobs describe "${SCHEDULER_NAME}" \
     --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --schedule="0 4 * * *" \
    --time-zone="Asia/Seoul" \
    --uri="${WORKFLOW_URI}" \
    --http-method=POST \
    --update-headers="Content-Type=application/json" \
    --message-body='{"argument":"{}"}' \
    --oauth-service-account-email="${SA_EMAIL}"
else
  gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --schedule="0 4 * * *" \
    --time-zone="Asia/Seoul" \
    --uri="${WORKFLOW_URI}" \
    --http-method=POST \
    --headers="Content-Type=application/json" \
    --message-body='{"argument":"{}"}' \
    --oauth-service-account-email="${SA_EMAIL}"
fi

# -------------------------------------------------------
# Done
# -------------------------------------------------------
echo ""
echo "=============================================="
echo " Deployment Complete!"
echo "=============================================="
echo ""
echo "Manual workflow run:"
echo "  gcloud workflows run ${WORKFLOW_NAME} \\"
echo "    --location=${REGION} \\"
echo "    --data='{\"date_key\": \"$(date +%Y%m%d)\"}'"
echo ""
echo "Manual single-job run:"
echo "  gcloud run jobs execute recs-export --region=${REGION} \\"
echo "    --args='--step=export,--project=${PROJECT_ID},--bucket=${BUCKET},--date-key=$(date +%Y%m%d)'"
echo ""
echo "Logs:"
echo "  gcloud logging read 'resource.type=cloud_run_job' --limit=50 --project=${PROJECT_ID}"
