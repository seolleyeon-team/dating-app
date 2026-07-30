#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=staging_common.sh
source "${SCRIPT_DIR}/staging_common.sh"

APPLY=false
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    *) fail "Unknown argument: $arg" ;;
  esac
done

require_staging_guard

export GCP_PROJECT="${TARGET_PROJECT}"
export GCP_REGION="${FUNCTIONS_REGION}"
export GCS_BUCKET="${GCS_BUCKET:-${TARGET_PROJECT}-recs}"

if [[ "$APPLY" != true ]]; then
  log "DRY RUN: would deploy recommendation Cloud Run jobs/workflow through infra/deploy.sh"
  log "GCP_PROJECT=${GCP_PROJECT} GCP_REGION=${GCP_REGION} GCS_BUCKET=${GCS_BUCKET} bash infra/deploy.sh"
  log "Required before apply: billing linked; run/cloudbuild/artifactregistry/workflows/scheduler APIs enabled."
  exit 0
fi

bash infra/deploy.sh
