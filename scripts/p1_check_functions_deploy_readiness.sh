#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/p1_chat_real_photo_common.sh
source "$SCRIPT_DIR/p1_chat_real_photo_common.sh" "$@"

require_command npm
require_command firebase
require_command rg
require_standard_env_defaults

FIREBASE_PROJECT_EFFECTIVE="$(effective_firebase_project)"
[ -n "$FIREBASE_PROJECT_EFFECTIVE" ] || fail "Firebase project is not configured."

info "Checking Functions readiness for Firebase project=$FIREBASE_PROJECT_EFFECTIVE"
npm --prefix functions run build
npm --prefix functions test

rg -n "export const getChatRealProfilePhoto|createGetChatRealProfilePhotoFunction|export const uploadOnboardingPhoto|export const beginAvatarGenerationFromOnboardingPhotos" functions/src/index.ts functions/src/chatRealPhoto.ts functions/src/onboardingPhotoUpload.ts functions/src/avatarSourceSetAdmission.ts
rg -n -- "private_key|-----BEGIN PRIVATE KEY-----" functions/src && fail "Potential private key literal found in functions/src" || true
rg -n "imageUrl|expiresAt|getSignedUrl|logger.info" functions/src/chatRealPhoto.ts

info "Live deployed status for selected functions:"
TMP_FUNCTIONS_JSON="$(mktemp)"
trap 'rm -f "$TMP_FUNCTIONS_JSON"' EXIT
firebase functions:list --project "$FIREBASE_PROJECT_EFFECTIVE" --json > "$TMP_FUNCTIONS_JSON"
python - "$TMP_FUNCTIONS_JSON" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
selected = {
    "getChatRealProfilePhoto",
    "uploadOnboardingPhoto",
    "beginAvatarGenerationFromOnboardingPhotos",
}
rows = []
for item in data.get("result", []):
    if item.get("id") in selected:
        rows.append({
            "id": item.get("id"),
            "state": item.get("state"),
            "region": item.get("region"),
            "serviceAccount": item.get("serviceAccount"),
            "hash": item.get("hash"),
        })
print(json.dumps(rows, ensure_ascii=False, indent=2))
PY
