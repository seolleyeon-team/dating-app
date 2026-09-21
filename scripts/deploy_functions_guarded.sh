#!/usr/bin/env bash
# Deploy specific Cloud Functions, but never silently drop their environment.
#
# `firebase deploy` replaces a function's environment with the env file's
# contents. On 2026-09-08 an incomplete file removed 19 variables from five
# production functions in one command, including the one that keeps queue
# dispatch fail-closed. Run the regression guard against the live revisions
# first, then deploy exactly the named functions.
#
# Usage:
#   scripts/deploy_functions_guarded.sh \
#     --project seolleyeon-final --region asia-northeast3 \
#     --env-file functions/.env.seolleyeon-final \
#     getCurrentAvatarGenerationStatus retryCurrentAvatarGeneration
#
# Declare each intended config change one key and one operation at a time:
#   --allow-remove-key KEY   --allow-add-key KEY   --allow-change-key KEY
# A declaration authorises exactly that key and exactly that operation. Any
# other difference still refuses the deploy.
set -euo pipefail

PROJECT=""
REGION=""
ENV_FILE=""
ALLOW_MULTIPLE_FUNCTIONS=0
DRY_RUN=0
ALLOWED=()
FUNCTIONS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --allow-multiple-functions) ALLOW_MULTIPLE_FUNCTIONS=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --allow-remove-key) ALLOWED+=(--allow-remove-key "$2"); shift 2 ;;
    --allow-add-key) ALLOWED+=(--allow-add-key "$2"); shift 2 ;;
    --allow-change-key) ALLOWED+=(--allow-change-key "$2"); shift 2 ;;
    --allow-removal|--allow-addition)
      echo "$1 waived every check for that key, a value change included." >&2
      echo "Use --allow-remove-key / --allow-add-key / --allow-change-key." >&2
      exit 2 ;;
    --) shift; break ;;
    -*) echo "unknown flag: $1" >&2; exit 2 ;;
    *) FUNCTIONS+=("$1"); shift ;;
  esac
done
FUNCTIONS+=("$@")

[ -n "$PROJECT" ] || { echo "--project is required" >&2; exit 2; }
[ -n "$REGION" ] || { echo "--region is required" >&2; exit 2; }
[ -n "$ENV_FILE" ] || { echo "--env-file is required" >&2; exit 2; }
[ "${#FUNCTIONS[@]}" -gt 0 ] || { echo "name at least one function" >&2; exit 2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
cd -- "$REPO_ROOT"

CONTRACT_ARGS=(
  validate
  --firebase-json "$REPO_ROOT/firebase.json"
  --project "$PROJECT"
  --env-file "$ENV_FILE"
)
for fn in "${FUNCTIONS[@]}"; do
  CONTRACT_ARGS+=(--function "$fn")
done
if [ "$ALLOW_MULTIPLE_FUNCTIONS" -eq 1 ]; then
  CONTRACT_ARGS+=(--allow-multiple-functions)
fi

echo "[deploy] Firebase dotenv/deployment target contract"
python scripts/deploy_functions_guarded_contract.py "${CONTRACT_ARGS[@]}"

FIREBASE_TOOLS_VERSION="$(python scripts/deploy_functions_guarded_contract.py version)"
FIREBASE_CLI_VERSION="$(npx -y "firebase-tools@$FIREBASE_TOOLS_VERSION" --version | tr -d '\r\n')"
if [ "$FIREBASE_CLI_VERSION" != "$FIREBASE_TOOLS_VERSION" ]; then
  echo "FIREBASE_CLI_VERSION_MISMATCH: expected $FIREBASE_TOOLS_VERSION, got $FIREBASE_CLI_VERSION" >&2
  exit 1
fi
echo "[deploy] Firebase CLI version: $FIREBASE_CLI_VERSION"

FUNCTIONS_SOURCE="$(python scripts/deploy_functions_guarded_contract.py source \
  --firebase-json "$REPO_ROOT/firebase.json")"

GUARD_ARGS=(
  --project "$PROJECT"
  --region "$REGION"
  --env-file "$ENV_FILE"
  --source-dir "$FUNCTIONS_SOURCE/src"
)
for fn in "${FUNCTIONS[@]}"; do
  GUARD_ARGS+=(--function "$fn")
done

echo "[deploy] environment regression guard"
PRE_GUARD_ENV_SHA256="$(python scripts/deploy_functions_guarded_contract.py sha256 \
  --file "$ENV_FILE")"
python scripts/functions_env_regression_guard.py "${GUARD_ARGS[@]}" "${ALLOWED[@]}"

# Recheck both the dotenv contract and its bytes immediately before invoking
# Firebase. The guard and Firebase must consume the same canonical file.
python scripts/deploy_functions_guarded_contract.py "${CONTRACT_ARGS[@]}"
CURRENT_ENV_SHA256="$(python scripts/deploy_functions_guarded_contract.py sha256 \
  --file "$ENV_FILE")"
if [ "$CURRENT_ENV_SHA256" != "$PRE_GUARD_ENV_SHA256" ]; then
  echo "ENV REGRESSION GUARD: FAIL" >&2
  echo "  GUARDED_ENV_CHANGED_AFTER_GUARD: dotenv SHA-256 changed between guard and deploy" >&2
  exit 1
fi

TARGETS=""
for fn in "${FUNCTIONS[@]}"; do
  TARGETS="${TARGETS:+$TARGETS,}functions:$fn"
done

echo "[deploy] firebase deploy --only $TARGETS"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[deploy] dry-run: Firebase CLI was not invoked"
  exit 0
fi
npx -y "firebase-tools@$FIREBASE_TOOLS_VERSION" deploy --only "$TARGETS" --project "$PROJECT" --non-interactive

# No declarations on the way back. The intended change has been applied, so the
# serving revision must now match the env file exactly - any remaining
# difference is drift the deploy introduced.
echo "[deploy] post-deploy environment comparison"
python scripts/functions_env_regression_guard.py "${GUARD_ARGS[@]}"
echo "[deploy] done"
