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

SERVICES=(
  firebase.googleapis.com
  firestore.googleapis.com
  storage.googleapis.com
  firebasestorage.googleapis.com
  cloudfunctions.googleapis.com
  run.googleapis.com
  cloudbuild.googleapis.com
  artifactregistry.googleapis.com
  iamcredentials.googleapis.com
  cloudtasks.googleapis.com
  pubsub.googleapis.com
  cloudscheduler.googleapis.com
  secretmanager.googleapis.com
  workflows.googleapis.com
  eventarc.googleapis.com
)

if [[ "$APPLY" != true ]]; then
  log "DRY RUN: would enable services in ${TARGET_PROJECT}:"
  printf '  %s\n' "${SERVICES[@]}"
  exit 0
fi

gcloud services enable "${SERVICES[@]}" --project="${TARGET_PROJECT}" --quiet
