#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=staging_common.sh
source "${SCRIPT_DIR}/staging_common.sh"

APPLY=false
TARGETS="firestore:rules,firestore:indexes,storage"
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    --firestore-only) TARGETS="firestore:rules,firestore:indexes" ;;
    --storage-only) TARGETS="storage" ;;
    *) fail "Unknown argument: $arg" ;;
  esac
done

require_staging_guard

if [[ "$APPLY" != true ]]; then
  log "DRY RUN: would deploy Firebase rules target '${TARGETS}' to ${TARGET_PROJECT}"
  log "Command: firebase deploy --only ${TARGETS} --project ${TARGET_PROJECT} --non-interactive"
  exit 0
fi

firebase deploy --only "${TARGETS}" --project "${TARGET_PROJECT}" --non-interactive
