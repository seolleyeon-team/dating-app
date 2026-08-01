#!/usr/bin/env bash
set -euo pipefail

TARGET_PROJECT="${TARGET_PROJECT:-seolleyeon-final}"
SOURCE_PROJECT="${SOURCE_PROJECT:-seolleyeon}"
FIREBASE_ALIAS="${FIREBASE_ALIAS:-staging}"
GCP_LOCATION="${GCP_LOCATION:-asia-northeast3}"
FUNCTIONS_REGION="${FUNCTIONS_REGION:-asia-northeast3}"
STAGING_BUCKET_PREFIX="${STAGING_BUCKET_PREFIX:-seolleyeon-final}"

SOURCE_PHOTO_BUCKET="${SOURCE_PHOTO_BUCKET:-${STAGING_BUCKET_PREFIX}-private-source-photos}"
CHAT_PROFILE_PHOTO_BUCKET="${CHAT_PROFILE_PHOTO_BUCKET:-${STAGING_BUCKET_PREFIX}-chat-profile-photos}"
APPROVED_AVATAR_BUCKET="${APPROVED_AVATAR_BUCKET:-${STAGING_BUCKET_PREFIX}-approved-avatars}"
AVATAR_TEMP_BUCKET="${AVATAR_TEMP_BUCKET:-${STAGING_BUCKET_PREFIX}-avatar-temp}"
EXPORT_BUCKET="${EXPORT_BUCKET:-${STAGING_BUCKET_PREFIX}-firestore-migration}"

EXPECTED_GCLOUD_ACCOUNT="${EXPECTED_GCLOUD_ACCOUNT:-seolleyeon.official@gmail.com}"
FUNCTIONS_RUNTIME_SERVICE_ACCOUNT="${FUNCTIONS_RUNTIME_SERVICE_ACCOUNT:-}"

log() {
  printf '[staging] %s\n' "$*" >&2
}

fail() {
  printf '[staging] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

active_gcloud_project() {
  gcloud config get-value project 2>/dev/null || true
}

active_gcloud_account() {
  gcloud config get-value account 2>/dev/null || true
}

active_firebase_project() {
  firebase use --json 2>/dev/null | node -e 'let s="";process.stdin.on("data",d=>s+=d);process.stdin.on("end",()=>{try{const j=JSON.parse(s); console.log(j.result||"");}catch(e){process.exit(1)}})'
}

adc_quota_project() {
  python - <<'PY'
import json, os, pathlib
path = pathlib.Path(os.environ.get("APPDATA", "")) / "gcloud" / "application_default_credentials.json"
if not path.exists():
    print("")
    raise SystemExit(0)
try:
    print(json.loads(path.read_text(encoding="utf-8")).get("quota_project_id", ""))
except Exception:
    print("")
PY
}

require_staging_guard() {
  require_cmd gcloud
  require_cmd firebase
  require_cmd node
  require_cmd python

  local gcloud_project
  local gcloud_account
  local firebase_project
  local quota_project
  gcloud_project="$(active_gcloud_project)"
  gcloud_account="$(active_gcloud_account)"
  firebase_project="$(active_firebase_project)"
  quota_project="$(adc_quota_project)"

  [[ "$SOURCE_PROJECT" != "$TARGET_PROJECT" ]] || fail "SOURCE_PROJECT and TARGET_PROJECT must differ."
  [[ "$TARGET_PROJECT" == "seolleyeon-final" ]] || fail "Refusing staging mutation for unexpected target: $TARGET_PROJECT"
  [[ "$gcloud_project" == "$TARGET_PROJECT" ]] || fail "gcloud project mismatch: expected $TARGET_PROJECT, got ${gcloud_project:-<empty>}"
  [[ "$firebase_project" == "$TARGET_PROJECT" ]] || fail "Firebase active project mismatch: expected $TARGET_PROJECT, got ${firebase_project:-<empty>}"
  [[ "$gcloud_account" == "$EXPECTED_GCLOUD_ACCOUNT" ]] || fail "gcloud account mismatch: expected $EXPECTED_GCLOUD_ACCOUNT, got ${gcloud_account:-<empty>}"
  [[ "$quota_project" == "$TARGET_PROJECT" ]] || fail "ADC quota project mismatch: expected $TARGET_PROJECT, got ${quota_project:-<empty>}"
}

bucket_names() {
  printf '%s\n' \
    "$SOURCE_PHOTO_BUCKET" \
    "$CHAT_PROFILE_PHOTO_BUCKET" \
    "$APPROVED_AVATAR_BUCKET" \
    "$AVATAR_TEMP_BUCKET" \
    "$EXPORT_BUCKET"
}
