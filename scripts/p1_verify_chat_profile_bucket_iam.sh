#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/p1_chat_real_photo_common.sh
source "$SCRIPT_DIR/p1_chat_real_photo_common.sh" "$@"

require_command gcloud
require_standard_env_defaults
require_runtime_service_account

PROJECT="$(effective_gcp_project)"
assert_project_match "$PROJECT"
assert_runtime_service_account_project "$FUNCTIONS_RUNTIME_SERVICE_ACCOUNT" "$PROJECT"

TMP_BUCKET_JSON="$(mktemp)"
TMP_POLICY_JSON="$(mktemp)"
trap 'rm -f "$TMP_BUCKET_JSON" "$TMP_POLICY_JSON"' EXIT

verify_bucket_ownership "$CHAT_PROFILE_PHOTO_BUCKET" "$PROJECT"
gcloud storage buckets describe "gs://$CHAT_PROFILE_PHOTO_BUCKET" --format=json >"$TMP_BUCKET_JSON"
python - "$CHAT_PROFILE_PHOTO_BUCKET" "$TMP_BUCKET_JSON" <<'PY'
import json, sys
with open(sys.argv[2], "r", encoding="utf-8") as f:
    data = json.load(f)
summary = {
    "bucket": sys.argv[1],
    "location": data.get("location"),
    "uniform_bucket_level_access": data.get("uniform_bucket_level_access"),
    "public_access_prevention": data.get("public_access_prevention"),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
if data.get("uniform_bucket_level_access") is not True:
    raise SystemExit("UBLA is not enabled")
if data.get("public_access_prevention") != "enforced":
    raise SystemExit("public access prevention is not enforced")
PY

check_no_public_iam_members "$CHAT_PROFILE_PHOTO_BUCKET"
check_no_direct_project_overgrant_for_service_account "$PROJECT" "$FUNCTIONS_RUNTIME_SERVICE_ACCOUNT"

gcloud storage buckets get-iam-policy "gs://$CHAT_PROFILE_PHOTO_BUCKET" --format=json >"$TMP_POLICY_JSON"
python - "$TMP_POLICY_JSON" "$FUNCTIONS_RUNTIME_SERVICE_ACCOUNT" <<'PY'
import json
import sys

path, service_account = sys.argv[1:3]
member = f"serviceAccount:{service_account}"
allowed_role = "roles/storage.objectAdmin"
forbidden_roles = {
    "roles/storage.admin",
    "roles/owner",
    "roles/editor",
}
with open(path, "r", encoding="utf-8") as f:
    policy = json.load(f)
bindings = policy.get("bindings") or []
roles = {
    binding.get("role")
    for binding in bindings
    if member in set(binding.get("members") or [])
}
if allowed_role not in roles:
    raise SystemExit(f"Missing {allowed_role} binding for {member}")
bad = sorted(role for role in roles if role in forbidden_roles)
if bad:
    raise SystemExit(f"Overbroad bucket IAM roles for {member}: {bad}")
print(f"[p1-chat-real-photo] Runtime service account has expected bucket role: {allowed_role}")
PY
