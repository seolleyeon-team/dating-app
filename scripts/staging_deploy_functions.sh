#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=staging_common.sh
source "${SCRIPT_DIR}/staging_common.sh"

APPLY=false
FUNCTION_TARGETS="${FUNCTION_TARGETS:-functions:getChatRealProfilePhoto,functions:beginAvatarGenerationFromOnboardingPhotos,functions:getAvatarJobCandidates,functions:approveAvatarCandidate}"

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    --targets=*) FUNCTION_TARGETS="${arg#--targets=}" ;;
    *) fail "Unknown argument: $arg" ;;
  esac
done

require_staging_guard

ENV_FILE="functions/.env.${TARGET_PROJECT}"
EXAMPLE_FILE="functions/.env.${TARGET_PROJECT}.example"

if [[ ! -f "$ENV_FILE" ]]; then
  fail "Missing ${ENV_FILE}. Copy ${EXAMPLE_FILE} to ${ENV_FILE}, review non-secret staging values, and retry."
fi

npm --prefix functions run build
npm --prefix functions test

if [[ "$APPLY" != true ]]; then
  log "DRY RUN: would deploy Functions target '${FUNCTION_TARGETS}' to ${TARGET_PROJECT}"
  log "Command: firebase deploy --only ${FUNCTION_TARGETS} --project ${TARGET_PROJECT} --non-interactive"
  exit 0
fi

firebase deploy --only "${FUNCTION_TARGETS}" --project "${TARGET_PROJECT}" --non-interactive
