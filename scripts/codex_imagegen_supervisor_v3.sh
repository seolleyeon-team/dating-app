#!/usr/bin/env bash
# Seolleyeon Codex internal Image Gen supervisor v3.
#
# This supervisor never calls the OpenAI Image API or Batch API. Image creation
# is delegated only to Codex internal Image Gen through OMX/Ralph prompts.
set -uo pipefail

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd -P)"
PYTHON_BIN="${PYTHON_BIN:-python}"
OMX_BIN="${OMX_BIN:-omx}"
OMX_FLAGS="${OMX_FLAGS:-}"
MODE="${MODE:-auto}"

TARGET_APPROVED_IDENTITIES="${TARGET_APPROVED_IDENTITIES:-240}"
TARGET_APPROVED_ASSETS="${TARGET_APPROVED_ASSETS:-720}"
CHUNK_IDENTITIES="${CHUNK_IDENTITIES:-24}"
CHUNK_ASSETS="${CHUNK_ASSETS:-72}"

MAX_CHUNKS="${MAX_CHUNKS:-30}"
REQUIRED_UNATTENDED_CHUNKS="${REQUIRED_UNATTENDED_CHUNKS:-10}"
MAX_IDENTITY_TICKS="${MAX_IDENTITY_TICKS:-320}"
MAX_ASSET_TICKS="${MAX_ASSET_TICKS:-1200}"
MAX_PENDING_RECOVERY_FAILURES="${MAX_PENDING_RECOVERY_FAILURES:-3}"
PENDING_RECOVERY_RETRY_SLEEP="${PENDING_RECOVERY_RETRY_SLEEP:-3}"
TURN_TIMEOUT_SECONDS="${TURN_TIMEOUT_SECONDS:-0}"
SLEEP_BETWEEN_TURNS="${SLEEP_BETWEEN_TURNS:-15}"
ALLOW_PROMOTE_BACK_TO_CHUNK="${ALLOW_PROMOTE_BACK_TO_CHUNK:-0}"
PROMOTE_AFTER_IDENTITY_SUCCESS_TICKS="${PROMOTE_AFTER_IDENTITY_SUCCESS_TICKS:-8}"
MIN_DEFICIT_IDENTITIES_FOR_CHUNK="${MIN_DEFICIT_IDENTITIES_FOR_CHUNK:-24}"
ASSET_NO_PROGRESS_THRESHOLD="${ASSET_NO_PROGRESS_THRESHOLD:-2}"
ACTIVE_VISUAL_QA="${ACTIVE_VISUAL_QA:-1}"

CODEX_GENERATED_IMAGES_DIR="${CODEX_GENERATED_IMAGES_DIR:-$HOME/.codex/generated_images}"
export CODEX_GENERATED_IMAGES_DIR

LOG_DIR="${LOG_DIR:-ai_image/reports/autopilot_logs}"
MANIFEST_DIR="${MANIFEST_DIR:-ai_image/manifests}"
REPORT_DIR="${REPORT_DIR:-ai_image/reports}"
VISUAL_DIR="${VISUAL_DIR:-ai_image/reports/visual_verdict}"
CHUNK_PROMPT_FILE="${CHUNK_PROMPT_FILE:-ai_image/prompts/RALPH_DISTRIBUTION_AWARE_CHUNK_PROMPT.md}"
PROMPT_SOURCE="${PROMPT_SOURCE:-lib/ai_recommend_model/seolleyeon_ai_profile_prompt_v3_package/seolleyeon_ai_profile_prompt_v3.py}"

MANUAL_REVIEW_FLAG="$MANIFEST_DIR/manual_review_required.flag"
PENDING_FILE="$MANIFEST_DIR/pending-imagegen.json"
UNATTENDED_VERIFY_FILE="$REPORT_DIR/chunk_unattended_verification.txt"
MODE_TRANSITIONS_LOG="$LOG_DIR/mode_transitions.log"

STOP_PATTERN_REGEX='manual review|approval required|awaiting user|please confirm|image gen unavailable|imagegen unavailable|quota (exceeded|limit|reached)|insufficient quota|usage limit|rate limit|cannot continue|fatal|permission denied'

cd "$REPO_ROOT"
mkdir -p "$LOG_DIR" "$MANIFEST_DIR" "$REPORT_DIR" "$VISUAL_DIR"
: >>"$MODE_TRANSITIONS_LOG"

CURRENT_LOG="$LOG_DIR/supervisor_boot.log"

log() {
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$CURRENT_LOG"
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

run_with_optional_timeout() {
  if [ "$TURN_TIMEOUT_SECONDS" -gt 0 ] && have_cmd timeout; then
    timeout "$TURN_TIMEOUT_SECONDS" "$@"
  else
    "$@"
  fi
}

run_logged() {
  log "$*"
  (cd "$REPO_ROOT" && "$@") >>"$CURRENT_LOG" 2>&1
}

write_unattended_verification() {
  local status="$1"
  local reason="${2:-}"
  local chunk_qa_complete="${3:-false}"
  local chunk_distribution_updated="${4:-false}"
  local chunk_new_approved_identities="${5:-0}"
  local chunk_new_rejected_identities="${6:-0}"
  local chunk_new_needs_review_identities="${7:-0}"
  # Writes chunk_unattended_verification=PASS after the required unattended chunk streak succeeds.
  {
    printf 'chunk_unattended_verification=%s\n' "$status"
    printf 'meaning=unattended_execution_only_not_final_QA_or_distribution_completion\n'
    printf 'required_chunks=%s\n' "$REQUIRED_UNATTENDED_CHUNKS"
    printf 'mode=%s\n' "$MODE"
    printf 'chunk_qa_complete=%s\n' "$chunk_qa_complete"
    printf 'chunk_distribution_updated=%s\n' "$chunk_distribution_updated"
    printf 'chunk_new_approved_identities=%s\n' "$chunk_new_approved_identities"
    printf 'chunk_new_rejected_identities=%s\n' "$chunk_new_rejected_identities"
    printf 'chunk_new_needs_review_identities=%s\n' "$chunk_new_needs_review_identities"
    printf 'updated_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    if [ -n "$reason" ]; then
      printf 'reason=%s\n' "$reason"
    fi
  } >"$UNATTENDED_VERIFY_FILE"
}

log_mode_transition() {
  local from_mode="$1"
  local to_mode="$2"
  local reason="$3"
  local before_ids="${4:-0}"
  local after_ids="${5:-0}"
  local before_imgs="${6:-0}"
  local after_imgs="${7:-0}"
  printf '{"timestamp":"%s","from_mode":"%s","to_mode":"%s","reason":"%s","approvedIdentityCountBefore":%s,"approvedIdentityCountAfter":%s,"approvedAssetCountBefore":%s,"approvedAssetCountAfter":%s}\n' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$from_mode" "$to_mode" "$reason" \
    "$before_ids" "$after_ids" "$before_imgs" "$after_imgs" >>"$MODE_TRANSITIONS_LOG"
}

stop_now() {
  local code="$1"
  shift
  log "$*"
  exit "$code"
}

completion_check() {
  log "completion check"
  (cd "$REPO_ROOT" && "$PYTHON_BIN" scripts/check_ai_image_completion_v3.py --root .) >>"$CURRENT_LOG" 2>&1
}

manual_review_check() {
  [ -f "$MANUAL_REVIEW_FLAG" ]
}

try_reconcile_manual_review_flag() {
  if ! manual_review_check; then
    return 0
  fi
  log "manual review flag exists; attempting safe bounded-chunk reconcile"
  run_logged "$PYTHON_BIN" scripts/run_ai_image_pipeline_v3.py bounded-chunk-reconcile --root . --apply --clear-manual-flag-if-safe || true
  if ! manual_review_check; then
    log "manual review flag cleared by safe reconcile"
    return 0
  fi
  log "manual review flag still requires attention after reconcile attempt"
  return 2
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
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("invalid_pending_json")
    raise SystemExit(0)
if data.get("resolved") is True or data.get("status") in {"resolved", "cleared"}:
    print("resolved")
elif data.get("status") in {"pending_imagegen", "imagegen_started"}:
    print(data.get("status"))
else:
    print("unresolved_pending:" + str(data.get("assetId") or data.get("status") or "pending-imagegen.json"))
PY
}

recover_pending_if_needed() {
  local status
  status="$(pending_status)"
  case "$status" in
    pending_imagegen|imagegen_started)
      log "pending Image Gen result detected; recovering"
      local attempt
      for attempt in $(seq 1 "$MAX_PENDING_RECOVERY_FAILURES"); do
        log "pending recovery attempt $attempt/$MAX_PENDING_RECOVERY_FAILURES"
        if (cd "$REPO_ROOT" && CODEX_GENERATED_IMAGES_DIR="$CODEX_GENERATED_IMAGES_DIR" "$PYTHON_BIN" scripts/recover_pending_imagegen_v3.py --root . --pending "$PENDING_FILE" --generated_root "$CODEX_GENERATED_IMAGES_DIR" --out_dir ai_image) >>"$CURRENT_LOG" 2>&1; then
          log "pending recovery succeeded"
          return 0
        fi
        sleep "$PENDING_RECOVERY_RETRY_SLEEP"
      done
      log "pending recovery failed repeatedly"
      return 4
      ;;
    invalid_pending_json)
      log "pending-imagegen.json is invalid JSON"
      return 4
      ;;
    none|resolved|cleared)
      log "no pending Image Gen recovery needed"
      return 0
      ;;
    unresolved_pending:*)
      log "unresolved pending-imagegen checkpoint blocks automation: $status"
      printf 'unresolved_pending_imagegen=%s\nupdated_at=%s\n' "$status" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$MANUAL_REVIEW_FLAG"
      return 4
      ;;
    *)
      log "unrecognized pending-imagegen checkpoint state blocks automation: $status"
      printf 'unresolved_pending_imagegen=%s\nupdated_at=%s\n' "$status" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$MANUAL_REVIEW_FLAG"
      return 4
      ;;
  esac
}

file_qa() {
  run_logged "$PYTHON_BIN" scripts/qa_ai_images_file_v3.py --root .
}

contact_sheets() {
  run_logged "$PYTHON_BIN" scripts/make_ai_image_contact_sheets_v3.py --root . --grouped --identity_sheets --chunked --stage pilot
}

distribution_audit() {
  run_logged "$PYTHON_BIN" scripts/audit_ai_profile_distribution_v3.py --root .
  audit_stop_check
}

active_visual_qa() {
  if [ "$ACTIVE_VISUAL_QA" = "1" ]; then
    run_logged "$PYTHON_BIN" scripts/run_ai_image_pipeline_v3.py active-visual-qa-all --root .
    return $?
  fi
  printf 'active_visual_qa_disabled\nupdated_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$MANUAL_REVIEW_FLAG"
  log "ACTIVE_VISUAL_QA=0; strict supervisor will not mark QA complete"
  return 2
}

summary_step() {
  if [ -f scripts/summarize_ai_images_v3.py ]; then
    run_logged "$PYTHON_BIN" scripts/summarize_ai_images_v3.py --root .
  else
    log "summary skipped: scripts/summarize_ai_images_v3.py not found"
  fi
}

audit_stop_check() {
  "$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

audit_path = Path("ai_image/reports/latest_distribution_audit.json")
if not audit_path.exists():
    raise SystemExit(0)
try:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(5)
fail_conditions = set(audit.get("failConditions") or [])
if "visual_verdict_json_invalid" in fail_conditions:
    raise SystemExit(5)
if audit.get("finalDecision") == "needs_manual_review":
    raise SystemExit(2)
raise SystemExit(0)
PY
  local rc=$?
  case "$rc" in
    0) return 0 ;;
    2) log "distribution audit requires manual review"; return 2 ;;
    5) log "visual-verdict JSON invalid"; return 5 ;;
    *) return "$rc" ;;
  esac
}

before_run_checks() {
  completion_check && return 10
  if manual_review_check; then
    try_reconcile_manual_review_flag || return 2
  fi
  recover_pending_if_needed || return $?
  file_qa || return $?
  distribution_audit || return $?
  return 0
}

after_run_checks() {
  recover_pending_if_needed || return $?
  file_qa || return $?
  contact_sheets || return $?
  active_visual_qa || return $?
  distribution_audit || return $?
  summary_step || return $?
  completion_check && return 10
  if manual_review_check; then
    try_reconcile_manual_review_flag || return 2
  fi
  return 0
}

count_raw_images() {
  if [ -d ai_image/raw ]; then
    find ai_image/raw -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.webp' \) 2>/dev/null | wc -l | tr -d ' '
  else
    printf '0\n'
  fi
}

read_progress() {
  "$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

path = Path("ai_image/reports/latest_distribution_audit.json")
manifests = Path("ai_image/manifests")
if not path.exists():
    print("0 0 0 0 0 0")
    raise SystemExit
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0 0 0 0 0 0")
    raise SystemExit
ids = data.get("approvedCompleteIdentityCount") or data.get("approvedCompleteIdentities") or 0
imgs = data.get("approvedImageCount") or data.get("approvedImages") or 0
def count_jsonl(name):
    file = manifests / name
    if not file.exists():
        return 0
    return sum(1 for line in file.read_text(encoding="utf-8").splitlines() if line.strip())
asset_qa = count_jsonl("asset_qa_manifest.jsonl")
identity_qa = count_jsonl("identity_qa_manifest.jsonl")
resolved_pending = count_jsonl("completed_pending_imagegen.jsonl")
rejected_identity = count_jsonl("rejected_identity_manifest.jsonl")
print(f"{ids} {imgs} {asset_qa} {identity_qa} {resolved_pending} {rejected_identity}")
PY
}

classify_stop_log() {
  local log_file="$1"
  if grep -Eiq "$STOP_PATTERN_REGEX" "$log_file"; then
    if grep -Eiq 'image gen unavailable|imagegen unavailable' "$log_file"; then
      printf 'imagegen_unavailable\n'
    elif grep -Eiq 'quota (exceeded|limit|reached)|insufficient quota|usage limit|rate limit' "$log_file"; then
      printf 'quota_or_rate_limit\n'
    elif grep -Eiq 'manual review|approval required|awaiting user|please confirm' "$log_file"; then
      printf 'manual_or_user_required\n'
    elif grep -Eiq 'permission denied' "$log_file"; then
      printf 'permission_denied\n'
    else
      printf 'fatal_or_cannot_continue\n'
    fi
    return 0
  fi
  printf 'ok\n'
}

run_omx_prompt() {
  local prompt="$1"
  local log_file="$2"
  log "running OMX prompt -> $log_file"
  set +e
  # shellcheck disable=SC2086
  (cd "$REPO_ROOT" && run_with_optional_timeout "$OMX_BIN" exec $OMX_FLAGS -C . "$prompt") >>"$log_file" 2>&1
  local rc=$?
  set -e
  cat "$log_file" >>"$CURRENT_LOG"
  local stop_reason
  stop_reason="$(classify_stop_log "$log_file")"
  if [ "$stop_reason" != "ok" ]; then
    log "stop pattern detected: $stop_reason"
    return 88
  fi
  return "$rc"
}

chunk_prompt() {
  if [ -f "$CHUNK_PROMPT_FILE" ]; then
    cat "$CHUNK_PROMPT_FILE"
    return 0
  fi
  cat <<PROMPT_EOF
\$ralph "Run only one bounded Seolleyeon distribution-aware Codex Image Gen chunk.

Use internal Image Gen only. Do not use OpenAI Image API. Do not use Batch API. Do not require OPENAI_API_KEY.
Do not modify SVD/KNN/CLIP/RRF recommender scripts.

Process at most ${CHUNK_IDENTITIES} incomplete identities and at most ${CHUNK_ASSETS} images. Do not continue to another chunk in the same Ralph run.
Generate only deficit buckets. Do not generate quota-full buckets. Do not generate looksLevelBand 4.4-5.0.
Generate face_card first, then silhouette_card and vibe_card using face_card as same-person reference when supported.
Checkpoint before and after every Image Gen. Run visual-verdict QA with strict JSON.
If visual-verdict is unavailable, invalid, cannot return strict JSON, or cannot be applied, write ai_image/manifests/manual_review_required.flag and stop.
If visual-verdict and numeric audit disagree, write ai_image/manifests/manual_review_required.flag.
Stop after this one chunk."
PROMPT_EOF
}

identity_prompt() {
  cat <<'PROMPT_EOF'
$ralph "Run exactly one Seolleyeon distribution-aware identity generation tick.

Use internal Image Gen only. Do not use OpenAI Image API. Do not use Batch API. Do not require OPENAI_API_KEY.
Do not modify SVD/KNN/CLIP/RRF recommender scripts.

Before generating, run completion check, manual review flag check, pending recovery, file QA, and distribution audit.
If target is not complete, select exactly one incomplete identity from a deficit bucket. Generate face_card first, then silhouette_card and vibe_card using face_card as same-person reference when supported. Checkpoint before and after every Image Gen. Run visual-verdict QA with strict JSON. If visual-verdict is unavailable, invalid, cannot return strict JSON, or cannot be applied, write ai_image/manifests/manual_review_required.flag and stop. Run numeric distribution audit. Stop after this one identity."
PROMPT_EOF
}

asset_prompt() {
  cat <<'PROMPT_EOF'
$ralph "Run exactly one Seolleyeon distribution-aware asset generation tick.

Use internal Image Gen only. Do not use OpenAI Image API. Do not use Batch API. Do not require OPENAI_API_KEY.
Do not modify SVD/KNN/CLIP/RRF recommender scripts.

Before generating, run completion check, manual review flag check, pending recovery, file QA, and distribution audit.
If target is not complete, select exactly one pending asset from a deficit bucket. Respect shot order: face_card before silhouette_card and vibe_card. Use face_card as same-person reference when supported. Write pending-imagegen.json before Image Gen. Invoke Image Gen exactly once. Recover/import the generated image. Run file QA. Run visual-verdict QA with strict JSON if this asset/identity becomes reviewable. If visual-verdict is unavailable, invalid, cannot return strict JSON, or cannot be applied, write ai_image/manifests/manual_review_required.flag and stop. Run numeric distribution audit. Stop after this one asset."
PROMPT_EOF
}

ensure_prepared_queue() {
  if [ -s ai_image/manifests/imagegen_queue.jsonl ]; then
    return 0
  fi
  log "imagegen queue missing; preparing 720 manifest"
  run_logged "$PYTHON_BIN" scripts/prepare_ai_image_assets_v3.py --root . --female_count 120 --male_count 120 --reserve_female_count 20 --reserve_male_count 20
}

preflight() {
  log "preflight: repo=$REPO_ROOT"
  log "preflight: MODE=$MODE CODEX_GENERATED_IMAGES_DIR=$CODEX_GENERATED_IMAGES_DIR"
  if ! have_cmd "$PYTHON_BIN"; then
    stop_now 40 "Python binary not found: $PYTHON_BIN"
  fi
  if ! have_cmd "$OMX_BIN" && ! have_cmd codex; then
    stop_now 40 "Neither OMX nor Codex CLI was found for bounded chunk execution"
  fi
  if ! have_cmd "$OMX_BIN"; then
    log "OMX binary not found: $OMX_BIN; bounded chunk mode will rely on Codex fallback, identity/asset Ralph fallback may be unavailable"
  fi
  if [ ! -f "$PROMPT_SOURCE" ]; then
    stop_now 41 "missing prompt source: $PROMPT_SOURCE"
  fi
  mkdir -p ai_image/raw ai_image/approved ai_image/rejected ai_image/female ai_image/male
  ensure_prepared_queue || stop_now 41 "failed to prepare imagegen queue"
  distribution_audit || true
}

handle_check_rc() {
  local rc="$1"
  local scope="$2"
  case "$rc" in
    0) return 0 ;;
    10) log "$scope: target complete"; return 10 ;;
    2) log "$scope: manual review required"; return 2 ;;
    4) log "$scope: pending recovery failed"; return 4 ;;
    5) log "$scope: visual-verdict JSON invalid"; return 5 ;;
    *) log "$scope: check failed rc=$rc"; return "$rc" ;;
  esac
}

run_one_prompt_tick() {
  local kind="$1"
  local index="$2"
  local prompt="$3"
  local log_file="$4"
  : >"$log_file"
  CURRENT_LOG="$log_file"
  log "===== $kind run $index start ====="

  before_run_checks
  local rc=$?
  handle_check_rc "$rc" "$kind before-run" || return $?
  if [ "$rc" -eq 10 ]; then
    return 10
  fi

  run_omx_prompt "$prompt" "$log_file"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    log "$kind OMX run failed rc=$rc"
    return "$rc"
  fi

  after_run_checks
  rc=$?
  handle_check_rc "$rc" "$kind after-run" || return $?
  if [ "$rc" -eq 10 ]; then
    return 10
  fi

  log "===== $kind run $index complete ====="
  return 0
}

run_bounded_chunk_tick() {
  local index="$1"
  local log_file="$2"
  : >"$log_file"
  CURRENT_LOG="$log_file"
  log "===== bounded chunk run $index start ====="

  before_run_checks
  local rc=$?
  handle_check_rc "$rc" "bounded chunk before-run" || return $?
  if [ "$rc" -eq 10 ]; then
    return 10
  fi

  run_logged "$PYTHON_BIN" scripts/run_ai_image_pipeline_v3.py bounded-chunk-validate-plan --root .
  rc=$?
  if [ "$rc" -ne 0 ]; then
    log "current bounded chunk plan is missing, dry-run, stale, or non-executable; creating a fresh production plan"
    run_logged "$PYTHON_BIN" scripts/run_ai_image_pipeline_v3.py bounded-chunk-plan --root . --production --force-replan --abandon-current
    rc=$?
    if [ "$rc" -ne 0 ]; then
      log "bounded production plan creation failed rc=$rc"
      return "$rc"
    fi
  fi

  run_logged "$PYTHON_BIN" scripts/run_ai_image_pipeline_v3.py bounded-chunk-run --root .
  rc=$?
  if [ "$rc" -ne 0 ]; then
    log "bounded chunk executor failed rc=$rc"
    return "$rc"
  fi

  completion_check && return 10
  if manual_review_check; then
    log "manual review flag exists after bounded chunk run"
    return 2
  fi
  log "===== bounded chunk run $index complete ====="
  return 0
}

run_chunk_loop() {
  local max_runs="$1"
  local verify_unattended="${2:-0}"
  local success_runs=0
  local zero_approved_identity_chunks=0
  local i
  for i in $(seq 1 "$max_runs"); do
    local before_ids before_imgs before_asset_qa before_identity_qa before_pending before_rejected
    local after_ids after_imgs after_asset_qa after_identity_qa after_pending after_rejected log_file
    log_file="$LOG_DIR/chunk_${i}.log"
    CURRENT_LOG="$log_file"
    read -r before_ids before_imgs before_asset_qa before_identity_qa before_pending before_rejected <<<"$(read_progress)"

    run_bounded_chunk_tick "$i/$max_runs" "$log_file"
    local rc=$?
    if [ "$rc" -eq 10 ]; then
      return 0
    fi
    if [ "$rc" -ne 0 ]; then
      if [ "$verify_unattended" = "1" ]; then
        write_unattended_verification "FAIL" "chunk_run_${i}_failed_rc_${rc}"
      fi
      return "$rc"
    fi

    read -r after_ids after_imgs after_asset_qa after_identity_qa after_pending after_rejected <<<"$(read_progress)"
    log "progress: approved identities $before_ids -> $after_ids, approved images $before_imgs -> $after_imgs, asset QA $before_asset_qa -> $after_asset_qa, identity QA $before_identity_qa -> $after_identity_qa, resolved pending $before_pending -> $after_pending"
    if [ "$after_ids" -le "$before_ids" ] && [ "$after_imgs" -le "$before_imgs" ] && [ "$after_asset_qa" -le "$before_asset_qa" ] && [ "$after_identity_qa" -le "$before_identity_qa" ] && [ "$after_pending" -le "$before_pending" ] && [ "$after_rejected" -le "$before_rejected" ]; then
      log "chunk made no progress"
      if [ "$verify_unattended" = "1" ]; then
        write_unattended_verification "FAIL" "chunk_run_${i}_no_progress"
      fi
      return 87
    fi
    if [ "$after_ids" -le "$before_ids" ]; then
      zero_approved_identity_chunks=$((zero_approved_identity_chunks + 1))
    else
      zero_approved_identity_chunks=0
    fi
    if [ "$zero_approved_identity_chunks" -ge 2 ]; then
      log "two consecutive chunks added zero approved identities"
      if [ "$verify_unattended" = "1" ]; then
        write_unattended_verification "FAIL" "two_consecutive_chunks_zero_approved_identities"
      fi
      return 87
    fi

    success_runs=$((success_runs + 1))
    if [ "$verify_unattended" = "1" ] && [ "$success_runs" -ge "$REQUIRED_UNATTENDED_CHUNKS" ]; then
      write_unattended_verification "PASS" "" "false" "true" "$((after_ids - before_ids))" "$((after_rejected - before_rejected))" "0"
      log "chunk unattended verification PASS: $success_runs successful chunks"
      return 0
    fi
    sleep "$SLEEP_BETWEEN_TURNS"
  done
  if [ "$verify_unattended" = "1" ]; then
    write_unattended_verification "FAIL" "only_${success_runs}_successful_chunks"
    return 87
  fi
  return 0
}

run_identity_loop() {
  local i
  local zero_identity_ticks=0
  local consecutive_identity_success=0
  local promotion_attempted=0
  for i in $(seq 1 "$MAX_IDENTITY_TICKS"); do
    local before_ids before_imgs before_asset_qa before_identity_qa before_pending before_rejected
    local after_ids after_imgs after_asset_qa after_identity_qa after_pending after_rejected
    read -r before_ids before_imgs before_asset_qa before_identity_qa before_pending before_rejected <<<"$(read_progress)"
    run_one_prompt_tick "identity" "$i/$MAX_IDENTITY_TICKS" "$(identity_prompt)" "$LOG_DIR/identity_tick_${i}.log"
    local rc=$?
    if [ "$rc" -eq 10 ]; then
      return 0
    fi
    if [ "$rc" -ne 0 ]; then
      return "$rc"
    fi
    read -r after_ids after_imgs after_asset_qa after_identity_qa after_pending after_rejected <<<"$(read_progress)"
    if [ "$after_ids" -le "$before_ids" ]; then
      zero_identity_ticks=$((zero_identity_ticks + 1))
      consecutive_identity_success=0
    else
      zero_identity_ticks=0
      consecutive_identity_success=$((consecutive_identity_success + 1))
    fi
    if [ "$zero_identity_ticks" -ge 3 ]; then
      log "identity mode added zero approved identities for three ticks"
      return 87
    fi
    if [ "$ALLOW_PROMOTE_BACK_TO_CHUNK" = "1" ] && [ "$promotion_attempted" = "0" ] && [ "$consecutive_identity_success" -ge "$PROMOTE_AFTER_IDENTITY_SUCCESS_TICKS" ]; then
      local remaining_deficit=$((TARGET_APPROVED_IDENTITIES - after_ids))
      if [ "$remaining_deficit" -ge "$MIN_DEFICIT_IDENTITIES_FOR_CHUNK" ]; then
        log "optional promotion probe from identity to chunk"
        log_mode_transition "identity" "chunk" "optional_promotion_probe" "$before_ids" "$after_ids" "$before_imgs" "$after_imgs"
        promotion_attempted=1
        if ! run_chunk_loop 1 0; then
          log "optional chunk probe failed; returning to identity mode and disabling further promotion"
          log_mode_transition "chunk" "identity" "optional_promotion_probe_failed" "$before_ids" "$after_ids" "$before_imgs" "$after_imgs"
        fi
      fi
    fi
    sleep "$SLEEP_BETWEEN_TURNS"
  done
  return 1
}

run_asset_loop() {
  local i
  local zero_asset_ticks=0
  for i in $(seq 1 "$MAX_ASSET_TICKS"); do
    local before_ids before_imgs before_asset_qa before_identity_qa before_pending before_rejected
    local after_ids after_imgs after_asset_qa after_identity_qa after_pending after_rejected
    read -r before_ids before_imgs before_asset_qa before_identity_qa before_pending before_rejected <<<"$(read_progress)"
    run_one_prompt_tick "asset" "$i/$MAX_ASSET_TICKS" "$(asset_prompt)" "$LOG_DIR/asset_tick_${i}.log"
    local rc=$?
    if [ "$rc" -eq 10 ]; then
      return 0
    fi
    if [ "$rc" -ne 0 ]; then
      return "$rc"
    fi
    read -r after_ids after_imgs after_asset_qa after_identity_qa after_pending after_rejected <<<"$(read_progress)"
    if [ "$after_ids" -le "$before_ids" ] && [ "$after_imgs" -le "$before_imgs" ] && [ "$after_asset_qa" -le "$before_asset_qa" ] && [ "$after_identity_qa" -le "$before_identity_qa" ] && [ "$after_pending" -le "$before_pending" ] && [ "$after_rejected" -le "$before_rejected" ]; then
      zero_asset_ticks=$((zero_asset_ticks + 1))
    else
      zero_asset_ticks=0
    fi
    if [ "$zero_asset_ticks" -ge "$ASSET_NO_PROGRESS_THRESHOLD" ]; then
      log "asset mode made no progress; writing manual review flag"
      printf 'asset_mode_no_progress\nupdated_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" >"$MANUAL_REVIEW_FLAG"
      return 87
    fi
    sleep "$SLEEP_BETWEEN_TURNS"
  done
  return 1
}

main() {
  CURRENT_LOG="$LOG_DIR/supervisor_$(date -u '+%Y%m%dT%H%M%SZ').log"
  : >"$CURRENT_LOG"
  write_unattended_verification "PENDING" "supervisor_started"
  preflight

  case "$MODE" in
    chunk)
      run_chunk_loop "$MAX_CHUNKS" 0
      ;;
    identity)
      run_identity_loop
      ;;
    asset)
      run_asset_loop
      ;;
    auto)
      log "MODE=auto: verifying chunk mode for $REQUIRED_UNATTENDED_CHUNKS unattended chunks"
      if run_chunk_loop "$REQUIRED_UNATTENDED_CHUNKS" 1; then
        if completion_check; then
          log "target complete after chunk verification"
          exit 0
        fi
        local remaining=$((MAX_CHUNKS - REQUIRED_UNATTENDED_CHUNKS))
        if [ "$remaining" -gt 0 ]; then
          log "chunk mode verified; continuing up to $remaining additional chunks"
          if ! run_chunk_loop "$remaining" 0; then
            log "post-verification chunk mode failed; falling back to identity mode"
            log_mode_transition "chunk" "identity" "post_verification_chunk_failed"
          fi
        fi
        if completion_check; then
          log "target complete after chunk mode"
          exit 0
        fi
      else
        log "chunk mode did not pass unattended verification; falling back to identity mode"
        log_mode_transition "chunk" "identity" "unattended_chunk_verification_failed"
      fi

      if run_identity_loop; then
        exit 0
      fi
      log "identity mode failed or stalled; falling back to asset mode"
      log_mode_transition "identity" "asset" "identity_mode_failed_or_stalled"
      run_asset_loop
      ;;
    *)
      stop_now 2 "unknown MODE=$MODE"
      ;;
  esac

  if completion_check; then
    log "DONE: completion check passed at final"
    exit 0
  fi
  log "finished without completion; inspect $LOG_DIR and ai_image/reports/latest_distribution_audit.json"
  exit 1
}

main "$@"
