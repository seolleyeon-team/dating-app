#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python}"

"$PYTHON_BIN" -m compileall -q lib/ai_recommend_model scripts tests
"$PYTHON_BIN" scripts/qa_media_privacy.py --dry_run --fail_on_warning --scan_client_code

if rg -n "seolleyeon-private-source-photos" lib/features lib/services lib/shared lib/data -S; then
  echo "private source bucket name must not appear in Flutter/client code" >&2
  exit 1
fi

if rg -n "userPrivateMedia|clipEmbeddings" lib/features lib/services lib/shared -S; then
  echo "backend-only collections must not appear in Flutter display/service code" >&2
  exit 1
fi

if rg -n "onboarding\\s*(\\[['\"]photoUrls['\"]\\]|\\.photoUrls)|onboarding.*photoUrls" lib/features lib/services lib/shared -S; then
  echo "public display code must not read onboarding.photoUrls" >&2
  exit 1
fi

"$PYTHON_BIN" -m pytest \
  tests/test_avatar_media_privacy.py \
  tests/test_avatar_media_upload.py \
  tests/test_clip_job_handler.py \
  tests/test_clip_job_service.py \
  tests/test_avatar_approval_helpers.py \
  tests/test_avatar_generation_worker.py \
  tests/test_avatar_qa_cleanup.py \
  -q
npm --prefix functions run build
flutter test test/profile_display_image_resolver_test.dart test/avatar_source_photo_service_test.dart
