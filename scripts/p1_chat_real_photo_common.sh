#!/usr/bin/env bash
set -euo pipefail

P1_APPLY=0
P1_LIVE=0

for arg in "$@"; do
  case "$arg" in
    --apply) P1_APPLY=1 ;;
    --live) P1_LIVE=1 ;;
  esac
done

info() {
  printf '[p1-chat-real-photo] %s\n' "$*"
}

fail() {
  printf '[p1-chat-real-photo][error] %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

read_gcloud_project() {
  gcloud config get-value project 2>/dev/null | tr -d '\r'
}

require_gcloud_project() {
  local current
  current="$(read_gcloud_project)"
  [ -n "$current" ] || fail "gcloud project is not configured. Run: gcloud config set project <staging-project>"
  printf '%s' "$current"
}

project_number() {
  local project="$1"
  gcloud projects describe "$project" --format='value(projectNumber)' 2>/dev/null | tr -d '\r'
}

effective_gcp_project() {
  if [ -n "${GCP_PROJECT:-}" ]; then
    printf '%s' "$GCP_PROJECT"
  else
    require_gcloud_project
  fi
}

effective_firebase_project() {
  if [ -n "${FIREBASE_PROJECT:-}" ]; then
    printf '%s' "$FIREBASE_PROJECT"
  else
    firebase use --json 2>/dev/null | python -c 'import json,sys; print(json.load(sys.stdin).get("result",""))' 2>/dev/null | tr -d '\r'
  fi
}

assert_same_firebase_project() {
  local gcp_project="$1"
  local firebase_project="$2"
  [ -n "$firebase_project" ] || fail "Firebase project is not configured."
  if [ "$firebase_project" != "$gcp_project" ]; then
    fail "Refusing deploy with mismatched projects: GCP_PROJECT=$gcp_project FIREBASE_PROJECT=$firebase_project"
  fi
}

assert_project_match() {
  local expected="$1"
  local actual
  actual="$(require_gcloud_project)"
  [ "$actual" = "$expected" ] || fail "Project mismatch: GCP_PROJECT=$expected but gcloud current project=$actual"
}

runtime_service_account_matches_project() {
  local service_account="$1"
  local project="$2"
  local number="$3"
  case "$service_account" in
    *"@$project.iam.gserviceaccount.com") return 0 ;;
    "$project@appspot.gserviceaccount.com") return 0 ;;
    "$number-compute@developer.gserviceaccount.com") return 0 ;;
    *) return 1 ;;
  esac
}

assert_runtime_service_account_project() {
  local service_account="$1"
  local project="$2"
  local number
  number="$(project_number "$project")"
  [ -n "$number" ] || fail "Could not resolve project number for $project"
  runtime_service_account_matches_project "$service_account" "$project" "$number" ||
    fail "FUNCTIONS_RUNTIME_SERVICE_ACCOUNT does not appear to belong to project $project: $service_account"
}

project_looks_production() {
  local project="$1"
  case "$project" in
    *stage*|*staging*|*dev*|*test*|*sandbox*) return 1 ;;
    *) return 0 ;;
  esac
}

prepare_firebase_deploy_project() {
  local gcp_project="$1"
  local firebase_project="$2"
  assert_same_firebase_project "$gcp_project" "$firebase_project"
  prepare_mutation_project "$firebase_project"
}

guard_mutation_project() {
  local project="$1"
  assert_project_match "$project"
  if project_looks_production "$project" && [ "${ALLOW_PRODUCTION:-false}" != "true" ]; then
    fail "Refusing mutation on production-like project '$project'. Use a staging project or set ALLOW_PRODUCTION=true only after explicit approval."
  fi
}

prepare_mutation_project() {
  local project="$1"
  assert_project_match "$project"
  if project_looks_production "$project" && [ "${ALLOW_PRODUCTION:-false}" != "true" ]; then
    if [ "$P1_APPLY" -eq 1 ]; then
      fail "Refusing mutation on production-like project '$project'. Use a staging project or set ALLOW_PRODUCTION=true only after explicit approval."
    fi
    info "Dry-run warning: project '$project' looks production-like; apply mode would be refused without explicit approval."
  fi
}

run_or_print() {
  if [ "$P1_APPLY" -eq 1 ]; then
    "$@"
  else
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
  fi
}

require_standard_env_defaults() {
  : "${GCP_LOCATION:=asia-northeast3}"
  : "${FUNCTIONS_REGION:=asia-northeast3}"
  : "${CHAT_PROFILE_PHOTO_BUCKET:=seolleyeon-chat-profile-photos}"
  : "${SOURCE_PHOTO_BUCKET:=seolleyeon-private-source-photos}"
  : "${APPROVED_AVATAR_BUCKET:=seolleyeon-approved-avatars}"
  : "${AVATAR_TEMP_BUCKET:=seolleyeon-avatar-temp}"
  : "${CHAT_REAL_PHOTO_CALLABLE:=getChatRealProfilePhoto}"
  : "${CHAT_REAL_PHOTO_SIGNED_URL_TTL_SECONDS:=300}"
  : "${USE_CHAT_PROFILE_SIGNED_URL:=true}"
}

require_runtime_service_account() {
  [ -n "${FUNCTIONS_RUNTIME_SERVICE_ACCOUNT:-}" ] || fail "FUNCTIONS_RUNTIME_SERVICE_ACCOUNT is required."
}

bucket_exists() {
  local bucket="$1"
  gcloud storage buckets describe "gs://$bucket" >/dev/null 2>&1
}

verify_bucket_ownership() {
  local bucket="$1"
  local project="$2"
  local expected_number
  local tmp
  expected_number="$(project_number "$project")"
  [ -n "$expected_number" ] || fail "Could not resolve project number for $project"
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN
  gcloud storage buckets describe "gs://$bucket" --raw --format=json > "$tmp"
  python - "$tmp" "$expected_number" "$bucket" "$project" <<'PY'
import json
import sys

path, expected_number, bucket, project = sys.argv[1:5]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
actual = str(data.get("projectNumber") or "")
if actual != str(expected_number):
    raise SystemExit(
        f"Bucket gs://{bucket} belongs to projectNumber={actual or '<unknown>'}, "
        f"expected {expected_number} for project {project}"
    )
print(f"[p1-chat-real-photo] Bucket ownership verified: gs://{bucket} projectNumber={actual}")
PY
}

check_no_public_iam_members() {
  local bucket="$1"
  local policy
  policy="$(gcloud storage buckets get-iam-policy "gs://$bucket" --format=json)"
  if printf '%s' "$policy" | grep -Eq '"allUsers"|"allAuthenticatedUsers"'; then
    fail "Public IAM member found on gs://$bucket"
  fi
  info "No allUsers/allAuthenticatedUsers IAM binding found on gs://$bucket"
}

check_no_direct_project_overgrant_for_service_account() {
  local project="$1"
  local service_account="$2"
  local tmp
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN
  gcloud projects get-iam-policy "$project" --format=json > "$tmp"
  python - "$tmp" "$service_account" <<'PY'
import json
import sys

path, service_account = sys.argv[1:3]
member = f"serviceAccount:{service_account}"
forbidden_roles = {
    "roles/storage.admin",
    "roles/owner",
    "roles/editor",
}
with open(path, "r", encoding="utf-8") as f:
    policy = json.load(f)
hits = []
for binding in policy.get("bindings") or []:
    role = binding.get("role")
    if role in forbidden_roles and member in set(binding.get("members") or []):
        hits.append(role)
if hits:
    raise SystemExit(f"Runtime service account has direct project-level overgrant roles: {sorted(hits)}")
print("[p1-chat-real-photo] No direct project-level owner/editor/storage.admin grant found for runtime service account.")
PY
}
