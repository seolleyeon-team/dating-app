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

create_or_report_bucket() {
  local bucket="$1"
  if gcloud storage buckets describe "gs://${bucket}" --project="${TARGET_PROJECT}" >/dev/null 2>&1; then
    log "Bucket exists: gs://${bucket}"
  elif [[ "$APPLY" == true ]]; then
    log "Creating bucket: gs://${bucket}"
    gcloud storage buckets create "gs://${bucket}" \
      --location="${GCP_LOCATION}" \
      --project="${TARGET_PROJECT}" \
      --uniform-bucket-level-access \
      --public-access-prevention
  else
    log "DRY RUN: would create gs://${bucket} in ${GCP_LOCATION}"
  fi

  if [[ "$APPLY" == true ]]; then
    gcloud storage buckets update "gs://${bucket}" \
      --uniform-bucket-level-access \
      --public-access-prevention
  else
    log "DRY RUN: would enforce UBLA and public access prevention for gs://${bucket}"
  fi
}

while IFS= read -r bucket; do
  create_or_report_bucket "$bucket"
done < <(bucket_names)
