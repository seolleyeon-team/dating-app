#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/p1_chat_real_photo_common.sh
source "$SCRIPT_DIR/p1_chat_real_photo_common.sh" "$@"

require_command firebase
require_standard_env_defaults

FIREBASE_PROJECT_EFFECTIVE="$(effective_firebase_project)"
[ -n "$FIREBASE_PROJECT_EFFECTIVE" ] || fail "Firebase project is not configured."

info "Checking deployed callable $CHAT_REAL_PHOTO_CALLABLE in project=$FIREBASE_PROJECT_EFFECTIVE"
TMP_FUNCTIONS_JSON="$(mktemp)"
trap 'rm -f "$TMP_FUNCTIONS_JSON"' EXIT
firebase functions:list --project "$FIREBASE_PROJECT_EFFECTIVE" --json > "$TMP_FUNCTIONS_JSON"
python - "$CHAT_REAL_PHOTO_CALLABLE" "$TMP_FUNCTIONS_JSON" <<'PY'
import json, sys
name = sys.argv[1]
with open(sys.argv[2], "r", encoding="utf-8") as f:
    data = json.load(f)
matches = [item for item in data.get("result", []) if item.get("id") == name]
print(json.dumps(matches, ensure_ascii=False, indent=2))
if not matches:
    raise SystemExit(f"{name} is not deployed")
if any(item.get("state") != "ACTIVE" for item in matches):
    raise SystemExit(f"{name} is not ACTIVE")
PY

info "For live auth matrix run: python scripts/p1_chat_real_photo_staging_matrix.py --live"
