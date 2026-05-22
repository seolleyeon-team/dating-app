#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=staging_common.sh
source "${SCRIPT_DIR}/staging_common.sh"

require_staging_guard

EXPECTED_JOBS=(recs-export recs-clip recs-svd recs-knn recs-rrf recs-verify)
STATUS=0

if ! gcloud run jobs list --project="${TARGET_PROJECT}" --region="${FUNCTIONS_REGION}" --format='value(metadata.name)' >/tmp/seolleyeon-final-run-jobs.txt 2>/tmp/seolleyeon-final-run-jobs.err; then
  cat /tmp/seolleyeon-final-run-jobs.err >&2
  exit 1
fi

for job in "${EXPECTED_JOBS[@]}"; do
  if grep -qx "$job" /tmp/seolleyeon-final-run-jobs.txt; then
    log "Cloud Run job exists: $job"
  else
    log "Missing Cloud Run job: $job"
    STATUS=1
  fi
done

exit "$STATUS"
