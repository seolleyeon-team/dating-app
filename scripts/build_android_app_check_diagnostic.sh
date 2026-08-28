#!/bin/zsh
# Creates a one-off internal-test AAB that exposes a redacted App Check token
# error on screen. It must never be used for a public/production release.

set -euo pipefail

project_root="${0:A:h:h}"
cd "$project_root"

readonly portone_store_id="store-ec95a751-307e-4b85-97bd-7c6fa0bbe0e2"
readonly artifact_path="$project_root/build/app/outputs/bundle/release/app-release.aab"
readonly archive_dir="${AAB_ARCHIVE_DIR:-$HOME/Desktop/설레연-AAB-보관}"

cleanup() {
  unset PORTONE_CHANNEL_KEY
}
trap cleanup EXIT

read -r -s "PORTONE_CHANNEL_KEY?PortOne 실 통합인증 Channel Key를 입력하세요: "
print

if [[ -z "$PORTONE_CHANNEL_KEY" || "$PORTONE_CHANNEL_KEY" != channel-key-* ]]; then
  print -u2 "Channel Key는 'channel-key-'로 시작해야 합니다."
  exit 1
fi

if [[ ! -f "$project_root/android/key.properties" ]]; then
  print -u2 "android/key.properties가 없어 Release AAB를 만들 수 없습니다."
  exit 1
fi

version=$(awk '/^version:[[:space:]]*/ { print $2; exit }' pubspec.yaml)
if [[ -z "$version" || "$version" != *+* ]]; then
  print -u2 "pubspec.yaml에서 버전 정보를 읽지 못했습니다."
  exit 1
fi

archive_name="Seolleyeon-${version//+/_}-app-check-diagnostic.aab"
archive_path="$archive_dir/$archive_name"
if [[ -e "$archive_path" ]]; then
  print -u2 "같은 버전의 진단 AAB가 이미 있습니다: $archive_path"
  print -u2 "빌드 번호를 올린 뒤 다시 실행하세요."
  exit 1
fi

flutter build appbundle --release \
  --dart-define="PORTONE_STORE_ID=$portone_store_id" \
  --dart-define="PORTONE_KG_INICIS_IDENTITY_CHANNEL_KEY=$PORTONE_CHANNEL_KEY" \
  --dart-define=APP_CHECK_DIAGNOSTIC_MODE=true \
  --dart-define="APP_CHECK_DIAGNOSTIC_BUILD_LABEL=$version"

[[ -f "$artifact_path" ]] || { print -u2 "AAB 출력 파일을 찾지 못했습니다."; exit 1; }
mkdir -p "$archive_dir"
cp "$artifact_path" "$archive_path"
sha256=$(shasum -a 256 "$archive_path" | awk '{print $1}')
print "진단 AAB 생성 완료"
print "버전: $version"
print "보관본: $archive_path"
print "SHA-256: $sha256"
