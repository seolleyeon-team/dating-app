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
BOOTSTRAP_MANIFEST=""
ALLOWED=()
FUNCTIONS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --allow-multiple-functions) ALLOW_MULTIPLE_FUNCTIONS=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --bootstrap-no-serving-revision-manifest)
      if [ -n "$BOOTSTRAP_MANIFEST" ]; then
        echo "bootstrap manifest may be supplied only once" >&2
        exit 2
      fi
      BOOTSTRAP_MANIFEST="$2"
      shift 2 ;;
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

if [ -n "$BOOTSTRAP_MANIFEST" ]; then
  if [ "$ALLOW_MULTIPLE_FUNCTIONS" -eq 1 ]; then
    echo "BOOTSTRAP_MULTI_FUNCTION_REFUSED: bootstrap mode is exact one function only" >&2
    exit 2
  fi
  if [ "${#FUNCTIONS[@]}" -ne 1 ]; then
    echo "BOOTSTRAP_EXACT_TARGET_REQUIRED: bootstrap mode requires exactly one function" >&2
    exit 2
  fi
  if [ "${#ALLOWED[@]}" -ne 0 ]; then
    echo "BOOTSTRAP_ALLOW_FLAG_REFUSED: --allow-* flags are not valid in bootstrap mode" >&2
    exit 2
  fi
fi

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

PRE_GUARD_ENV_SHA256="$(python scripts/deploy_functions_guarded_contract.py sha256 \
  --file "$ENV_FILE")"
DISCOVERY_PARAMS_FILE=""
cleanup_bootstrap_artifacts() {
  if [ -n "$DISCOVERY_PARAMS_FILE" ] && [ -f "$DISCOVERY_PARAMS_FILE" ]; then
    rm -f -- "$DISCOVERY_PARAMS_FILE"
  fi
  if [ -n "$BOOTSTRAP_MANIFEST" ]; then
    if ! python scripts/functions_bootstrap_generated_artifact.py \
      --repo-root "$REPO_ROOT" \
      --remove >/dev/null; then
      echo "GENERATED_ARTIFACT_CLEANUP_REFUSED: exact generated output was not removed" >&2
    fi
  fi
}
trap cleanup_bootstrap_artifacts EXIT

if [ -n "$BOOTSTRAP_MANIFEST" ]; then
  echo "[deploy] verify exact generated JSON before bootstrap build"
  python scripts/functions_bootstrap_generated_artifact.py \
    --repo-root "$REPO_ROOT"
  echo "[deploy] no-serving-revision bootstrap source preflight"
  python scripts/functions_bootstrap_env_guard.py \
    --repo-root "$REPO_ROOT" \
    --manifest "$BOOTSTRAP_MANIFEST" \
    --project "$PROJECT" \
    --region "$REGION" \
    --function "${FUNCTIONS[0]}" \
    --env-file "$ENV_FILE" \
    --source-dir "$FUNCTIONS_SOURCE/src" \
    --firebase-cli-version "$FIREBASE_TOOLS_VERSION" \
    --prebuild-source-only
else
  echo "[deploy] environment regression guard"
  python scripts/functions_env_regression_guard.py "${GUARD_ARGS[@]}" "${ALLOWED[@]}"
fi

# Match firebase.json's predeploy hook exactly. Do not install dependencies
# here: deploy readiness must not silently change the dependency graph or
# depend on network state. `npm ci --prefix "$FUNCTIONS_SOURCE"` is an
# explicit preparation step when this guard reports missing dependencies.
TSC_SHIM="$FUNCTIONS_SOURCE/node_modules/.bin/tsc"
TSC_WINDOWS_SHIM="$TSC_SHIM.cmd"
if [ ! -d "$FUNCTIONS_SOURCE/node_modules" ] || \
  { [ ! -f "$TSC_SHIM" ] && [ ! -f "$TSC_WINDOWS_SHIM" ]; }; then
  echo "FUNCTIONS_DEPENDENCIES_NOT_READY: missing node_modules or TypeScript tsc shim" >&2
  echo "  Prepare explicitly with: npm ci --prefix \"$FUNCTIONS_SOURCE\"" >&2
  exit 1
fi

echo "[deploy] Functions local predeploy build"
if ! (
  export RESOURCE_DIR="$FUNCTIONS_SOURCE"
  npm --prefix "$RESOURCE_DIR" run build
); then
  echo "FUNCTIONS_PREDEPLOY_BUILD_FAILED: Firebase deploy refused" >&2
  exit 1
fi
echo "[deploy] Functions predeploy build: PASS"

if [ -n "$BOOTSTRAP_MANIFEST" ]; then
  DISCOVERY_PARAMS_FILE="$(mktemp "${TMPDIR:-/tmp}/functions-build-params.XXXXXX")"
  echo "[deploy] discover complete Functions Build parameters with pinned CLI parser"
  npx -y --package="firebase-tools@$FIREBASE_TOOLS_VERSION" -- node \
    "$SCRIPT_DIR/functions_discover_build_params.js" \
    --functions-dir "$FUNCTIONS_SOURCE" \
    --project "$PROJECT" \
    --region "$REGION" \
    --runtime nodejs22 \
    --firebase-cli-version "$FIREBASE_TOOLS_VERSION" \
    > "$DISCOVERY_PARAMS_FILE"

  echo "[deploy] no-serving-revision bootstrap environment and parameter guard"
  python scripts/functions_bootstrap_env_guard.py \
    --repo-root "$REPO_ROOT" \
    --manifest "$BOOTSTRAP_MANIFEST" \
    --project "$PROJECT" \
    --region "$REGION" \
    --function "${FUNCTIONS[0]}" \
    --env-file "$ENV_FILE" \
    --source-dir "$FUNCTIONS_SOURCE/src" \
    --firebase-cli-version "$FIREBASE_TOOLS_VERSION" \
    --discovered-build-params "$DISCOVERY_PARAMS_FILE"

  echo "[deploy] remove only the verified generated JSON artifact"
  python scripts/functions_bootstrap_generated_artifact.py \
    --repo-root "$REPO_ROOT" \
    --remove
fi

# The dotenv contract and bytes must still be identical after the build and
# immediately before querying the pinned Firebase CLI or deploying.
python scripts/deploy_functions_guarded_contract.py "${CONTRACT_ARGS[@]}"
CURRENT_ENV_SHA256="$(python scripts/deploy_functions_guarded_contract.py sha256 \
  --file "$ENV_FILE")"
if [ "$CURRENT_ENV_SHA256" != "$PRE_GUARD_ENV_SHA256" ]; then
  echo "ENV REGRESSION GUARD: FAIL" >&2
  echo "  GUARDED_ENV_CHANGED_AFTER_GUARD: dotenv SHA-256 changed between guard and deploy" >&2
  exit 1
fi

FIREBASE_CLI_VERSION="$(npx -y "firebase-tools@$FIREBASE_TOOLS_VERSION" --version | tr -d '\r\n')"
if [ "$FIREBASE_CLI_VERSION" != "$FIREBASE_TOOLS_VERSION" ]; then
  echo "FIREBASE_CLI_VERSION_MISMATCH: expected $FIREBASE_TOOLS_VERSION, got $FIREBASE_CLI_VERSION" >&2
  exit 1
fi
echo "[deploy] Firebase CLI version: $FIREBASE_CLI_VERSION"

TARGETS=""
for fn in "${FUNCTIONS[@]}"; do
  TARGETS="${TARGETS:+$TARGETS,}functions:$fn"
done

echo "[deploy] firebase deploy --only $TARGETS"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[deploy] dry-run: Firebase deploy was not invoked"
  exit 0
fi
FUNCTIONS_DISCOVERY_TIMEOUT=30 npx -y "firebase-tools@$FIREBASE_TOOLS_VERSION" deploy --only "$TARGETS" --project "$PROJECT" --non-interactive

# No declarations on the way back. The intended change has been applied, so the
# serving revision must now match the env file exactly - any remaining
# difference is drift the deploy introduced.
echo "[deploy] post-deploy environment comparison"
python scripts/functions_env_regression_guard.py "${GUARD_ARGS[@]}"
echo "[deploy] done"
