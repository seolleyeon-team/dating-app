#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=staging_common.sh
source "${SCRIPT_DIR}/staging_common.sh"

OUT_DIR="${OUT_DIR:-out/cloudrun-source}"
mkdir -p "$OUT_DIR"

require_staging_guard

log "Source project is read-only: ${SOURCE_PROJECT}"
log "Writing inventory to ${OUT_DIR}"

gcloud run services list \
  --project="${SOURCE_PROJECT}" \
  --region="${FUNCTIONS_REGION}" \
  --format=json > "${OUT_DIR}/source-services.json"

gcloud run jobs list \
  --project="${SOURCE_PROJECT}" \
  --region="${FUNCTIONS_REGION}" \
  --format=json > "${OUT_DIR}/source-jobs.json"

if gcloud run services list --project="${TARGET_PROJECT}" --region="${FUNCTIONS_REGION}" --format=json > "${OUT_DIR}/target-services.json" 2>"${OUT_DIR}/target-services.err"; then
  log "Target services inventory written."
else
  log "Target services inventory failed; see ${OUT_DIR}/target-services.err"
fi

if gcloud run jobs list --project="${TARGET_PROJECT}" --region="${FUNCTIONS_REGION}" --format=json > "${OUT_DIR}/target-jobs.json" 2>"${OUT_DIR}/target-jobs.err"; then
  log "Target jobs inventory written."
else
  log "Target jobs inventory failed; see ${OUT_DIR}/target-jobs.err"
fi

python - <<'PY'
import json
from pathlib import Path

out = Path("out/cloudrun-source")
summary = {"services": [], "jobs": [], "targetErrors": {}}
for name, key in [("source-services.json", "services"), ("source-jobs.json", "jobs")]:
    path = out / name
    if not path.exists():
        continue
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        rows = []
    for row in rows:
        meta = row.get("metadata", {})
        spec = row.get("spec", {})
        template = spec.get("template", {}).get("spec", {}) if isinstance(spec.get("template"), dict) else {}
        containers = template.get("containers", []) if isinstance(template, dict) else []
        image = containers[0].get("image", "") if containers else ""
        summary[key].append({
            "name": meta.get("name", ""),
            "image": image,
            "serviceAccount": template.get("serviceAccountName", ""),
        })

for err_name in ["target-services.err", "target-jobs.err"]:
    path = out / err_name
    if path.exists() and path.read_text(encoding="utf-8").strip():
        summary["targetErrors"][err_name] = path.read_text(encoding="utf-8").strip()[:1000]

(out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(summary, indent=2, ensure_ascii=False))
PY
