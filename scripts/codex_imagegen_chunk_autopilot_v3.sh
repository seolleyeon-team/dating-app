#!/usr/bin/env bash
set -uo pipefail

printf '%s\n' "scripts/codex_imagegen_chunk_autopilot_v3.sh is deprecated for production AI profile generation."
printf '%s\n' "Use scripts/run_ai_image_pipeline_v3.py bounded-chunk-status, bounded-chunk-reconcile, and bounded-chunk-run instead."
exit 2

ROOT="${AI_IMAGE_ROOT:-.}"
ROOT="$(cd "$ROOT" && pwd -P)"
PYTHON_BIN="${PYTHON_BIN:-python}"
MAX_CHUNKS="${MAX_CHUNKS:-30}"
MAX_PENDING_RECOVERY_FAILURES="${MAX_PENDING_RECOVERY_FAILURES:-3}"
PENDING_RECOVERY_RETRY_SLEEP="${PENDING_RECOVERY_RETRY_SLEEP:-3}"
GENERATED_DIR="${CODEX_GENERATED_IMAGES_DIR:-$HOME/.codex/generated_images}"
ACTIVE_VISUAL_QA="${ACTIVE_VISUAL_QA:-1}"

PROMPT_FILE="$ROOT/ai_image/prompts/RALPH_DISTRIBUTION_AWARE_CHUNK_PROMPT.md"
MANUAL_REVIEW_FLAG="$ROOT/ai_image/manifests/manual_review_required.flag"
PENDING_FILE="$ROOT/ai_image/manifests/pending-imagegen.json"
AUDIT_JSON="$ROOT/ai_image/reports/latest_distribution_audit.json"
LOG_DIR="$ROOT/ai_image/reports/autopilot_logs"

mkdir -p "$LOG_DIR"

log_line() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$CURRENT_LOG"
}

run_logged() {
  log_line "$*"
  (cd "$ROOT" && "$@") >>"$CURRENT_LOG" 2>&1
}

stop_with() {
  local code="$1"
  shift
  log_line "$*"
  exit "$code"
}

check_manual_review_flag() {
  if [ -f "$MANUAL_REVIEW_FLAG" ]; then
    try_reconcile_manual_review_flag || stop_with 2 "manual review required; stopping: $MANUAL_REVIEW_FLAG"
  fi
}

try_reconcile_manual_review_flag() {
  if [ ! -f "$MANUAL_REVIEW_FLAG" ]; then
    return 0
  fi
  log_line "manual review flag exists; attempting safe bounded-chunk reconcile"
  run_logged "$PYTHON_BIN" scripts/run_ai_image_pipeline_v3.py bounded-chunk-reconcile --root . --apply --clear-manual-flag-if-safe || true
  if [ ! -f "$MANUAL_REVIEW_FLAG" ]; then
    log_line "manual review flag cleared by safe reconcile"
    return 0
  fi
  log_line "manual review flag still requires attention after reconcile attempt"
  return 2
}

check_completion() {
  log_line "completion check"
  if (cd "$ROOT" && "$PYTHON_BIN" scripts/check_ai_image_completion_v3.py --root .) >>"$CURRENT_LOG" 2>&1; then
    stop_with 0 "target complete; stopping"
  fi
}

pending_status() {
  if [ ! -f "$PENDING_FILE" ]; then
    printf 'none\n'
    return 0
  fi
  "$PYTHON_BIN" - "$PENDING_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    value = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("invalid_pending_json")
    raise SystemExit(0)
if value.get("resolved") is True or value.get("status") in {"resolved", "cleared"}:
    print("resolved")
elif value.get("status") in {"pending_imagegen", "imagegen_started"}:
    print(value.get("status"))
else:
    print("unresolved_pending:" + str(value.get("assetId") or value.get("status") or "pending-imagegen.json"))
PY
}

recover_pending_if_needed() {
  local status
  status="$(pending_status)"
  case "$status" in
    pending_imagegen|imagegen_started)
      log_line "pending Image Gen result detected; recovering before chunk"
      local attempt
      for attempt in $(seq 1 "$MAX_PENDING_RECOVERY_FAILURES"); do
        log_line "pending recovery attempt $attempt/$MAX_PENDING_RECOVERY_FAILURES"
        if (cd "$ROOT" && CODEX_GENERATED_IMAGES_DIR="$GENERATED_DIR" "$PYTHON_BIN" scripts/recover_pending_imagegen_v3.py --root . --pending "$PENDING_FILE" --generated_root "$GENERATED_DIR" --out_dir ai_image) >>"$CURRENT_LOG" 2>&1; then
          log_line "pending recovery succeeded"
          run_logged "$PYTHON_BIN" scripts/qa_ai_images_file_v3.py --root .
          return 0
        fi
        sleep "$PENDING_RECOVERY_RETRY_SLEEP"
      done
      stop_with 4 "pending recovery failed repeatedly; stopping"
      ;;
    invalid_pending_json)
      stop_with 4 "pending-imagegen.json is invalid JSON; stopping"
      ;;
    none|resolved|cleared)
      return 0
      ;;
    unresolved_pending:*)
      printf 'unresolved_pending_imagegen=%s\nupdated_at=%s\n' "$status" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$MANUAL_REVIEW_FLAG"
      stop_with 4 "unresolved pending-imagegen checkpoint blocks autopilot: $status"
      ;;
    *)
      printf 'unresolved_pending_imagegen=%s\nupdated_at=%s\n' "$status" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$MANUAL_REVIEW_FLAG"
      stop_with 4 "unrecognized pending-imagegen checkpoint state blocks autopilot: $status"
      ;;
  esac
}

check_audit_stop_conditions() {
  if [ ! -f "$AUDIT_JSON" ]; then
    return 0
  fi
  local audit_result
  audit_result="$("$PYTHON_BIN" - "$AUDIT_JSON" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    audit = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"visual_json_invalid:audit_json_parse_failed:{exc}")
    raise SystemExit(0)

fail_conditions = set(audit.get("failConditions") or [])
if "visual_verdict_json_invalid" in fail_conditions:
    print("visual_json_invalid")
elif audit.get("finalDecision") == "needs_manual_review":
    print("manual_review_required")
else:
    print("ok")
PY
)"
  case "$audit_result" in
    visual_json_invalid*)
      stop_with 5 "visual-verdict JSON invalid; stopping: $audit_result"
      ;;
    manual_review_required)
      stop_with 2 "distribution audit requires manual review; stopping"
      ;;
    *)
      return 0
      ;;
  esac
}

run_distribution_audit() {
  run_logged "$PYTHON_BIN" scripts/audit_ai_profile_distribution_v3.py --root .
  check_audit_stop_conditions
  check_manual_review_flag
}

run_active_visual_qa() {
  if [ "$ACTIVE_VISUAL_QA" = "1" ]; then
    run_logged "$PYTHON_BIN" scripts/run_ai_image_pipeline_v3.py active-visual-qa-all --root .
    check_manual_review_flag
    return 0
  fi
  printf 'active_visual_qa_disabled\nupdated_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$MANUAL_REVIEW_FLAG"
  stop_with 2 "ACTIVE_VISUAL_QA=0; strict chunk autopilot cannot mark QA complete"
}

detect_omx_stop_patterns() {
  if grep -Eiq 'quota (exceeded|limit|reached)|usage limit|rate limit|rate.?limited|429|too many requests|credits? exhausted|billing limit' "$CURRENT_LOG"; then
    stop_with 3 "quota/usage/rate limit detected; stopping"
  fi
  if grep -Eiq 'image gen unavailable|imagegen unavailable|image generation unavailable|imagegen.*not available|image_gen.*not available|cannot invoke.*imagegen|tool.*imagegen.*not.*available' "$CURRENT_LOG"; then
    stop_with 3 "Image Gen unavailable; stopping"
  fi
}

run_after_chunk_checks() {
  run_logged "$PYTHON_BIN" scripts/qa_ai_images_file_v3.py --root .
  run_logged "$PYTHON_BIN" scripts/make_ai_image_contact_sheets_v3.py --root . --grouped --identity_sheets --chunked --stage pilot
  run_active_visual_qa
  run_distribution_audit
  check_completion
}

if [ ! -f "$PROMPT_FILE" ]; then
  CURRENT_LOG="$LOG_DIR/chunk_0.log"
  : >"$CURRENT_LOG"
  stop_with 2 "missing Ralph distribution-aware chunk prompt: $PROMPT_FILE"
fi

if ! command -v omx >/dev/null 2>&1; then
  CURRENT_LOG="$LOG_DIR/chunk_0.log"
  : >"$CURRENT_LOG"
  stop_with 3 "omx command unavailable; cannot call Codex Image Gen chunk runner"
fi

for chunk in $(seq 1 "$MAX_CHUNKS"); do
  CURRENT_LOG="$LOG_DIR/chunk_${chunk}.log"
  : >"$CURRENT_LOG"
  log_line "chunk $chunk/$MAX_CHUNKS start"

  check_completion
  check_manual_review_flag
  recover_pending_if_needed
  run_distribution_audit

  prompt="$(cat "$PROMPT_FILE")"
  log_line "calling omx exec with RALPH_DISTRIBUTION_AWARE_CHUNK_PROMPT"
  if ! (cd "$ROOT" && omx exec -C . "$prompt") >>"$CURRENT_LOG" 2>&1; then
    detect_omx_stop_patterns
    stop_with 2 "omx exec failed; see $CURRENT_LOG"
  fi
  detect_omx_stop_patterns
  check_manual_review_flag

  run_after_chunk_checks
  log_line "chunk $chunk/$MAX_CHUNKS complete"
done

CURRENT_LOG="$LOG_DIR/chunk_${MAX_CHUNKS}.log"
log_line "MAX_CHUNKS=$MAX_CHUNKS reached without final completion; stopping"
exit 2
