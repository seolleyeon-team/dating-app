#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=staging_common.sh
source "${SCRIPT_DIR}/staging_common.sh"

require_staging_guard

STATUS=0

verify_bucket() {
  local bucket="$1"
  local desc_file
  local policy_file
  log "Verifying bucket: gs://${bucket}"
  desc_file="$(mktemp)"
  policy_file="$(mktemp)"

  if ! gcloud storage buckets describe "gs://${bucket}" --project="${TARGET_PROJECT}" --format=json >"${desc_file}" 2>"${desc_file}.err"; then
    cat "${desc_file}.err" >&2
    rm -f "${desc_file}" "${desc_file}.err" "${policy_file}" "${policy_file}.err"
    STATUS=1
    return
  fi

  if ! python - "$bucket" "${desc_file}" <<'PY'
import json, sys
bucket = sys.argv[1]
path = sys.argv[2]
with open(path, encoding="utf-8") as fp:
    data = json.load(fp)
ubla = data.get("uniform_bucket_level_access")
if ubla is None:
    ubla = data.get("iamConfiguration", {}).get("uniformBucketLevelAccess", {}).get("enabled")
pap = data.get("public_access_prevention")
if pap is None:
    pap = data.get("iamConfiguration", {}).get("publicAccessPrevention")
ok = True
if ubla is not True:
    print(f"{bucket}: UBLA not enabled", file=sys.stderr)
    ok = False
if pap != "enforced":
    print(f"{bucket}: public access prevention not enforced ({pap})", file=sys.stderr)
    ok = False
raise SystemExit(0 if ok else 1)
PY
  then
    STATUS=1
  fi

  if ! gcloud storage buckets get-iam-policy "gs://${bucket}" --project="${TARGET_PROJECT}" --format=json >"${policy_file}" 2>"${policy_file}.err"; then
    cat "${policy_file}.err" >&2
    rm -f "${desc_file}" "${desc_file}.err" "${policy_file}" "${policy_file}.err"
    STATUS=1
    return
  fi

  if ! python - "$bucket" "${FUNCTIONS_RUNTIME_SERVICE_ACCOUNT}" "${policy_file}" <<'PY'
import json, sys
bucket = sys.argv[1]
runtime_sa = sys.argv[2]
path = sys.argv[3]
with open(path, encoding="utf-8") as fp:
    policy = json.load(fp)
members = []
for binding in policy.get("bindings", []):
    members.extend(binding.get("members", []))
public = [m for m in members if m in {"allUsers", "allAuthenticatedUsers"}]
if public:
    print(f"{bucket}: public IAM members found: {public}", file=sys.stderr)
    raise SystemExit(1)
if runtime_sa:
    wanted = f"serviceAccount:{runtime_sa}"
    if wanted not in members:
        print(f"{bucket}: runtime service account binding missing: {wanted}", file=sys.stderr)
        raise SystemExit(1)
print(f"{bucket}: iam_ok")
PY
  then
    STATUS=1
  fi

  rm -f "${desc_file}" "${desc_file}.err" "${policy_file}" "${policy_file}.err"
}

while IFS= read -r bucket; do
  verify_bucket "$bucket"
done < <(bucket_names)

exit "$STATUS"
