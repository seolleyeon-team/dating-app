#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/p1_chat_real_photo_common.sh
source "$SCRIPT_DIR/p1_chat_real_photo_common.sh" "$@"

require_command gcloud
require_standard_env_defaults

PROJECT="$(effective_gcp_project)"
assert_project_match "$PROJECT"

info "Checking chat profile bucket in project=$PROJECT bucket=$CHAT_PROFILE_PHOTO_BUCKET"
gcloud auth list --filter=status:ACTIVE --format='value(account)' | sed 's/^/[active-account] /'

TMP_BUCKET_JSON="$(mktemp)"
trap 'rm -f "$TMP_BUCKET_JSON"' EXIT

if gcloud storage buckets describe "gs://$CHAT_PROFILE_PHOTO_BUCKET" --format=json >"$TMP_BUCKET_JSON" 2>/dev/null; then
  verify_bucket_ownership "$CHAT_PROFILE_PHOTO_BUCKET" "$PROJECT"
  python - "$CHAT_PROFILE_PHOTO_BUCKET" "$TMP_BUCKET_JSON" <<'PY'
import json, sys
bucket = sys.argv[1]
path = sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
print(json.dumps({
    "bucket": bucket,
    "exists": True,
    "location": data.get("location"),
    "uniform_bucket_level_access": data.get("uniform_bucket_level_access"),
    "public_access_prevention": data.get("public_access_prevention"),
}, ensure_ascii=False, indent=2))
PY
  check_no_public_iam_members "$CHAT_PROFILE_PHOTO_BUCKET"
else
  info "Bucket does not exist: gs://$CHAT_PROFILE_PHOTO_BUCKET"
  info "Create it with: bash scripts/p1_apply_chat_profile_bucket_staging.sh --apply"
  exit 1
fi
