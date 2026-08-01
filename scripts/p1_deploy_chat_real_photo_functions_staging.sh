#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/p1_chat_real_photo_common.sh
source "$SCRIPT_DIR/p1_chat_real_photo_common.sh" "$@"

require_command npm
require_command firebase
require_standard_env_defaults

[ "$P1_APPLY" -eq 1 ] || info "Dry-run only. Re-run with --apply to deploy selected staging functions."

PROJECT="$(effective_gcp_project)"
FIREBASE_PROJECT_EFFECTIVE="${FIREBASE_PROJECT:-$PROJECT}"
prepare_firebase_deploy_project "$PROJECT" "$FIREBASE_PROJECT_EFFECTIVE"

npm --prefix functions run build
npm --prefix functions test

TARGETS="functions:getChatRealProfilePhoto,functions:uploadAvatarSourcePhoto"
if [ -n "${CHAT_REAL_PHOTO_CLEANUP_FUNCTION:-}" ]; then
  TARGETS="$TARGETS,functions:$CHAT_REAL_PHOTO_CLEANUP_FUNCTION"
fi

run_or_print firebase deploy --project "$FIREBASE_PROJECT_EFFECTIVE" --only "$TARGETS"
