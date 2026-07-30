#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=staging_common.sh
source "${SCRIPT_DIR}/staging_common.sh"

require_staging_guard

cat <<EOF
{
  "status": "pass",
  "sourceProject": "${SOURCE_PROJECT}",
  "targetProject": "${TARGET_PROJECT}",
  "firebaseAlias": "${FIREBASE_ALIAS}",
  "gcloudAccount": "$(active_gcloud_account)",
  "gcloudProject": "$(active_gcloud_project)",
  "firebaseProject": "$(active_firebase_project)",
  "adcQuotaProject": "$(adc_quota_project)"
}
EOF
